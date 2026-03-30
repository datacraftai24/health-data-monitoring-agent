"""General agent — conversational fallback with full health + focus context."""

import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.engine.memory_manager import memory_manager
from src.models.conversation import ConversationLog
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)

GENERAL_SYSTEM_PROMPT = """You are MetaboCoach — a personal metabolic health + productivity AI.

You ARE connected to the user's FreeStyle Libre 2 CGM sensor. You monitor glucose every 5 minutes.
You track meals, analyze food photos, and learn food-glucose responses over time.
You also run a focus coaching system (morning rituals, focus blocks, daily wins).

NEVER say you can't monitor or don't have access to health data.

User: {user_name}
Current health: {health_state}
Recent memories: {memories}

Guidelines:
- Be warm but direct. Not generic.
- Lead with data when available.
- Keep responses under 200 words.
- If user mentions food, suggest they send a photo or describe it for analysis.
- If user asks about glucose, give the actual reading.
- Connect health patterns to productivity when relevant."""


class GeneralAgent:
    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def handle(self, message: str, user: User, db: AsyncSession) -> str:
        """Handle general conversation with full context + history."""
        health_state = await self._get_health_state(db, user)
        memories = await memory_manager.get_context_text(db, str(user.id), limit=10)

        system = GENERAL_SYSTEM_PROMPT.format(
            user_name=user.name or "User",
            health_state=health_state,
            memories=memories,
        )

        # Build conversation history from recent logs
        history_result = await db.execute(
            select(ConversationLog)
            .where(ConversationLog.user_id == user.id)
            .order_by(ConversationLog.timestamp.desc())
            .limit(10)
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
                temperature=0.7,
                max_output_tokens=400,
            ),
        )
        return response.text

    async def _get_health_state(self, db: AsyncSession, user: User) -> str:
        lines = []

        result = await db.execute(
            select(GlucoseReading)
            .where(GlucoseReading.user_id == user.id)
            .order_by(GlucoseReading.timestamp.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest:
            lines.append(f"Glucose: {latest.glucose_mmol:.1f} mmol/L ({trend_arrow_to_label(latest.trend_arrow)})")
            lines.append(f"Reading: {latest.timestamp.strftime('%I:%M %p')}")

        meal_result = await db.execute(
            select(Meal).where(Meal.user_id == user.id).order_by(Meal.timestamp.desc()).limit(1)
        )
        last_meal = meal_result.scalar_one_or_none()
        if last_meal:
            mins_ago = int((datetime.now(timezone.utc) - last_meal.timestamp).total_seconds() / 60)
            lines.append(f"Last meal: {last_meal.description} ({mins_ago} min ago)")

        return "\n".join(lines) if lines else "No data yet."


general_agent = GeneralAgent()
