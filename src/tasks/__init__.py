"""Celery task configuration for MetaboCoach."""

from celery import Celery
from celery.schedules import crontab

from src.config import settings

celery_app = Celery("metabocoach", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.default_timezone,
    enable_utc=True,
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "poll-glucose-active-hours": {
        "task": "src.tasks.libre_poller.poll_all_users_glucose",
        "schedule": 300.0,  # Every 5 minutes
    },
    "daily-summary-report": {
        "task": "src.tasks.daily_summary.generate_daily_summaries",
        "schedule": crontab(hour=21, minute=0),  # 9 PM daily
    },
    "weekly-report": {
        "task": "src.tasks.weekly_report.generate_weekly_reports",
        "schedule": crontab(hour=19, minute=0, day_of_week="sunday"),  # Sunday 7 PM
    },
    "pattern-analysis": {
        "task": "src.tasks.pattern_analysis.run_pattern_analysis",
        "schedule": crontab(hour=3, minute=0),  # 3 AM daily
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["src.tasks"])
