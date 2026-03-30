"""Personalized recommendation engine using Gemini."""

import logging

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

RECOMMENDATION_SYSTEM_PROMPT = """You are MetaboCoach's recommendation engine. Generate specific,
actionable health recommendations based on the user's metabolic data.

Be concise (1-2 sentences max per recommendation). Use the user's actual data and patterns.
Focus on practical, immediate actions they can take.

Format each recommendation as a short, friendly message suitable for WhatsApp/Telegram."""


class Recommender:
    """Generate personalized recommendations based on metabolic data."""

    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def get_meal_recommendation(
        self,
        meal_analysis: dict,
        current_glucose: float,
        food_history: list[dict] | None = None,
    ) -> str:
        """Get a recommendation for a specific meal."""
        prompt = f"""Based on this meal analysis, provide a brief recommendation:

Meal: {meal_analysis}
Current glucose: {current_glucose} mmol/L
Known food responses: {food_history or 'None yet'}

Give 1-2 specific, actionable tips. Keep it under 50 words."""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RECOMMENDATION_SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=150,
            ),
        )
        return response.text

    async def get_daily_insights(self, daily_data: dict) -> list[str]:
        """Generate insights for the daily summary report."""
        meals_section = ""
        if daily_data.get("meals_logged"):
            meals_lines = []
            for m in daily_data["meals_logged"]:
                line = f"- {m.get('time')}: {m.get('description')} ({m.get('calories', '?')} cal)"
                if m.get("actual_peak"):
                    line += f" → peaked at {m['actual_peak']:.1f} mmol/L"
                    if m.get("predicted_spike"):
                        line += f" (predicted +{m['predicted_spike']:.1f})"
                meals_section = "\n".join(meals_lines)

        known_foods = daily_data.get("known_food_responses", {})
        phase = daily_data.get("metabolic_phase", "observation")

        prompt = f"""Based on today's health data, generate 2-3 specific, personalized insights:

Overall: glucose avg {daily_data.get('glucose_avg')}, range {daily_data.get('glucose_range')}, \
time in range {daily_data.get('time_in_range')}, crashes: {daily_data.get('crashes')}, \
calories: {daily_data.get('calories')}, protein: {daily_data.get('protein')}g, \
steps: {daily_data.get('steps')}

Meals today:
{meals_section or 'No meals logged'}

Metabolic learning phase: {phase}
Known food patterns: {known_foods or 'None yet'}

Requirements:
- Reference specific meals and their actual glucose impact
- Compare predicted vs actual spikes where data exists
- Suggest timing or portion adjustments based on patterns
- Keep each insight under 40 words
Format as a numbered list."""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RECOMMENDATION_SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=300,
            ),
        )
        lines = [
            line.strip().lstrip("0123456789.-) ")
            for line in response.text.strip().split("\n")
            if line.strip()
        ]
        return [line for line in lines if line]

    async def get_weekly_recommendations(self, weekly_data: dict) -> str:
        """Generate recommendations for the weekly report."""
        prompt = f"""Based on this week's health data, provide 3 recommendations for next week:

{weekly_data}

Focus on:
1. One nutrition improvement
2. One activity/timing improvement
3. One glucose management tip

Keep each recommendation under 30 words."""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=RECOMMENDATION_SYSTEM_PROMPT,
                temperature=0.5,
                max_output_tokens=300,
            ),
        )
        return response.text


recommender = Recommender()
