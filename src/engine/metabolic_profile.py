"""User metabolic profile — learned patterns from correlated data."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GlucoseResponse:
    """Glucose response pattern for a specific food."""

    food_name: str
    avg_peak: float = 0.0
    avg_time_to_peak_min: int = 45
    avg_time_to_baseline_min: int = 120
    crash_probability: float = 0.0
    sample_count: int = 0


@dataclass
class MetabolicProfile:
    """Personal metabolic profile built from correlated glucose, food, and activity data."""

    user_id: str = ""
    phase: str = "observation"  # observation, pattern_matching, predictive
    days_of_data: int = 0

    # Glucose baselines
    avg_fasting_glucose: float = 0.0
    avg_post_meal_peak: float = 0.0
    avg_time_to_peak_min: int = 45
    avg_time_to_baseline_min: int = 120
    crash_threshold_hours: float = 2.5
    crash_frequency_per_day: float = 0.0

    # Food response mapping (food_name -> GlucoseResponse)
    food_responses: dict[str, GlucoseResponse] = field(default_factory=dict)

    # Activity impact
    post_meal_walk_glucose_reduction: float = 0.0  # mmol/L reduction from 10-min walk
    exercise_glucose_impact: dict[str, float] = field(default_factory=dict)  # activity_type -> impact

    # Time-based patterns
    crash_risk_by_hour: dict[int, float] = field(default_factory=dict)  # hour -> probability
    morning_sensitivity: float = 1.0  # Multiplier vs evening
    evening_sensitivity: float = 1.0

    # Meal timing patterns: meal_type -> {avg_hour, avg_carbs, avg_spike, count}
    meal_timing_patterns: dict[str, dict] = field(default_factory=dict)
    # Best/worst performing meals for recommendations
    best_performing_meals: list[dict] = field(default_factory=list)
    worst_performing_meals: list[dict] = field(default_factory=list)

    last_updated: datetime | None = None

    def update_phase(self):
        """Update learning phase based on days of data collected."""
        if self.days_of_data >= 14:
            self.phase = "predictive"
        elif self.days_of_data >= 7:
            self.phase = "pattern_matching"
        else:
            self.phase = "observation"

    def update_food_response(
        self,
        food_name: str,
        peak_glucose: float,
        time_to_peak_min: int,
        crashed: bool,
    ):
        """Update the food response model with a new data point."""
        if food_name not in self.food_responses:
            self.food_responses[food_name] = GlucoseResponse(food_name=food_name)

        fr = self.food_responses[food_name]
        n = fr.sample_count

        # Running average
        fr.avg_peak = (fr.avg_peak * n + peak_glucose) / (n + 1)
        fr.avg_time_to_peak_min = (fr.avg_time_to_peak_min * n + time_to_peak_min) // (n + 1)
        fr.crash_probability = (fr.crash_probability * n + (1.0 if crashed else 0.0)) / (n + 1)
        fr.sample_count = n + 1

    def get_crash_risk_for_food(self, food_name: str) -> float:
        """Get the crash probability for a specific food. Returns 0.0 if unknown."""
        fr = self.food_responses.get(food_name)
        return fr.crash_probability if fr else 0.0

    def update_meal_timing(
        self, meal_type: str, hour: int, carbs_g: float, peak_glucose: float
    ):
        """Update meal timing patterns with a new data point."""
        if meal_type not in self.meal_timing_patterns:
            self.meal_timing_patterns[meal_type] = {
                "avg_hour": hour, "avg_carbs": carbs_g, "avg_spike": peak_glucose, "count": 0,
            }
        p = self.meal_timing_patterns[meal_type]
        n = p["count"]
        p["avg_hour"] = (p["avg_hour"] * n + hour) / (n + 1)
        p["avg_carbs"] = (p["avg_carbs"] * n + carbs_g) / (n + 1)
        p["avg_spike"] = (p["avg_spike"] * n + peak_glucose) / (n + 1)
        p["count"] = n + 1

    def get_predicted_peak(self, food_name: str) -> float | None:
        """Get predicted glucose peak for a food. Returns None if unknown."""
        fr = self.food_responses.get(food_name)
        return fr.avg_peak if fr and fr.sample_count >= 2 else None

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "user_id": self.user_id,
            "phase": self.phase,
            "days_of_data": self.days_of_data,
            "avg_fasting_glucose": self.avg_fasting_glucose,
            "avg_post_meal_peak": self.avg_post_meal_peak,
            "avg_time_to_peak_min": self.avg_time_to_peak_min,
            "avg_time_to_baseline_min": self.avg_time_to_baseline_min,
            "crash_threshold_hours": self.crash_threshold_hours,
            "crash_frequency_per_day": self.crash_frequency_per_day,
            "food_responses": {
                k: {
                    "food_name": v.food_name,
                    "avg_peak": v.avg_peak,
                    "avg_time_to_peak_min": v.avg_time_to_peak_min,
                    "crash_probability": v.crash_probability,
                    "sample_count": v.sample_count,
                }
                for k, v in self.food_responses.items()
            },
            "post_meal_walk_glucose_reduction": self.post_meal_walk_glucose_reduction,
            "crash_risk_by_hour": self.crash_risk_by_hour,
            "meal_timing_patterns": self.meal_timing_patterns,
            "best_performing_meals": self.best_performing_meals,
            "worst_performing_meals": self.worst_performing_meals,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetabolicProfile":
        """Deserialize from dict."""
        profile = cls(
            user_id=data.get("user_id", ""),
            phase=data.get("phase", "observation"),
            days_of_data=data.get("days_of_data", 0),
            avg_fasting_glucose=data.get("avg_fasting_glucose", 0),
            avg_post_meal_peak=data.get("avg_post_meal_peak", 0),
            avg_time_to_peak_min=data.get("avg_time_to_peak_min", 45),
            avg_time_to_baseline_min=data.get("avg_time_to_baseline_min", 120),
            crash_threshold_hours=data.get("crash_threshold_hours", 2.5),
            crash_frequency_per_day=data.get("crash_frequency_per_day", 0),
            post_meal_walk_glucose_reduction=data.get("post_meal_walk_glucose_reduction", 0),
            crash_risk_by_hour=data.get("crash_risk_by_hour", {}),
            meal_timing_patterns=data.get("meal_timing_patterns", {}),
            best_performing_meals=data.get("best_performing_meals", []),
            worst_performing_meals=data.get("worst_performing_meals", []),
        )
        for k, v in data.get("food_responses", {}).items():
            profile.food_responses[k] = GlucoseResponse(
                food_name=v.get("food_name", k),
                avg_peak=v.get("avg_peak", 0),
                avg_time_to_peak_min=v.get("avg_time_to_peak_min", 45),
                crash_probability=v.get("crash_probability", 0),
                sample_count=v.get("sample_count", 0),
            )
        return profile
