"""Post-meal glucose follow-up — checks glucose response 60 min after a meal."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.messaging.telegram_client import telegram_client
from src.models.base import async_session
from src.models.food_response import FoodResponse
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.tasks.meal_followup.check_post_meal_glucose")
def check_post_meal_glucose(meal_id: int, user_id: str):
    """Check glucose response after a meal (called 60 min post-meal via countdown)."""
    asyncio.get_event_loop().run_until_complete(_check_meal(meal_id, user_id))


async def _check_meal(meal_id: int, user_id: str):
    async with async_session() as db:
        meal = await db.get(Meal, meal_id)
        if not meal:
            logger.warning("Meal %s not found for follow-up", meal_id)
            return

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            logger.warning("User %s not found for meal follow-up", user_id)
            return

        # Query glucose readings 15–90 min after meal
        window_start = meal.timestamp + timedelta(minutes=15)
        window_end = meal.timestamp + timedelta(minutes=90)

        readings_result = await db.execute(
            select(GlucoseReading)
            .where(
                GlucoseReading.user_id == user_id,
                GlucoseReading.timestamp >= window_start,
                GlucoseReading.timestamp <= window_end,
            )
            .order_by(GlucoseReading.timestamp)
        )
        readings = readings_result.scalars().all()

        if not readings:
            if user.telegram_chat_id:
                await telegram_client.send_message(
                    user.telegram_chat_id,
                    f"No glucose data available for your meal ({meal.description or 'logged meal'}). "
                    "Sensor may have been out of range.",
                )
            return

        # Find peak glucose
        peak_reading = max(readings, key=lambda r: r.glucose_mmol)
        peak_glucose = peak_reading.glucose_mmol
        time_to_peak_min = int(
            (peak_reading.timestamp - meal.timestamp).total_seconds() / 60
        )

        # Update meal with actual peak
        meal.actual_peak = peak_glucose
        meal.actual_peak_time = peak_reading.timestamp

        # Check for crash (glucose < 4.5 within 60–150 min after meal)
        crash_window_start = meal.timestamp + timedelta(minutes=60)
        crash_window_end = meal.timestamp + timedelta(minutes=150)
        crash_result = await db.execute(
            select(GlucoseReading)
            .where(
                GlucoseReading.user_id == user_id,
                GlucoseReading.timestamp >= crash_window_start,
                GlucoseReading.timestamp <= crash_window_end,
                GlucoseReading.glucose_mmol < 4.5,
            )
            .limit(1)
        )
        crashed = crash_result.scalar_one_or_none() is not None

        # Update FoodResponse for each food item
        items = meal.items or []
        for item in items:
            food_name = item.get("name", "").lower().strip()
            if not food_name:
                continue

            fr_result = await db.execute(
                select(FoodResponse).where(
                    FoodResponse.user_id == user_id,
                    FoodResponse.food_name == food_name,
                )
            )
            fr = fr_result.scalar_one_or_none()

            if fr:
                # Running average update
                n = fr.sample_count or 0
                fr.avg_peak_glucose = (
                    (fr.avg_peak_glucose or 0) * n + peak_glucose
                ) / (n + 1)
                fr.avg_time_to_peak_min = (
                    (fr.avg_time_to_peak_min or 0) * n + time_to_peak_min
                ) // (n + 1)
                if crashed:
                    fr.crash_probability = (
                        (fr.crash_probability or 0) * n + 1.0
                    ) / (n + 1)
                else:
                    fr.crash_probability = (
                        (fr.crash_probability or 0) * n
                    ) / (n + 1)
                fr.sample_count = n + 1
                fr.last_eaten = datetime.now(timezone.utc)
            else:
                fr = FoodResponse(
                    user_id=user_id,
                    food_name=food_name,
                    food_category=item.get("gi_score", "medium"),
                    avg_peak_glucose=peak_glucose,
                    avg_time_to_peak_min=time_to_peak_min,
                    crash_probability=1.0 if crashed else 0.0,
                    sample_count=1,
                    last_eaten=datetime.now(timezone.utc),
                )
                db.add(fr)

        await db.commit()

        # Send follow-up message via Telegram
        if user.telegram_chat_id:
            desc = meal.description or "your meal"
            lines = [
                f"<b>Glucose after {desc}:</b>",
                f"  Peak: <b>{peak_glucose:.1f} mmol/L</b> at {time_to_peak_min} min",
            ]

            if meal.predicted_spike:
                diff = peak_glucose - (meal.predicted_spike + 5.0)  # base + spike
                if abs(diff) > 0.5:
                    indicator = "higher" if diff > 0 else "lower"
                    lines.append(
                        f"  (Predicted +{meal.predicted_spike:.1f}, "
                        f"actual was {abs(diff):.1f} {indicator} than expected)"
                    )

            if crashed:
                lines.append("  ⚡ Crash detected — consider pairing with protein next time")

            await telegram_client.send_message(
                user.telegram_chat_id, "\n".join(lines)
            )

        logger.info(
            "Meal follow-up complete: meal=%s peak=%.1f at %d min crashed=%s",
            meal_id, peak_glucose, time_to_peak_min, crashed,
        )
