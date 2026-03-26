"""Weekly report generation task."""

import asyncio
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.recommender import recommender
from src.messaging.dispatcher import dispatcher
from src.models.base import async_session
from src.models.daily_summary import DailySummary
from src.models.user import User
from src.tasks import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="src.tasks.weekly_report.generate_weekly_reports")
def generate_weekly_reports():
    """Generate and send weekly reports for all users (Sunday 7 PM)."""
    asyncio.get_event_loop().run_until_complete(_generate_all())


async def _generate_all():
    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for user in users:
            try:
                await _generate_user_weekly(db, user)
            except Exception:
                logger.exception("Error generating weekly report for user %s", user.id)


async def _generate_user_weekly(db: AsyncSession, user: User):
    """Generate weekly report for a single user."""
    today = date.today()
    week_start = today - timedelta(days=7)

    result = await db.execute(
        select(DailySummary)
        .where(
            DailySummary.user_id == user.id,
            DailySummary.date >= week_start,
            DailySummary.date <= today,
        )
        .order_by(DailySummary.date)
    )
    summaries = result.scalars().all()

    if not summaries:
        return

    # Aggregate weekly stats
    avg_glucose = sum(s.glucose_avg or 0 for s in summaries) / len(summaries)
    avg_tir = sum(s.time_in_range_pct or 0 for s in summaries) / len(summaries)
    total_crashes = sum(s.crash_count or 0 for s in summaries)
    avg_calories = sum(s.total_calories or 0 for s in summaries) / len(summaries)
    avg_protein = sum(s.total_protein_g or 0 for s in summaries) / len(summaries)
    avg_steps = sum(s.total_steps or 0 for s in summaries) / len(summaries)

    weekly_data = {
        "avg_glucose": f"{avg_glucose:.1f} mmol/L",
        "time_in_range": f"{avg_tir:.0f}%",
        "total_crashes": total_crashes,
        "avg_daily_calories": int(avg_calories),
        "avg_daily_protein": f"{avg_protein:.0f}g",
        "avg_daily_steps": int(avg_steps),
        "days_tracked": len(summaries),
    }

    recommendations = await recommender.get_weekly_recommendations(weekly_data)

    report = _format_weekly_report(week_start, today, weekly_data, recommendations)
    await dispatcher.send(user=user, message=report, priority="low", force=True)


def _format_weekly_report(week_start, week_end, data, recommendations) -> str:
    lines = [
        f"📊 Weekly Report — {week_start.strftime('%b %d')} to {week_end.strftime('%b %d, %Y')}",
        "",
        "🩸 Glucose",
        f"   Avg: {data['avg_glucose']}",
        f"   Time in range: {data['time_in_range']}",
        f"   Total crashes: {data['total_crashes']}",
        "",
        "🍽️ Nutrition (daily avg)",
        f"   Calories: {data['avg_daily_calories']}",
        f"   Protein: {data['avg_daily_protein']}",
        "",
        "🚶 Activity (daily avg)",
        f"   Steps: {data['avg_daily_steps']:,}",
        "",
        "💡 Recommendations for Next Week",
        recommendations,
    ]
    return "\n".join(lines)
