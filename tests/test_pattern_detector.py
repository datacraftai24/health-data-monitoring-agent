"""Tests for glucose pattern detection."""

from datetime import datetime, timedelta

from src.ai.pattern_detector import PatternDetector


class TestPatternDetector:
    def setup_method(self):
        self.detector = PatternDetector()

    def _make_readings(self, values: list[float], interval_min: int = 5) -> list[dict]:
        """Create a list of mock readings from glucose values."""
        base = datetime(2026, 3, 26, 12, 0, 0)
        return [
            {
                "timestamp": base + timedelta(minutes=i * interval_min),
                "glucose_mmol": v,
                "trend_arrow": 3,
            }
            for i, v in enumerate(values)
        ]

    def test_detect_crash(self):
        """Should detect a glucose crash below 3.9."""
        readings = self._make_readings([6.0, 5.5, 4.5, 3.8, 3.5, 3.2, 3.8, 4.5])
        analysis = self.detector.analyze_readings(readings)
        assert analysis.crash_count >= 1

    def test_detect_spike(self):
        """Should detect a glucose spike above 10.0."""
        readings = self._make_readings([6.0, 7.5, 9.0, 10.5, 11.0, 10.2, 9.0, 7.5])
        analysis = self.detector.analyze_readings(readings)
        assert analysis.spike_count >= 1

    def test_time_in_range(self):
        """Should calculate time in range correctly."""
        # All readings in range (3.9-9.0)
        readings = self._make_readings([5.0, 5.5, 6.0, 6.5, 7.0])
        analysis = self.detector.analyze_readings(readings)
        assert analysis.time_in_range_pct == 100.0

    def test_time_in_range_mixed(self):
        """Should handle mixed in/out of range readings."""
        # 3 in range, 2 out of range
        readings = self._make_readings([5.0, 6.0, 7.0, 3.5, 10.5])
        analysis = self.detector.analyze_readings(readings)
        assert analysis.time_in_range_pct == 60.0

    def test_rate_of_change_falling(self):
        """Should calculate negative rate of change for falling glucose."""
        readings = self._make_readings([7.0, 6.0])
        rate = self.detector.calculate_rate_of_change(readings)
        assert rate < 0

    def test_rate_of_change_rising(self):
        """Should calculate positive rate of change for rising glucose."""
        readings = self._make_readings([5.0, 6.0])
        rate = self.detector.calculate_rate_of_change(readings)
        assert rate > 0

    def test_rate_of_change_stable(self):
        """Should calculate near-zero rate for stable glucose."""
        readings = self._make_readings([5.5, 5.5])
        rate = self.detector.calculate_rate_of_change(readings)
        assert rate == 0.0

    def test_empty_readings(self):
        """Should handle empty readings gracefully."""
        analysis = self.detector.analyze_readings([])
        assert analysis.crash_count == 0
        assert analysis.spike_count == 0

    def test_single_reading(self):
        """Should handle a single reading."""
        readings = self._make_readings([5.5])
        analysis = self.detector.analyze_readings(readings)
        assert analysis.time_in_range_pct == 100.0

    def test_rapid_drop_detection(self):
        """Should detect rapid glucose drops."""
        # Drop of 2.0 mmol/L in 5 minutes = very rapid
        readings = self._make_readings([8.0, 6.0])
        analysis = self.detector.analyze_readings(readings)
        rapid_drops = [p for p in analysis.patterns if p.pattern_type == "rapid_drop"]
        assert len(rapid_drops) > 0
