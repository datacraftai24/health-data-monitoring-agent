"""Tests for the alert rule engine."""

from datetime import datetime

from src.engine.alert_engine import AlertEngine, HealthContext


class TestAlertEngine:
    def setup_method(self):
        self.engine = AlertEngine()

    def test_active_crash_alert(self):
        """Should trigger critical alert when glucose is below 3.9."""
        ctx = HealthContext(current_glucose=3.5, glucose_trend="falling")
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "active_crash" for a in alerts)
        assert any(a.priority == "critical" for a in alerts)

    def test_crash_prediction(self):
        """Should predict crash when glucose falling fast and getting low."""
        ctx = HealthContext(
            current_glucose=5.2,
            glucose_trend="falling_fast",
            rate_of_change=-0.8,
            time_since_last_meal_hours=3.0,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "crash_prediction" for a in alerts)

    def test_no_crash_prediction_when_stable(self):
        """Should not predict crash when glucose is stable."""
        ctx = HealthContext(
            current_glucose=5.2,
            glucose_trend="stable",
            rate_of_change=0.0,
            time_since_last_meal_hours=3.0,
        )
        alerts = self.engine.evaluate(ctx)
        assert not any(a.rule_name == "crash_prediction" for a in alerts)

    def test_pre_meal_reminder(self):
        """Should remind to eat when too long since last meal and glucose dropping."""
        ctx = HealthContext(
            current_glucose=5.5,
            glucose_trend="stable",
            time_since_last_meal_hours=3.0,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "pre_meal_reminder" for a in alerts)

    def test_no_meal_reminder_when_recently_ate(self):
        """Should not remind to eat when user ate recently."""
        ctx = HealthContext(
            current_glucose=5.5,
            glucose_trend="stable",
            time_since_last_meal_hours=1.0,
        )
        alerts = self.engine.evaluate(ctx)
        assert not any(a.rule_name == "pre_meal_reminder" for a in alerts)

    def test_post_meal_walk_nudge(self):
        """Should suggest walk when glucose is spiking after meal."""
        ctx = HealthContext(
            current_glucose=8.5,
            glucose_trend="rising",
            time_since_last_meal_hours=0.5,
            steps_last_30min=50,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "post_meal_walk_nudge" for a in alerts)

    def test_no_walk_nudge_if_already_walking(self):
        """Should not suggest walk if user is already walking."""
        ctx = HealthContext(
            current_glucose=8.5,
            glucose_trend="rising",
            time_since_last_meal_hours=0.5,
            steps_last_30min=500,
        )
        alerts = self.engine.evaluate(ctx)
        assert not any(a.rule_name == "post_meal_walk_nudge" for a in alerts)

    def test_pre_nap_warning(self):
        """Should warn before napping if crash risk is high."""
        ctx = HealthContext(
            current_glucose=6.0,
            glucose_trend="falling",
            time_since_last_meal_hours=1.0,
            last_meal_carbs_g=60,
            steps_last_30min=20,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "pre_nap_warning" for a in alerts)

    def test_overnight_crash_prevention(self):
        """Should alert before bed if glucose is low."""
        ctx = HealthContext(
            current_glucose=4.5,
            glucose_trend="stable",
            is_bedtime=True,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "overnight_crash_prevention" for a in alerts)

    def test_pre_exercise_fuel_check(self):
        """Should alert before exercise if glucose is low."""
        ctx = HealthContext(
            current_glucose=5.0,
            glucose_trend="stable",
            has_upcoming_activity=True,
            time_since_last_meal_hours=3.0,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "pre_exercise_fuel_check" for a in alerts)

    def test_no_alerts_when_normal(self):
        """Should not trigger any critical alerts when everything is normal."""
        ctx = HealthContext(
            current_glucose=6.5,
            glucose_trend="stable",
            rate_of_change=0.1,
            time_since_last_meal_hours=1.5,
            steps_last_30min=300,
        )
        alerts = self.engine.evaluate(ctx)
        critical = [a for a in alerts if a.priority == "critical"]
        assert len(critical) == 0

    def test_no_alerts_when_glucose_is_none(self):
        """Should return empty alerts when glucose is None."""
        ctx = HealthContext(current_glucose=None)
        alerts = self.engine.evaluate(ctx)
        assert len(alerts) == 0

    def test_sleep_window_suppresses_meal_reminder(self):
        """Should NOT send fasting alert at 3 AM even if 9 hours since last meal."""
        ctx = HealthContext(
            current_glucose=5.5,
            glucose_trend="stable",
            time_since_last_meal_hours=9.0,
            current_hour=3,
        )
        alerts = self.engine.evaluate(ctx)
        assert not any(a.rule_name == "pre_meal_reminder" for a in alerts)

    def test_sleep_window_still_allows_crash_alert(self):
        """Should still send crash alert at 3 AM if glucose is critically low."""
        ctx = HealthContext(
            current_glucose=3.5,
            glucose_trend="falling",
            current_hour=3,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "active_crash" for a in alerts)

    def test_daytime_meal_reminder_works(self):
        """Should send fasting alert during the day normally."""
        ctx = HealthContext(
            current_glucose=5.5,
            glucose_trend="stable",
            time_since_last_meal_hours=3.0,
            current_hour=14,
        )
        alerts = self.engine.evaluate(ctx)
        assert any(a.rule_name == "pre_meal_reminder" for a in alerts)
