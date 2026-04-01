"""General agent — conversational fallback with full health + focus + user context."""

import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.engine.memory_manager import memory_manager
from src.engine.user_context import user_context_manager
from src.models.conversation import ConversationLog
from src.models.focus import DailyFocus, TodoItem
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)

GENERAL_SYSTEM_PROMPT = """You are MetaboCoach — a personal metabolic health + productivity coach.

You ARE connected to the user's FreeStyle Libre 2 CGM sensor. You monitor glucose every 5 minutes.
You track meals, analyze food photos, and learn food-glucose responses over time.
You also coach focus, habits, and daily productivity — naturally, not through commands.

NEVER say you can't monitor or don't have access to health data.
NEVER say you don't have their to-do list or task list — you DO. It's shown below.

Who they are:
{user_profile}

Current health:
{health_state}

Today's focus:
{focus_state}

Active to-do list:
{todo_list}

Guidelines:
- Be warm but direct. Not generic. You know this person.
- Lead with data when available.
- Keep responses under 200 words.
- If user mentions food, suggest they send a photo or describe it for analysis.
- If user asks about glucose, give the actual reading from the health state above.
- If user asks about their to-do list, tasks, or what they need to do, use the todo list AND
  pending tasks from their profile. Never say you don't have it.
- If user casually mentions something they need to do ("I need to email X"), acknowledge it
  and it will be captured in their profile automatically.
- Connect health patterns to productivity when relevant.
- If user says something that sounds like a task completion, acknowledge it."""


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
        user_profile = await user_context_manager.get_profile_text(db, user)
        focus_state = await self._get_focus_state(db, user)
        todo_list = await self._get_todo_list(db, user)

        system = GENERAL_SYSTEM_PROMPT.format(
            user_name=user.name or "User",
            user_profile=user_profile,
            health_state=health_state,
            focus_state=focus_state,
            todo_list=todo_list,
        )

        # Build conversation history
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
        """Get current health state — always fetch freshest glucose reading."""
        lines = []

        # Try live fetch first, fall back to DB
        from src.ingestion.libre import libre_client
        live_reading = None
        try:
            if user.libre_patient_id:
                live_reading = await libre_client.get_latest_for_user(user)
        except Exception:
            logger.debug("Live glucose fetch failed for user %s, using DB", user.id)

        if live_reading:
            lines.append(f"Glucose: {live_reading['glucose_mmol']:.1f} mmol/L "
                        f"({trend_arrow_to_label(live_reading.get('trend_arrow')) or 'unknown trend'})")
            lines.append(f"Reading: {live_reading.get('timestamp', 'just now')}")
        else:
            result = await db.execute(
                select(GlucoseReading)
                .where(GlucoseReading.user_id == user.id)
                .order_by(GlucoseReading.timestamp.desc())
                .limit(1)
            )
            latest = result.scalar_one_or_none()
            if latest:
                age_min = int((datetime.now(timezone.utc) - latest.timestamp).total_seconds() / 60)
                lines.append(f"Glucose: {latest.glucose_mmol:.1f} mmol/L "
                            f"({trend_arrow_to_label(latest.trend_arrow) or 'unknown'})")
                lines.append(f"Reading: {latest.timestamp.strftime('%I:%M %p')} ({age_min} min ago)")

        meal_result = await db.execute(
            select(Meal).where(Meal.user_id == user.id).order_by(Meal.timestamp.desc()).limit(1)
        )
        last_meal = meal_result.scalar_one_or_none()
        if last_meal:
            mins_ago = int((datetime.now(timezone.utc) - last_meal.timestamp).total_seconds() / 60)
            lines.append(f"Last meal: {last_meal.description} ({mins_ago} min ago)")

        return "\n".join(lines) if lines else "No data yet."

    async def _get_focus_state(self, db: AsyncSession, user: User) -> str:
        """Get today's focus state."""
        today = datetime.now(timezone.utc).date()
        result = await db.execute(
            select(DailyFocus).where(DailyFocus.user_id == user.id, DailyFocus.date == today)
        )
        focus = result.scalar_one_or_none()
        if not focus:
            return "No focus session started today."

        lines = []
        if focus.one_thing:
            status = "DONE" if focus.one_thing_done_at else "in progress"
            lines.append(f"ONE thing: {focus.one_thing} ({status})")
        if focus.daily_win:
            lines.append(f"Today's win: {focus.daily_win}")
        if focus.streak_count and focus.streak_count > 1:
            lines.append(f"Streak: {focus.streak_count} days")

        return "\n".join(lines) if lines else "Focus session exists but no ONE thing set."

    async def _get_todo_list(self, db: AsyncSession, user: User) -> str:
        """Get active todo items."""
        today = datetime.now(timezone.utc).date()
        result = await db.execute(
            select(TodoItem)
            .where(
                TodoItem.user_id == user.id,
                TodoItem.created_for_date == today,
                TodoItem.completed == False,  # noqa: E712
            )
            .order_by(TodoItem.priority)
        )
        todos = result.scalars().all()

        if not todos:
            return "No active to-do items for today."

        lines = []
        for i, todo in enumerate(todos, 1):
            lines.append(f"{i}. {todo.task}")
        return "\n".join(lines)


general_agent = GeneralAgent()
