"""Scheduled glucose polling from LibreLinkUp."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from src.ai.pattern_detector import pattern_detector
from src.engine.alert_engine import HealthContext, alert_engine
from src.ingestion.libre import libre_client
from src.messaging.dispatcher import dispatcher
from src.models.base import async_session
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.user import User
from src.tasks import celery_app
from src.utils.glucose_math import trend_arrow_to_label

logger = logging.getLogger(__name__)


@celery_app.task(name="src.tasks.libre_poller.poll_all_users_glucose")
def poll_all_users_glucose():
    """Poll glucose for all active users (called by Celery Beat)."""
    asyncio.get_event_loop().run_until_complete(_poll_all())


async def _poll_all():
    async with async_session() as db:
        result = await db.execute(
            select(User).where(User.libre_patient_id.isnot(None))
        )
        users = result.scalars().all()

        for user in users:
            try:
                await _poll_user_glucose(db, user)
            except Exception:
                logger.exception("Error polling glucose for user %s", user.id)


async def _poll_user_glucose(db, user: User):
    """Poll and process glucose for a single user."""
    reading_data = await libre_client.get_latest_for_user(user)
    if not reading_data:
        return

    # Save reading
    reading = GlucoseReading(
        user_id=user.id,
        timestamp=datetime.fromisoformat(reading_data["timestamp"]),
        glucose_mmol=reading_data["glucose_mmol"],
        trend_arrow=reading_data.get("trend_arrow"),
        is_high=reading_data.get("is_high", False),
        is_low=reading_data.get("is_low", False),
    )
    db.add(reading)
    await db.commit()

    # Get recent readings for rate of change
    recent_result = await db.execute(
        select(GlucoseReading)
        .where(GlucoseReading.user_id == user.id)
        .order_by(GlucoseReading.timestamp.desc())
        .limit(6)
    )
    recent = recent_result.scalars().all()
    recent_dicts = [
        {"timestamp": r.timestamp, "glucose_mmol": r.glucose_mmol}
        for r in reversed(recent)
    ]
    rate_of_change = pattern_detector.calculate_rate_of_change(recent_dicts)

    # Get last meal info
    meal_result = await db.execute(
        select(Meal)
        .where(Meal.user_id == user.id)
        .order_by(Meal.timestamp.desc())
        .limit(1)
    )
    last_meal = meal_result.scalar_one_or_none()
    time_since_meal = None
    last_meal_carbs = None
    if last_meal:
        time_since_meal = (datetime.utcnow() - last_meal.timestamp).total_seconds() / 3600
        last_meal_carbs = last_meal.total_carbs_g

    # Build context and evaluate rules
    ctx = HealthContext(
        current_glucose=reading_data["glucose_mmol"],
        glucose_trend=trend_arrow_to_label(reading_data.get("trend_arrow")),
        rate_of_change=rate_of_change,
        time_since_last_meal_hours=time_since_meal,
        last_meal_carbs_g=last_meal_carbs,
    )

    alerts = alert_engine.evaluate(ctx)

    # Send alerts
    for alert in alerts:
        await dispatcher.send(
            user=user,
            message=alert.message,
            priority=alert.priority,
            glucose_value=alert.glucose_value,
        )
