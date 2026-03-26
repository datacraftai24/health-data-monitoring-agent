"""Glucose pattern detection and analysis."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.models.glucose import GlucoseReading

logger = logging.getLogger(__name__)

# Trend arrow mappings
TREND_LABELS = {
    1: "falling_fast",
    2: "falling",
    3: "stable",
    4: "rising",
    5: "rising_fast",
}


@dataclass
class GlucosePattern:
    pattern_type: str  # crash, spike, prolonged_high, rapid_drop, overnight_low
    start_time: datetime | None = None
    end_time: datetime | None = None
    min_glucose: float = 0.0
    max_glucose: float = 0.0
    rate_of_change: float = 0.0  # mmol/L per 15 min
    severity: str = "low"  # low, medium, high


@dataclass
class PatternAnalysis:
    patterns: list[GlucosePattern] = field(default_factory=list)
    avg_fasting_glucose: float = 0.0
    avg_post_meal_peak: float = 0.0
    time_in_range_pct: float = 0.0
    crash_count: int = 0
    spike_count: int = 0


class PatternDetector:
    """Detect glucose patterns from time-series data."""

    def __init__(
        self,
        low_threshold: float = 3.9,
        high_threshold: float = 10.0,
        target_low: float = 3.9,
        target_high: float = 9.0,
    ):
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.target_low = target_low
        self.target_high = target_high

    def analyze_readings(self, readings: list[dict]) -> PatternAnalysis:
        """Analyze a list of glucose readings and detect patterns.

        Args:
            readings: List of dicts with 'timestamp', 'glucose_mmol', 'trend_arrow' keys.
        """
        if not readings:
            return PatternAnalysis()

        patterns = []
        glucose_values = [r["glucose_mmol"] for r in readings]

        # Time in range
        in_range = sum(1 for g in glucose_values if self.target_low <= g <= self.target_high)
        time_in_range_pct = (in_range / len(glucose_values)) * 100 if glucose_values else 0

        # Detect crashes (glucose < low_threshold)
        crashes = self._detect_crashes(readings)
        patterns.extend(crashes)

        # Detect spikes (glucose > high_threshold)
        spikes = self._detect_spikes(readings)
        patterns.extend(spikes)

        # Detect rapid drops
        rapid_drops = self._detect_rapid_drops(readings)
        patterns.extend(rapid_drops)

        return PatternAnalysis(
            patterns=patterns,
            avg_fasting_glucose=self._calc_fasting_avg(readings),
            time_in_range_pct=time_in_range_pct,
            crash_count=len(crashes),
            spike_count=len(spikes),
        )

    def calculate_rate_of_change(self, readings: list[dict]) -> float:
        """Calculate glucose rate of change in mmol/L per 15 minutes.

        Args:
            readings: Recent readings sorted by timestamp (newest last).

        Returns:
            Rate of change (negative = falling, positive = rising).
        """
        if len(readings) < 2:
            return 0.0

        latest = readings[-1]
        earlier = readings[-2]

        time_diff = (latest["timestamp"] - earlier["timestamp"]).total_seconds() / 60
        if time_diff == 0:
            return 0.0

        glucose_diff = latest["glucose_mmol"] - earlier["glucose_mmol"]
        return (glucose_diff / time_diff) * 15  # Normalize to per-15-min

    def _detect_crashes(self, readings: list[dict]) -> list[GlucosePattern]:
        crashes = []
        in_crash = False
        crash_start = None
        min_glucose = float("inf")

        for r in readings:
            if r["glucose_mmol"] < self.low_threshold:
                if not in_crash:
                    in_crash = True
                    crash_start = r["timestamp"]
                    min_glucose = r["glucose_mmol"]
                else:
                    min_glucose = min(min_glucose, r["glucose_mmol"])
            elif in_crash:
                severity = "high" if min_glucose < 3.3 else "medium" if min_glucose < 3.6 else "low"
                crashes.append(
                    GlucosePattern(
                        pattern_type="crash",
                        start_time=crash_start,
                        end_time=r["timestamp"],
                        min_glucose=min_glucose,
                        severity=severity,
                    )
                )
                in_crash = False
                min_glucose = float("inf")

        return crashes

    def _detect_spikes(self, readings: list[dict]) -> list[GlucosePattern]:
        spikes = []
        in_spike = False
        spike_start = None
        max_glucose = 0.0

        for r in readings:
            if r["glucose_mmol"] > self.high_threshold:
                if not in_spike:
                    in_spike = True
                    spike_start = r["timestamp"]
                    max_glucose = r["glucose_mmol"]
                else:
                    max_glucose = max(max_glucose, r["glucose_mmol"])
            elif in_spike:
                severity = "high" if max_glucose > 12.0 else "medium" if max_glucose > 10.5 else "low"
                spikes.append(
                    GlucosePattern(
                        pattern_type="spike",
                        start_time=spike_start,
                        end_time=r["timestamp"],
                        max_glucose=max_glucose,
                        severity=severity,
                    )
                )
                in_spike = False
                max_glucose = 0.0

        return spikes

    def _detect_rapid_drops(self, readings: list[dict]) -> list[GlucosePattern]:
        rapid_drops = []
        for i in range(1, len(readings)):
            rate = self.calculate_rate_of_change([readings[i - 1], readings[i]])
            if rate < -0.5:  # Falling more than 0.5 mmol/L per 15 min
                severity = "high" if rate < -1.0 else "medium"
                rapid_drops.append(
                    GlucosePattern(
                        pattern_type="rapid_drop",
                        start_time=readings[i - 1]["timestamp"],
                        end_time=readings[i]["timestamp"],
                        rate_of_change=rate,
                        severity=severity,
                    )
                )
        return rapid_drops

    def _calc_fasting_avg(self, readings: list[dict]) -> float:
        """Calculate average fasting glucose (readings between 5-7 AM)."""
        fasting = [
            r["glucose_mmol"]
            for r in readings
            if hasattr(r["timestamp"], "hour") and 5 <= r["timestamp"].hour < 7
        ]
        return sum(fasting) / len(fasting) if fasting else 0.0


pattern_detector = PatternDetector()
