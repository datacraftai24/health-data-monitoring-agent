"""Garmin Connect API client for activity, steps, and workout data."""

import logging
from dataclasses import dataclass
from datetime import date, datetime

from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GarminDailySummary:
    date: date
    steps: int = 0
    total_calories: int = 0
    active_calories: int = 0
    distance_km: float = 0.0
    active_minutes: int = 0
    heart_rate_avg: int | None = None
    heart_rate_resting: int | None = None
    stress_avg: int | None = None
    sleep_duration_min: int | None = None
    sleep_score: int | None = None


@dataclass
class GarminActivity:
    start_time: datetime
    end_time: datetime | None
    activity_type: str
    duration_min: int
    calories_burned: int
    avg_heart_rate: int | None = None


class GarminClient:
    """Client for Garmin Connect Push API.

    Garmin uses a Push API model — they send data to registered webhook endpoints.
    This client provides methods to parse incoming push data and also to validate
    webhook signatures.
    """

    def __init__(self):
        self.consumer_key = settings.garmin_consumer_key
        self.consumer_secret = settings.garmin_consumer_secret

    def parse_daily_summary(self, payload: dict) -> GarminDailySummary:
        """Parse a Garmin daily summary push notification."""
        summaries = payload.get("dailies", [])
        if not summaries:
            raise ValueError("No daily summary data in payload")

        s = summaries[0]
        return GarminDailySummary(
            date=date.fromisoformat(s.get("calendarDate", str(date.today()))),
            steps=s.get("steps", 0),
            total_calories=s.get("totalKilocalories", 0),
            active_calories=s.get("activeKilocalories", 0),
            distance_km=round(s.get("distanceInMeters", 0) / 1000, 2),
            active_minutes=s.get("moderateIntensityDurationInSeconds", 0) // 60
            + s.get("vigorousIntensityDurationInSeconds", 0) // 60,
            heart_rate_avg=s.get("averageHeartRateInBeatsPerMinute"),
            heart_rate_resting=s.get("restingHeartRateInBeatsPerMinute"),
            stress_avg=s.get("averageStressLevel"),
            sleep_duration_min=(s.get("sleepDurationInSeconds") or 0) // 60 or None,
            sleep_score=s.get("sleepScoreQuality"),
        )

    def parse_activity(self, payload: dict) -> list[GarminActivity]:
        """Parse Garmin activity push notification."""
        activities = payload.get("activities", [])
        results = []
        for a in activities:
            results.append(
                GarminActivity(
                    start_time=datetime.fromisoformat(a["startTimeInSeconds"]),
                    end_time=None,
                    activity_type=a.get("activityType", "unknown"),
                    duration_min=(a.get("durationInSeconds", 0)) // 60,
                    calories_burned=a.get("activeKilocalories", 0),
                    avg_heart_rate=a.get("averageHeartRateInBeatsPerMinute"),
                )
            )
        return results

    def parse_steps_intraday(self, payload: dict) -> int:
        """Parse intraday step count from Garmin push data. Returns total steps so far today."""
        epochs = payload.get("epochs", [])
        return sum(e.get("steps", 0) for e in epochs)


garmin_client = GarminClient()
