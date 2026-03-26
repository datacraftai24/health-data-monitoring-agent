"""Periodic pattern analysis — recalculates metabolic profiles."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.pattern_detector import pattern_detector
from src.engine.metabolic_profile import MetabolicProfile
from src.models.base import async_session
from src.models.glucose import GlucoseReading
from src.models.food_response import FoodResponse
from src.models.meal import Meal
from src.models.user import User
from src.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.tasks.pattern_analysis.run_pattern_analysis")
def run_pattern_analysis():
    """Recalculate metabolic profiles for all users (nightly at 3 AM)."""
    asyncio.get_event_loop().run_until_complete(_analyze_all())


async def _analyze_all():
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for user in users:
            try:
                await _analyze_user_patterns(db, user)
            except Exception:
                logger.exception("Error analyzing patterns for user %s", user.id)


async def _analyze_user_patterns(db: AsyncSession, user: User):
    """Recalculate metabolic profile for a user."""
    # Get all glucose readings from last 14 days
    since = datetime.utcnow() - timedelta(days=14)

    readings_result = await db.execute(
        select(GlucoseReading)
        .where(GlucoseReading.user_id == user.id, GlucoseReading.timestamp >= since)
        .order_by(GlucoseReading.timestamp)
    )
    readings = readings_result.scalars().all()

    if not readings:
        return

    reading_dicts = [
        {
            "timestamp": r.timestamp,
            "glucose_mmol": r.glucose_mmol,
            "trend_arrow": r.trend_arrow,
        }
        for r in readings
    ]

    # Run pattern detection
    analysis = pattern_detector.analyze_readings(reading_dicts)

    # Count unique days of data
    unique_days = len(set(r.timestamp.date() for r in readings))

    # Load or create metabolic profile
    existing = MetabolicProfile.from_dict(user.metabolic_profile or {})
    existing.user_id = str(user.id)
    existing.days_of_data = unique_days
    existing.avg_fasting_glucose = analysis.avg_fasting_glucose
    existing.time_in_range_pct = analysis.time_in_range_pct
    existing.crash_frequency_per_day = analysis.crash_count / max(unique_days, 1)
    existing.update_phase()
    existing.last_updated = datetime.utcnow()

    # Update crash risk by hour
    for pattern in analysis.patterns:
        if pattern.pattern_type == "crash" and pattern.start_time:
            hour = pattern.start_time.hour
            current = existing.crash_risk_by_hour.get(hour, 0)
            existing.crash_risk_by_hour[hour] = min(1.0, current + 0.1)

    # Load food responses from DB
    food_result = await db.execute(
        select(FoodResponse).where(FoodResponse.user_id == user.id)
    )
    food_responses = food_result.scalars().all()
    for fr in food_responses:
        if fr.food_name:
            existing.update_food_response(
                food_name=fr.food_name,
                peak_glucose=fr.avg_peak_glucose or 0,
                time_to_peak_min=fr.avg_time_to_peak_min or 45,
                crashed=fr.crash_probability is not None and fr.crash_probability > 0.5,
            )

    # Save updated profile
    user.metabolic_profile = existing.to_dict()
    await db.commit()

    logger.info(
        "Updated metabolic profile for user %s (phase=%s, days=%d)",
        user.id, existing.phase, existing.days_of_data,
    )
