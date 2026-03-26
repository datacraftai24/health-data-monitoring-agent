"""Garmin Push API webhook handler."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.garmin import garmin_client
from src.models.activity import ActivityData, Workout
from src.models.base import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/garmin/daily")
async def garmin_daily_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Garmin daily summary push notifications."""
    payload = await request.json()
    logger.info("Garmin daily summary received")

    try:
        summary = garmin_client.parse_daily_summary(payload)

        # TODO: Map Garmin user token to our user_id
        # For now, extract user_id from payload metadata
        user_access_token = payload.get("userAccessToken", "")

        activity = ActivityData(
            user_id=user_access_token,  # Will be mapped via Garmin OAuth token
            date=summary.date,
            steps=summary.steps,
            total_calories=summary.total_calories,
            active_calories=summary.active_calories,
            distance_km=summary.distance_km,
            active_minutes=summary.active_minutes,
            heart_rate_avg=summary.heart_rate_avg,
            heart_rate_resting=summary.heart_rate_resting,
            stress_avg=summary.stress_avg,
            sleep_duration_min=summary.sleep_duration_min,
            sleep_score=summary.sleep_score,
        )
        db.add(activity)
        await db.commit()
    except Exception:
        logger.exception("Error processing Garmin daily summary")

    return {"ok": True}


@router.post("/garmin/activity")
async def garmin_activity_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Garmin activity/workout push notifications."""
    payload = await request.json()
    logger.info("Garmin activity received")

    try:
        activities = garmin_client.parse_activity(payload)
        user_access_token = payload.get("userAccessToken", "")

        for act in activities:
            workout = Workout(
                user_id=user_access_token,
                start_time=act.start_time,
                end_time=act.end_time,
                activity_type=act.activity_type,
                duration_min=act.duration_min,
                calories_burned=act.calories_burned,
                avg_heart_rate=act.avg_heart_rate,
            )
            db.add(workout)

        await db.commit()
    except Exception:
        logger.exception("Error processing Garmin activity")

    return {"ok": True}
