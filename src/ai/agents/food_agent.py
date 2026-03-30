"""Food agent — handles food photo analysis, meal logging, and nutrition queries."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.engine.memory_manager import memory_manager
from src.ingestion.food import process_food_photo, process_food_text
from src.messaging.telegram_client import telegram_client
from src.models.food_response import FoodResponse
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.tasks.meal_followup import check_post_meal_glucose

logger = logging.getLogger(__name__)


class FoodAgent:
    """Handles food analysis, meal persistence, and follow-up scheduling."""

    async def handle_photo(
        self, photo_bytes: bytes, caption: str, user: User, chat_id: int, db: AsyncSession
    ) -> str:
        """Analyze a food photo, save meal, schedule follow-up."""
        food_history, current_glucose = await self._get_food_context(db, user)

        analysis = await process_food_photo(
            photo_bytes=photo_bytes,
            user=user,
            caption=caption,
            current_glucose=current_glucose,
            food_history=food_history,
        )

        meal = await self._save_meal(db, user, analysis, caption)
        self._schedule_followup(meal, user)

        return self._format_response(analysis, current_glucose)

    async def handle_text(
        self, text: str, user: User, chat_id: int, db: AsyncSession
    ) -> str:
        """Analyze food from text description, save meal, schedule follow-up."""
        food_history, current_glucose = await self._get_food_context(db, user)

        analysis = await process_food_text(
            text=text,
            user=user,
            current_glucose=current_glucose,
            food_history=food_history,
        )

        description = ", ".join(item.name for item in analysis.items) if analysis.items else text
        meal = await self._save_meal(db, user, analysis, description)
        self._schedule_followup(meal, user)

        # Update memory with this food logging
        for item in analysis.items:
            await memory_manager.update(
                db, str(user.id),
                key=f"last_ate_{item.name.lower()}",
                value=f"at {datetime.now(timezone.utc).strftime('%I:%M %p')}, {item.calories} cal, {item.carbs_g}g carbs",
                category="food",
            )

        return self._format_response(analysis, current_glucose)

    async def _get_food_context(self, db: AsyncSession, user: User):
        """Fetch food history and current glucose."""
        fr_result = await db.execute(
            select(FoodResponse).where(FoodResponse.user_id == user.id)
        )
        food_history = [
            {
                "food_name": fr.food_name,
                "avg_peak_glucose": fr.avg_peak_glucose,
                "crash_probability": fr.crash_probability,
                "sample_count": fr.sample_count,
            }
            for fr in fr_result.scalars().all()
        ]

        glucose_result = await db.execute(
            select(GlucoseReading.glucose_mmol)
            .where(GlucoseReading.user_id == user.id)
            .order_by(GlucoseReading.timestamp.desc())
            .limit(1)
        )
        current_glucose = glucose_result.scalar_one_or_none()

        return food_history, current_glucose

    async def _save_meal(self, db, user, analysis, description):
        """Persist meal and return the record."""
        hour = datetime.now().hour
        if 5 <= hour < 11:
            meal_type = "breakfast"
        elif 11 <= hour < 15:
            meal_type = "lunch"
        elif 15 <= hour < 18:
            meal_type = "snack"
        else:
            meal_type = "dinner"

        meal = Meal(
            user_id=user.id,
            timestamp=datetime.now(timezone.utc),
            meal_type=meal_type,
            description=description,
            items=[
                {
                    "name": i.name, "portion_g": i.portion_g, "calories": i.calories,
                    "protein_g": i.protein_g, "carbs_g": i.carbs_g, "fat_g": i.fat_g,
                    "fiber_g": i.fiber_g, "gi_score": i.gi_score,
                }
                for i in analysis.items
            ],
            total_calories=analysis.total_calories,
            total_protein_g=analysis.total_protein_g,
            total_carbs_g=analysis.total_carbs_g,
            total_fat_g=analysis.total_fat_g,
            total_fiber_g=analysis.total_fiber_g,
            avg_gi_score=analysis.items[0].gi_score if analysis.items else None,
            predicted_spike=analysis.predicted_spike,
        )
        db.add(meal)
        await db.commit()
        await db.refresh(meal)
        logger.info("Meal %s saved for user %s", meal.id, user.id)
        return meal

    def _schedule_followup(self, meal, user):
        """Schedule 60-min glucose follow-up."""
        check_post_meal_glucose.apply_async(
            args=[meal.id, str(user.id)],
            countdown=3600,
        )
        logger.info("Follow-up scheduled for meal %s in 60 min", meal.id)

    def _format_response(self, analysis, current_glucose) -> str:
        """Format meal analysis into Telegram message."""
        items_text = ", ".join(item.name for item in analysis.items) if analysis.items else "your meal"

        lines = [
            f"<b>Meal logged:</b> {items_text}",
            f"📊 ~{analysis.total_calories} cal | "
            f"{analysis.total_protein_g:.0f}g protein | {analysis.total_carbs_g:.0f}g carbs | "
            f"{analysis.total_fat_g:.0f}g fat",
        ]

        if current_glucose:
            lines.append(f"📈 Current glucose: {current_glucose:.1f} mmol/L")

        if analysis.predicted_spike > 2.0:
            lines.append(f"⚠️ Predicted spike: +{analysis.predicted_spike:.1f} mmol/L")

        if analysis.crash_risk in ("medium", "high"):
            lines.append(f"⚡ Crash risk: {analysis.crash_risk}")

        if analysis.recommendation:
            lines.append(f"\n💡 {analysis.recommendation}")

        lines.append("\n⏱ I'll check your glucose in 60 min and report back.")

        return "\n".join(lines)


food_agent = FoodAgent()
