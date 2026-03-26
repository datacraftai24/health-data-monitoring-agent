"""Daily summary report generation task."""

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.recommender import recommender
from src.engine.calorie_tracker import calorie_tracker
from src.messaging.dispatcher import dispatcher
from src.models.base import async_session
from src.models.daily_summary import DailySummary
from src.models.glucose import GlucoseReading
from src.models.activity import ActivityData
from src.models.user import User
from src.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.tasks.daily_summary.generate_daily_summaries")
def generate_daily_summaries():
    """Generate and send daily summaries for all users (called by Celery Beat at 9 PM)."""
    asyncio.get_event_loop().run_until_complete(_generate_all())


async def _generate_all():
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for user in users:
            try:
                await _generate_user_summary(db, user)
            except Exception:
                logger.exception("Error generating daily summary for user %s", user.id)


async def _generate_user_summary(db: AsyncSession, user: User):
    """Generate daily summary for a single user."""
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)

    # Glucose stats
    glucose_result = await db.execute(
        select(
            func.avg(GlucoseReading.glucose_mmol),
            func.min(GlucoseReading.glucose_mmol),
            func.max(GlucoseReading.glucose_mmol),
            func.count(GlucoseReading.id),
        ).where(
            GlucoseReading.user_id == user.id,
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp < end,
        )
    )
    g_row = glucose_result.one()
    glucose_avg, glucose_min, glucose_max, glucose_count = g_row

    # Time in range
    if glucose_count and glucose_count > 0:
        in_range_result = await db.execute(
            select(func.count(GlucoseReading.id)).where(
                GlucoseReading.user_id == user.id,
                GlucoseReading.timestamp >= start,
                GlucoseReading.timestamp < end,
                GlucoseReading.glucose_mmol >= user.glucose_target_low,
                GlucoseReading.glucose_mmol <= user.glucose_target_high,
            )
        )
        in_range_count = in_range_result.scalar() or 0
        time_in_range = (in_range_count / glucose_count) * 100
    else:
        time_in_range = 0

    # Crash count
    crash_result = await db.execute(
        select(func.count(GlucoseReading.id)).where(
            GlucoseReading.user_id == user.id,
            GlucoseReading.timestamp >= start,
            GlucoseReading.timestamp < end,
            GlucoseReading.glucose_mmol < user.glucose_low_threshold,
        )
    )
    crash_count = crash_result.scalar() or 0

    # Nutrition
    nutrition = await calorie_tracker.get_daily_totals(db, str(user.id), today)

    # Activity
    activity_result = await db.execute(
        select(ActivityData).where(ActivityData.user_id == user.id, ActivityData.date == today)
    )
    activity = activity_result.scalar_one_or_none()

    # Save summary
    summary = DailySummary(
        user_id=user.id,
        date=today,
        glucose_avg=glucose_avg,
        glucose_min=glucose_min,
        glucose_max=glucose_max,
        time_in_range_pct=time_in_range,
        crash_count=crash_count,
        total_steps=activity.steps if activity else 0,
        total_active_calories=activity.active_calories if activity else 0,
        total_calories=nutrition.total_calories,
        total_protein_g=nutrition.total_protein_g,
        total_carbs_g=nutrition.total_carbs_g,
        total_fat_g=nutrition.total_fat_g,
        meals_logged=nutrition.meals_logged,
    )
    db.add(summary)
    await db.commit()

    # Generate insights with Gemini
    daily_data = {
        "glucose_avg": glucose_avg,
        "glucose_range": f"{glucose_min}-{glucose_max}",
        "time_in_range": f"{time_in_range:.0f}%",
        "crashes": crash_count,
        "calories": nutrition.total_calories,
        "protein": nutrition.total_protein_g,
        "steps": activity.steps if activity else 0,
    }
    insights = await recommender.get_daily_insights(daily_data)

    # Format and send report
    report = _format_daily_report(
        today, glucose_avg, glucose_min, glucose_max, time_in_range,
        crash_count, nutrition, activity, insights, user,
    )
    await dispatcher.send(user=user, message=report, priority="low", force=True)


def _format_daily_report(
    today, glucose_avg, glucose_min, glucose_max, time_in_range,
    crash_count, nutrition, activity, insights, user,
) -> str:
    lines = [
        f"📊 Daily Report — {today.strftime('%B %d, %Y')}",
        "",
        "🩸 Glucose",
    ]
    if glucose_avg:
        lines.append(f"   Range: {glucose_min:.1f} — {glucose_max:.1f} mmol/L")
        lines.append(f"   Time in range: {time_in_range:.0f}%")
        lines.append(f"   Crashes: {crash_count}")
        lines.append(f"   Avg: {glucose_avg:.1f} mmol/L")
    else:
        lines.append("   No glucose data today")

    lines.extend([
        "",
        "🍽️ Nutrition",
        f"   Calories: {nutrition.total_calories} / {user.daily_calorie_target or '?'} target",
        f"   Protein: {nutrition.total_protein_g:.0f}g / {user.daily_protein_target_g or '?'}g target",
        f"   Carbs: {nutrition.total_carbs_g:.0f}g | Fat: {nutrition.total_fat_g:.0f}g",
        "",
        "🚶 Activity",
        f"   Steps: {activity.steps if activity else 0:,}",
    ])

    if insights:
        lines.extend(["", "📈 Insights"])
        for insight in insights:
            lines.append(f"   • {insight}")

    return "\n".join(lines)
