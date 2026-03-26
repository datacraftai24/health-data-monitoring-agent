"""Dashboard API routes for optional web dashboard."""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.models.glucose import GlucoseReading
from src.models.meal import Meal
from src.models.daily_summary import DailySummary

router = APIRouter()


@router.get("/glucose/{user_id}")
async def get_glucose_data(
    user_id: str,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """Get recent glucose readings for a user."""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(GlucoseReading)
        .where(GlucoseReading.user_id == user_id, GlucoseReading.timestamp >= since)
        .order_by(GlucoseReading.timestamp.asc())
    )
    readings = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp.isoformat(),
            "glucose_mmol": r.glucose_mmol,
            "trend_arrow": r.trend_arrow,
        }
        for r in readings
    ]


@router.get("/meals/{user_id}")
async def get_meals(
    user_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """Get recent meals for a user."""
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Meal)
        .where(Meal.user_id == user_id, Meal.timestamp >= since)
        .order_by(Meal.timestamp.desc())
    )
    meals = result.scalars().all()
    return [
        {
            "id": m.id,
            "timestamp": m.timestamp.isoformat(),
            "meal_type": m.meal_type,
            "description": m.description,
            "total_calories": m.total_calories,
            "total_protein_g": m.total_protein_g,
            "total_carbs_g": m.total_carbs_g,
            "items": m.items,
        }
        for m in meals
    ]


@router.get("/summary/{user_id}")
async def get_daily_summary(
    user_id: str,
    target_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get daily summary for a user."""
    target = target_date or date.today()
    result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == user_id, DailySummary.date == target
        )
    )
    summary = result.scalar_one_or_none()
    if not summary:
        return {"message": "No summary available for this date"}
    return {
        "date": summary.date.isoformat(),
        "glucose_avg": summary.glucose_avg,
        "glucose_min": summary.glucose_min,
        "glucose_max": summary.glucose_max,
        "time_in_range_pct": summary.time_in_range_pct,
        "crash_count": summary.crash_count,
        "total_steps": summary.total_steps,
        "total_calories": summary.total_calories,
        "total_protein_g": summary.total_protein_g,
        "overall_score": summary.overall_score,
    }
