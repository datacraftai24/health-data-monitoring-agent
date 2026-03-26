"""Food photo and text analysis using Google Gemini Vision."""

import json
import logging

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

FOOD_ANALYSIS_SYSTEM_PROMPT = """You are a nutritionist AI. Analyze the food provided.

User context:
- Pre-diabetic (HbA1c {hba1c}%)
- Reactive hypoglycemia pattern
- Weight loss goal (daily calorie target: {calorie_target} cal, protein target: {protein_target}g)
- South Asian diet

For each food item identify:
1. Food name and preparation method
2. Estimated portion size (grams)
3. Calories
4. Macros (protein, carbs, fat, fiber in grams)
5. Glycemic Index (low/medium/high)
6. Estimated Glycemic Load

Then provide:
- Total meal calories and macros
- Predicted glucose spike (mmol/L above baseline)
- Expected spike timing (minutes after eating)
- Risk of post-meal crash (low/medium/high) based on user's pattern
- Specific recommendation for this meal

{food_history_context}

Respond in JSON only with this structure:
{{
  "items": [
    {{
      "name": "food name",
      "portion_g": 100,
      "calories": 200,
      "protein_g": 10,
      "carbs_g": 30,
      "fat_g": 8,
      "fiber_g": 3,
      "gi_score": "medium",
      "gl_load": 15
    }}
  ],
  "total_calories": 500,
  "total_protein": 25,
  "total_carbs": 60,
  "total_fat": 20,
  "total_fiber": 8,
  "predicted_spike": 2.5,
  "spike_timing_min": 45,
  "crash_risk": "medium",
  "recommendation": "Consider adding more protein to reduce the spike."
}}"""


class FoodAnalyzer:
    """Analyze food photos and text descriptions using Gemini."""

    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    def _build_system_prompt(
        self,
        user_profile: dict | None = None,
        current_glucose: float | None = None,
        food_history: list[dict] | None = None,
    ) -> str:
        profile = user_profile or {}
        history_context = ""
        if food_history:
            history_lines = []
            for fh in food_history[:10]:
                history_lines.append(
                    f"- {fh['food_name']}: peak {fh.get('avg_peak_glucose', '?')} mmol/L, "
                    f"crash prob {fh.get('crash_probability', 0):.0%}"
                )
            history_context = (
                "Known food responses for this user:\n" + "\n".join(history_lines)
            )

        glucose_note = ""
        if current_glucose is not None:
            glucose_note = f"\nCurrent glucose: {current_glucose} mmol/L"

        return FOOD_ANALYSIS_SYSTEM_PROMPT.format(
            hba1c=profile.get("hba1c", "6.0"),
            calorie_target=profile.get("daily_calorie_target", 1800),
            protein_target=profile.get("daily_protein_target_g", 120),
            food_history_context=history_context + glucose_note,
        )

    async def analyze_photo(
        self,
        photo_bytes: bytes,
        caption: str = "",
        user_profile: dict | None = None,
        current_glucose: float | None = None,
        food_history: list[dict] | None = None,
    ) -> dict:
        """Analyze a food photo with Gemini Vision."""
        system_prompt = self._build_system_prompt(user_profile, current_glucose, food_history)

        user_message = "Analyze this food photo."
        if caption:
            user_message += f" Additional context: {caption}"

        response = self.client.models.generate_content(
            model=settings.gemini_vision_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=photo_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=user_message),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )

        return self._parse_response(response.text)

    async def analyze_text(
        self,
        text: str,
        user_profile: dict | None = None,
        current_glucose: float | None = None,
        food_history: list[dict] | None = None,
    ) -> dict:
        """Analyze a text-based food description with Gemini."""
        system_prompt = self._build_system_prompt(user_profile, current_glucose, food_history)

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=f"Analyze this meal: {text}",
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )

        return self._parse_response(response.text)

    def _parse_response(self, text: str) -> dict:
        """Parse JSON response from Gemini, handling markdown code blocks."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("Failed to parse Gemini food analysis response: %s", text[:200])
            return {
                "items": [],
                "total_calories": 0,
                "total_protein": 0,
                "total_carbs": 0,
                "total_fat": 0,
                "total_fiber": 0,
                "predicted_spike": 0,
                "crash_risk": "unknown",
                "recommendation": "Unable to analyze — please try again.",
            }


food_analyzer = FoodAnalyzer()
