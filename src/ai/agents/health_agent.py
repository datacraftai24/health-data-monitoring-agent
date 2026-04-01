"""Health agent — handles glucose queries with LIVE data, trends, and health status."""

import logging
from datetime import datetime, timedelta, timezone

from google import genai
from google.genai import types
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.engine.memory_manager import memory_manager
from src.engine.user_context import user_context_manager
from src.models.conversation import ConversationLog
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)

HEALTH_SYSTEM_PROMPT = """You are MetaboCoach's health agent. You have REAL-TIME access to the user's
FreeStyle Libre 2 CGM sensor. You ARE monitoring their glucose continuously.

NEVER say you can't monitor or don't have access. You DO have the data — it's shown below.
The reading below is LIVE — fetched right now, not cached.

Who they are:
{user_profile}

Current health data:
{health_data}

Learned patterns:
{memories}

Guidelines:
- Lead with the actual numbers — the glucose value shown above is current and accurate
- Be concise (under 150 words)
- If glucose is in range (3.9-9.0), acknowledge it positively
- If trending up/down, suggest action
- Reference their known spike foods and crash triggers from the profile
- Connect glucose to how they might feel (energy, focus, fatigue)
- If the reading is stale (> 15 min old), mention it and say you'll get a fresh one next poll"""


class HealthAgent:
    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def handle(self, message: str, user: User, db: AsyncSession) -> str:
        """Handle a health/glucose query with LIVE data fetch."""
        health_data = await self._get_health_data(db, user)
        memories = await memory_manager.get_context_text(db, str(user.id), "health")
        user_profile = await user_context_manager.get_profile_text(db, user)

        system = HEALTH_SYSTEM_PROMPT.format(
            user_profile=user_profile,
            health_data=health_data,
            memories=memories,
        )

        # Recent conversation for context
        history_result = await db.execute(
            select(ConversationLog)
            .where(ConversationLog.user_id == user.id)
            .order_by(ConversationLog.timestamp.desc())
            .limit(6)
        )
        history_rows = list(reversed(history_result.scalars().all()))

        contents = []
        for row in history_rows:
            role = "user" if row.direction == "in" else "model"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=row.message[:500])])
            )
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.5,
                max_output_tokens=300,
            ),
        )
        return response.text

    async def _get_health_data(self, db: AsyncSession, user: User) -> str:
        """Get health data — try LIVE fetch first, fall back to DB."""
        lines = []

        # Always try live fetch when user explicitly asks about glucose
        from src.ingestion.libre import libre_client
        live_reading = None
        try:
            if user.libre_patient_id:
                live_reading = await libre_client.get_latest_for_user(user)
        except Exception:
            logger.debug("Live glucose fetch failed for user %s", user.id)

        if live_reading:
            lines.append(f"LIVE glucose: {live_reading['glucose_mmol']:.1f} mmol/L")
            trend = trend_arrow_to_label(live_reading.get("trend_arrow"))
            lines.append(f"Trend: {trend or 'unknown'}")
            lines.append(f"Reading time: {live_reading.get('timestamp', 'just now')}")
            lines.append("(This is a LIVE reading, just fetched)")
        else:
            # Fall back to latest DB reading
            result = await db.execute(
                select(GlucoseReading)
                .where(GlucoseReading.user_id == user.id)
                .order_by(GlucoseReading.timestamp.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest:
                age_min = int((datetime.now(timezone.utc) - latest.timestamp).total_seconds() / 60)
                stale_note = " (STALE — live fetch failed)" if age_min > 15 else ""
                lines.append(f"Current glucose: {latest.glucose_mmol:.1f} mmol/L{stale_note}")
                lines.append(f"Trend: {trend_arrow_to_label(latest.trend_arrow) or 'unknown'}")
                lines.append(f"Reading time: {latest.timestamp.strftime('%I:%M %p')} ({age_min} min ago)")
            else:
                lines.append("No glucose data available yet.")

        # Today's stats
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stats = await db.execute(
            select(
                func.avg(GlucoseReading.glucose_mmol),
                func.min(GlucoseReading.glucose_mmol),
                func.max(GlucoseReading.glucose_mmol),
                func.count(GlucoseReading.id),
            ).where(
                GlucoseReading.user_id == user.id,
                GlucoseReading.timestamp >= today_start,
            )
        )
        avg, min_g, max_g, count = stats.one()
        if count and count > 0:
            lines.append(f"Today: avg {avg:.1f}, range {min_g:.1f}-{max_g:.1f} mmol/L ({count} readings)")

        # Last meal
        meal_result = await db.execute(
            select(Meal)
            .where(Meal.user_id == user.id)
            .order_by(Meal.timestamp.desc())
            .limit(1)
        )
        last_meal = meal_result.scalar_one_or_none()
        if last_meal:
            mins_ago = int((now - last_meal.timestamp).total_seconds() / 60)
            lines.append(f"Last meal: {last_meal.description} ({mins_ago} min ago)")

        return "\n".join(lines) if lines else "No health data available."


health_agent = HealthAgent()
