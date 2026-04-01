"""Alert engine — evaluates rules against current health context and triggers alerts."""

import logging
from dataclasses import dataclass
from datetime import datetime

from src.engine.rules import RULES_BY_NAME, AlertRule

logger = logging.getLogger(__name__)


@dataclass
class TriggeredAlert:
    rule_name: str
    priority: str
    message: str
    timestamp: datetime
    glucose_value: float | None = None


@dataclass
class HealthContext:
    """Current health state for rule evaluation."""

    current_glucose: float | None = None
    glucose_trend: str | None = None  # falling_fast, falling, stable, rising, rising_fast
    rate_of_change: float = 0.0  # mmol/L per 15 min
    time_since_last_meal_hours: float | None = None
    last_meal_carbs_g: float | None = None
    steps_last_30min: int = 0
    steps_today: int = 0
    calories_today: int = 0
    protein_today: float = 0
    calorie_target: int = 1800
    is_bedtime: bool = False
    has_upcoming_activity: bool = False
    upcoming_activity_type: str | None = None
    current_hour: int = 12  # 0-23, for sleep window detection


class AlertEngine:
    """Evaluate health context against alert rules."""

    def evaluate(self, ctx: HealthContext) -> list[TriggeredAlert]:
        """Evaluate all rules and return triggered alerts."""
        alerts = []
        now = datetime.utcnow()

        if ctx.current_glucose is None:
            return alerts

        # Active crash — glucose critically low
        if ctx.current_glucose < 3.9:
            rule = RULES_BY_NAME["active_crash"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(glucose=ctx.current_glucose),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Crash prediction — glucose falling fast and getting low
        elif (
            ctx.glucose_trend in ("falling", "falling_fast")
            and ctx.rate_of_change < -0.5
            and ctx.current_glucose < 5.5
            and (ctx.time_since_last_meal_hours or 0) > 2
        ):
            rule = RULES_BY_NAME["crash_prediction"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(glucose=ctx.current_glucose),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Sleep window: suppress fasting/meal reminders between midnight-7AM
        # unless glucose is actually dropping below 4.0 (handled by crash alerts above)
        is_sleep_window = ctx.current_hour < 7 or ctx.current_hour >= 24

        # Pre-meal reminder — too long since last meal (suppressed during sleep)
        if (
            not is_sleep_window
            and ctx.time_since_last_meal_hours is not None
            and ctx.time_since_last_meal_hours > 2.5
            and ctx.current_glucose < 6.0
        ):
            rule = RULES_BY_NAME["pre_meal_reminder"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(hours=ctx.time_since_last_meal_hours),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Post-meal walk nudge — glucose rising after eating
        if (
            ctx.glucose_trend in ("rising", "rising_fast")
            and ctx.current_glucose > 7.5
            and ctx.time_since_last_meal_hours is not None
            and ctx.time_since_last_meal_hours < 1.0
            and ctx.steps_last_30min < 200
        ):
            rule = RULES_BY_NAME["post_meal_walk_nudge"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(glucose=ctx.current_glucose),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Pre-nap warning — sedentary after carb-heavy meal with falling glucose
        if (
            ctx.glucose_trend in ("falling", "falling_fast")
            and ctx.time_since_last_meal_hours is not None
            and 0.5 <= ctx.time_since_last_meal_hours <= 1.5
            and (ctx.last_meal_carbs_g or 0) > 40
            and ctx.steps_last_30min < 100
        ):
            rule = RULES_BY_NAME["pre_nap_warning"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template,
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Pre-exercise fuel check
        if (
            ctx.has_upcoming_activity
            and ctx.current_glucose < 5.5
            and (ctx.time_since_last_meal_hours or 0) > 2
        ):
            rule = RULES_BY_NAME["pre_exercise_fuel_check"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(glucose=ctx.current_glucose),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        # Overnight crash prevention
        if ctx.is_bedtime and ctx.current_glucose < 5.0:
            rule = RULES_BY_NAME["overnight_crash_prevention"]
            alerts.append(
                TriggeredAlert(
                    rule_name=rule.name,
                    priority=rule.priority,
                    message=rule.message_template.format(glucose=ctx.current_glucose),
                    timestamp=now,
                    glucose_value=ctx.current_glucose,
                )
            )

        return alerts


alert_engine = AlertEngine()
