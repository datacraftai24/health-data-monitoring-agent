"""Alert rule definitions for the MetaboCoach rule engine."""

from dataclasses import dataclass


@dataclass
class AlertRule:
    name: str
    description: str
    priority: str  # critical, high, medium, low
    message_template: str


RULES: list[AlertRule] = [
    AlertRule(
        name="crash_prediction",
        description="Predict glucose crash before it happens",
        priority="critical",
        message_template=(
            "⚠️ Glucose at {glucose} mmol/L and dropping fast. "
            "Eat a snack NOW to prevent a crash."
        ),
    ),
    AlertRule(
        name="active_crash",
        description="Glucose is critically low",
        priority="critical",
        message_template=(
            "🚨 Glucose at {glucose} mmol/L — this is LOW. "
            "Eat fast-acting carbs immediately (juice, glucose tabs, fruit)."
        ),
    ),
    AlertRule(
        name="pre_meal_reminder",
        description="Remind to eat before gap gets too long",
        priority="medium",
        message_template=(
            "🍽️ It's been {hours:.1f}h since you last ate. "
            "Time for a snack to keep glucose stable."
        ),
    ),
    AlertRule(
        name="post_meal_walk_nudge",
        description="Suggest walk when spike detected",
        priority="medium",
        message_template=(
            "🚶 Glucose at {glucose} mmol/L after eating. "
            "A 10-min walk now will help bring it down."
        ),
    ),
    AlertRule(
        name="pre_nap_warning",
        description="Warn before napping if crash risk is high",
        priority="high",
        message_template=(
            "😴 Your glucose is dropping after that meal. "
            "Walk 10 min before napping to avoid a crash."
        ),
    ),
    AlertRule(
        name="pre_exercise_fuel_check",
        description="Ensure adequate fuel before exercise",
        priority="high",
        message_template=(
            "💪 Glucose is {glucose} mmol/L before your workout. "
            "Eat a banana or small snack first to fuel up."
        ),
    ),
    AlertRule(
        name="overnight_crash_prevention",
        description="Ensure adequate fuel before sleep",
        priority="high",
        message_template=(
            "🌙 Glucose is {glucose} mmol/L before bed. "
            "Have a small protein snack to avoid an overnight crash."
        ),
    ),
    AlertRule(
        name="daily_calorie_update",
        description="Track daily calorie progress after meal",
        priority="low",
        message_template=(
            "📊 Today so far: {calories} cal, {protein}g protein. "
            "Budget remaining: {remaining} cal."
        ),
    ),
    AlertRule(
        name="high_gi_food_warning",
        description="Warn when high GI food detected",
        priority="medium",
        message_template=(
            "⚠️ {food} tends to spike your glucose (peak {peak} mmol/L last time). "
            "Consider {alternative} instead, or walk right after eating."
        ),
    ),
]

RULES_BY_NAME = {rule.name: rule for rule in RULES}
