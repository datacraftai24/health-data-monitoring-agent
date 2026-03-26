"""Conversational AI using Google Gemini for natural chat interactions."""

import logging

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

CONVERSATION_SYSTEM_PROMPT = """You are MetaboCoach, a personal metabolic health AI assistant.
You help the user manage their glucose levels, nutrition, and activity for optimal health.

User profile:
{user_context}

Current health state:
{health_state}

Guidelines:
- Be warm, supportive, and concise
- Use data to back up recommendations
- Reference the user's personal patterns when available
- Keep responses under 200 words for messaging platforms
- Use simple emojis sparingly for readability
- If the user logs food via text, extract the food items and estimate nutrition
- Always consider the user's glucose state when making recommendations
- Warn about known spike foods based on their history
- Encourage protein intake and post-meal walks
- Be proactive about crash prevention

If the user is logging food (mentions eating, having, or describing a meal), respond with:
1. Quick analysis of the food
2. Estimated calories/macros
3. Any glucose-related warnings based on their history
4. A practical recommendation

For general questions, provide helpful, data-driven answers about their health trends."""


class ConversationEngine:
    """Handle natural language conversations with users via Gemini."""

    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def respond(
        self,
        user_message: str,
        user_context: dict | None = None,
        health_state: dict | None = None,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Generate a conversational response to the user's message."""
        context = user_context or {}
        state = health_state or {}

        system = CONVERSATION_SYSTEM_PROMPT.format(
            user_context=self._format_user_context(context),
            health_state=self._format_health_state(state),
        )

        contents = []
        if conversation_history:
            for msg in conversation_history[-10:]:
                contents.append(
                    types.Content(
                        role=msg["role"],
                        parts=[types.Part.from_text(text=msg["content"])],
                    )
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.7,
                max_output_tokens=500,
            ),
        )

        return response.text

    def _format_user_context(self, ctx: dict) -> str:
        if not ctx:
            return "No profile data available yet."
        lines = []
        if ctx.get("name"):
            lines.append(f"Name: {ctx['name']}")
        if ctx.get("hba1c"):
            lines.append(f"HbA1c: {ctx['hba1c']}%")
        if ctx.get("weight_kg"):
            lines.append(f"Weight: {ctx['weight_kg']} kg")
        if ctx.get("daily_calorie_target"):
            lines.append(f"Calorie target: {ctx['daily_calorie_target']} cal/day")
        if ctx.get("daily_protein_target_g"):
            lines.append(f"Protein target: {ctx['daily_protein_target_g']}g/day")
        return "\n".join(lines) if lines else "No profile data available yet."

    def _format_health_state(self, state: dict) -> str:
        if not state:
            return "No current health data available."
        lines = []
        if state.get("current_glucose"):
            lines.append(f"Current glucose: {state['current_glucose']} mmol/L")
        if state.get("trend"):
            lines.append(f"Glucose trend: {state['trend']}")
        if state.get("last_meal"):
            lines.append(f"Last meal: {state['last_meal']}")
        if state.get("time_since_meal"):
            lines.append(f"Time since last meal: {state['time_since_meal']}")
        if state.get("steps_today"):
            lines.append(f"Steps today: {state['steps_today']}")
        if state.get("calories_today"):
            lines.append(f"Calories today: {state['calories_today']}")
        if state.get("protein_today"):
            lines.append(f"Protein today: {state['protein_today']}g")
        return "\n".join(lines) if lines else "No current health data available."


conversation_engine = ConversationEngine()
