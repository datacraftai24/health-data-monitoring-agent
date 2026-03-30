"""Intent router — classifies every Telegram message using Gemini before routing to agents."""

import logging

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

INTENT_PROMPT = """Classify this Telegram message into exactly ONE intent. Reply with ONLY the intent label.

Intents:
- food_log: user is describing food they ate/are eating, or asking to analyze food
- glucose_check: user wants current glucose, glucose trend, or to monitor glucose
- focus_command: user is using a focus system command (/morning, /onething, /focus, /stop, /park, /phone, /win, /1win, /todo, /todone, /todolist, /tonight, /tune, /ideas, /done, /status)
- health_status: user wants overall health snapshot, calories, protein progress
- general: everything else (questions, conversation, greetings)

Message: {message}
Has photo: {has_photo}

Intent:"""


class IntentRouter:
    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

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


intent_router = IntentRouter()
