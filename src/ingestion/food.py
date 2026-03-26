"""Food photo and text processing — delegates to Gemini Vision for analysis."""

import logging
from dataclasses import dataclass, field

from src.ai.food_analyzer import food_analyzer
from src.models.user import User

logger = logging.getLogger(__name__)


@dataclass
class FoodItem:
    name: str
    portion_g: float = 0
    calories: int = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    gi_score: str = "medium"  # low, medium, high
    gl_load: float = 0


@dataclass
class MealAnalysis:
    items: list[FoodItem] = field(default_factory=list)
    total_calories: int = 0
    total_protein_g: float = 0
    total_carbs_g: float = 0
    total_fat_g: float = 0
    total_fiber_g: float = 0
    predicted_spike: float = 0.0
    spike_timing_min: int = 0
    crash_risk: str = "low"
    recommendation: str = ""


async def process_food_photo(
    photo_bytes: bytes,
    user: User,
    caption: str = "",
    current_glucose: float | None = None,
    food_history: list[dict] | None = None,
) -> MealAnalysis:
    """Analyze a food photo using Gemini Vision and return structured meal data."""
    raw = await food_analyzer.analyze_photo(
        photo_bytes=photo_bytes,
        caption=caption,
        user_profile={
            "hba1c": user.hba1c,
            "weight_kg": user.weight_kg,
            "daily_calorie_target": user.daily_calorie_target,
            "daily_protein_target_g": user.daily_protein_target_g,
        },
        current_glucose=current_glucose,
        food_history=food_history,
    )
    return _parse_analysis(raw)


async def process_food_text(
    text: str,
    user: User,
    current_glucose: float | None = None,
    food_history: list[dict] | None = None,
) -> MealAnalysis:
    """Analyze a text-based food description using Gemini."""
    raw = await food_analyzer.analyze_text(
        text=text,
        user_profile={
            "hba1c": user.hba1c,
            "weight_kg": user.weight_kg,
            "daily_calorie_target": user.daily_calorie_target,
            "daily_protein_target_g": user.daily_protein_target_g,
        },
        current_glucose=current_glucose,
        food_history=food_history,
    )
    return _parse_analysis(raw)


def _parse_analysis(raw: dict) -> MealAnalysis:
    """Parse Gemini's JSON response into a MealAnalysis."""
    items = []
    for item_data in raw.get("items", []):
        items.append(
            FoodItem(
                name=item_data.get("name", "Unknown"),
                portion_g=item_data.get("portion_g", 0),
                calories=item_data.get("calories", 0),
                protein_g=item_data.get("protein_g", 0),
                carbs_g=item_data.get("carbs_g", 0),
                fat_g=item_data.get("fat_g", 0),
                fiber_g=item_data.get("fiber_g", 0),
                gi_score=item_data.get("gi_score", "medium"),
                gl_load=item_data.get("gl_load", 0),
            )
        )

    return MealAnalysis(
        items=items,
        total_calories=raw.get("total_calories", 0),
        total_protein_g=raw.get("total_protein", 0),
        total_carbs_g=raw.get("total_carbs", 0),
        total_fat_g=raw.get("total_fat", 0),
        total_fiber_g=raw.get("total_fiber", 0),
        predicted_spike=raw.get("predicted_spike", 0),
        spike_timing_min=raw.get("spike_timing_min", 45),
        crash_risk=raw.get("crash_risk", "low"),
        recommendation=raw.get("recommendation", ""),
    )
