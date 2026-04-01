"""Intent router — classifies every Telegram message using Gemini before routing to agents.

Also manages pending_input state for context-aware parsing (e.g., after morning activation
asks for ONE thing, the next message should be treated as the ONE thing, not re-classified).
"""

import logging

import redis.asyncio as aioredis
from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

INTENT_PROMPT = """Classify this Telegram message into exactly ONE intent. Reply with ONLY the intent label.

Intents:
- food_log: user is describing food they ate/are eating, or asking to analyze food
- glucose_check: user wants current glucose, glucose trend, or to monitor glucose
- focus_command: user is using a focus/productivity command OR asking about their to-do list, tasks, what they need to do, schedule, morning routine, or daily planning
- health_status: user wants overall health snapshot, calories, protein progress
- general: everything else (questions, conversation, greetings)

IMPORTANT: If the user asks "what's my todo list", "what do I need to do", "my tasks", "what's on my list" — that is focus_command, NOT general.

Message: {message}
Has photo: {has_photo}

Intent:"""


class IntentRouter:
    def __init__(self):
        self._client: genai.Client | None = None
        self._redis: aioredis.Redis | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    @property
    def redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url)
        return self._redis

    async def classify(self, message: str, has_photo: bool = False) -> str:
        """Classify a message intent. Returns intent label string."""
        # Photos always go to food
        if has_photo:
            return "food_log"

        # Slash commands route directly
        cmd = message.strip().lower()
        if cmd.startswith("/"):
            command_map = {
                "/start": "general", "/help": "general",
                "/glucose": "glucose_check",
                "/status": "focus_command", "/calories": "health_status",
                "/morning": "focus_command", "/onething": "focus_command",
                "/focus": "focus_command", "/stop": "focus_command",
                "/park": "focus_command", "/phone": "focus_command",
                "/win": "focus_command", "/1win": "focus_command",
                "/done": "focus_command", "/log": "food_log",
                "/todo": "focus_command", "/todone": "focus_command",
                "/todolist": "focus_command", "/tonight": "focus_command",
                "/tune": "focus_command", "/tuneapply": "focus_command",
                "/tunereject": "focus_command", "/ideas": "focus_command",
                "/todoclear": "focus_command",
                "/pause": "general",
            }
            for prefix, intent in command_map.items():
                if cmd.startswith(prefix):
                    return intent
            return "general"

        # Keyword shortcuts for common queries that Gemini might misroute
        todo_keywords = ["todo", "to-do", "to do list", "task list", "my tasks",
                         "what do i need", "what's on my list", "my list"]
        if any(kw in cmd for kw in todo_keywords):
            return "focus_command"

        # Use Gemini for natural language classification
        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=INTENT_PROMPT.format(message=message, has_photo=has_photo),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=10,
                ),
            )
            intent = response.text.strip().lower().replace(" ", "_")
            valid = {"food_log", "glucose_check", "focus_command", "health_status", "general"}
            return intent if intent in valid else "general"
        except Exception:
            logger.exception("Intent classification failed, defaulting to general")
            return "general"

    # --- Pending input state management ---

    async def set_pending_input(self, user_id: str, input_type: str, ttl: int = 300):
        """Set what input we're expecting from the user next.

        Args:
            user_id: User ID.
            input_type: What we're expecting, e.g., "awaiting_onething", "awaiting_win".
            ttl: Time to live in seconds (default 5 min).
        """
        await self.redis.set(f"pending_input:{user_id}", input_type, ex=ttl)

    async def get_pending_input(self, user_id: str) -> str | None:
        """Check if we're expecting specific input from this user."""
        result = await self.redis.get(f"pending_input:{user_id}")
        return result.decode() if result else None

    async def clear_pending_input(self, user_id: str):
        """Clear the pending input expectation."""
        await self.redis.delete(f"pending_input:{user_id}")


intent_router = IntentRouter()
