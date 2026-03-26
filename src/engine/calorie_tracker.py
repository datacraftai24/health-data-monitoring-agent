"""Daily calorie and macro tracking."""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.meal import Meal

logger = logging.getLogger(__name__)


@dataclass
class DailyNutrition:
    date: date
    total_calories: int = 0
    total_protein_g: float = 0
    total_carbs_g: float = 0
    total_fat_g: float = 0
    total_fiber_g: float = 0
    meals_logged: int = 0


class CalorieTracker:
    """Track daily calorie and macro intake."""

    async def get_daily_totals(
        self, db: AsyncSession, user_id: str, target_date: date | None = None
    ) -> DailyNutrition:
        """Get total nutrition for a specific day."""
        target = target_date or date.today()
        start = datetime.combine(target, datetime.min.time())
        end = start + timedelta(days=1)

        result = await db.execute(
            select(
                func.coalesce(func.sum(Meal.total_calories), 0),
                func.coalesce(func.sum(Meal.total_protein_g), 0),
                func.coalesce(func.sum(Meal.total_carbs_g), 0),
                func.coalesce(func.sum(Meal.total_fat_g), 0),
                func.coalesce(func.sum(Meal.total_fiber_g), 0),
                func.count(Meal.id),
            ).where(
                Meal.user_id == user_id,
                Meal.timestamp >= start,
                Meal.timestamp < end,
            )
        )
        row = result.one()

        return DailyNutrition(
            date=target,
            total_calories=int(row[0]),
            total_protein_g=float(row[1]),
            total_carbs_g=float(row[2]),
            total_fat_g=float(row[3]),
            total_fiber_g=float(row[4]),
            meals_logged=int(row[5]),
        )

    async def get_remaining_budget(
        self,
        db: AsyncSession,
        user_id: str,
        calorie_target: int,
        protein_target_g: int,
    ) -> dict:
        """Get remaining calorie and protein budget for today."""
        today = await self.get_daily_totals(db, user_id)
        return {
            "calories_consumed": today.total_calories,
            "calories_remaining": max(0, calorie_target - today.total_calories),
            "protein_consumed_g": today.total_protein_g,
            "protein_remaining_g": max(0, protein_target_g - today.total_protein_g),
            "meals_logged": today.meals_logged,
        }


calorie_tracker = CalorieTracker()
