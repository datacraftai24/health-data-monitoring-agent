"""Celery task configuration for MetaboCoach."""

from celery import Celery
from celery.schedules import crontab

from src.config import settings

celery_app = Celery(
    "metabocoach",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.tasks.libre_poller",
        "src.tasks.daily_summary",
        "src.tasks.weekly_report",
        "src.tasks.pattern_analysis",
        "src.tasks.meal_followup",
        "src.tasks.focus_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Toronto",
    enable_utc=True,
)

# Scheduled tasks (Celery Beat) — all times in America/Toronto
celery_app.conf.beat_schedule = {
    # === HEALTH ===
    "poll-glucose": {
        "task": "src.tasks.libre_poller.poll_all_users_glucose",
        "schedule": 2400.0,  # Every 40 minutes
    },
    "daily-summary-report": {
        "task": "src.tasks.daily_summary.generate_daily_summaries",
        "schedule": crontab(hour=21, minute=0),  # 9 PM
    },
    "weekly-report": {
        "task": "src.tasks.weekly_report.generate_weekly_reports",
        "schedule": crontab(hour=19, minute=0, day_of_week="sunday"),
    },
    "pattern-analysis": {
        "task": "src.tasks.pattern_analysis.run_pattern_analysis",
        "schedule": crontab(hour=3, minute=0),  # 3 AM
    },

    # === FOCUS: MORNING (weekdays) ===
    "morning-activation": {
        "task": "src.tasks.focus_tasks.morning_activation_nudge",
        "schedule": crontab(hour=8, minute=15, day_of_week="mon-fri"),
    },
    "morning-escalation": {
        "task": "src.tasks.focus_tasks.morning_escalation",
        "schedule": crontab(hour=8, minute=35, day_of_week="mon-fri"),
    },
    "morning-late-escalation": {
        "task": "src.tasks.focus_tasks.morning_late_escalation",
        "schedule": crontab(hour=9, minute=0, day_of_week="mon-fri"),
    },

    # === FOCUS: DAY CHECK-INS (weekdays) ===
    "mid-morning-checkin": {
        "task": "src.tasks.focus_tasks.mid_morning_checkin",
        "schedule": crontab(hour=10, minute=30, day_of_week="mon-fri"),
    },
    "afternoon-block": {
        "task": "src.tasks.focus_tasks.afternoon_block_reminder",
        "schedule": crontab(hour=13, minute=25, day_of_week="mon-fri"),
    },
    "builder-block": {
        "task": "src.tasks.focus_tasks.builder_block_reminder",
        "schedule": crontab(hour=15, minute=15, day_of_week="mon-fri"),
    },
    "day-closing": {
        "task": "src.tasks.focus_tasks.day_closing",
        "schedule": crontab(hour=17, minute=0, day_of_week="mon-fri"),
    },

    # === FOCUS: EVENING (daily) ===
    "night-planning": {
        "task": "src.tasks.focus_tasks.evening_night_planning",
        "schedule": crontab(hour=21, minute=0),  # 9 PM
    },
    "night-incomplete": {
        "task": "src.tasks.focus_tasks.night_planning_incomplete",
        "schedule": crontab(hour=21, minute=45),  # 9:45 PM
    },
}
