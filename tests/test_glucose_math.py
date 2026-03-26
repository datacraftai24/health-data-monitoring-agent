"""Tests for glucose math utilities."""

from src.utils.glucose_math import (
    classify_glucose,
    estimated_a1c,
    is_in_range,
    mgdl_to_mmol,
    mmol_to_mgdl,
    trend_arrow_to_label,
)


class TestGlucoseMath:
    def test_mmol_to_mgdl(self):
        assert mmol_to_mgdl(5.5) == 99.1

    def test_mgdl_to_mmol(self):
        assert mgdl_to_mmol(100) == 5.6

    def test_roundtrip_conversion(self):
        original = 6.0
        converted = mgdl_to_mmol(mmol_to_mgdl(original))
        assert abs(converted - original) < 0.2

    def test_trend_arrow_labels(self):
        assert trend_arrow_to_label(1) == "falling_fast"
        assert trend_arrow_to_label(3) == "stable"
        assert trend_arrow_to_label(5) == "rising_fast"
        assert trend_arrow_to_label(None) is None

    def test_is_in_range(self):
        assert is_in_range(5.5)
        assert is_in_range(3.9)
        assert is_in_range(9.0)
        assert not is_in_range(3.8)
        assert not is_in_range(9.1)

    def test_classify_glucose(self):
        assert classify_glucose(2.5) == "very_low"
        assert classify_glucose(3.5) == "low"
        assert classify_glucose(5.5) == "normal"
        assert classify_glucose(9.5) == "elevated"
        assert classify_glucose(12.0) == "high"
        assert classify_glucose(15.0) == "very_high"

    def test_estimated_a1c(self):
        # Average glucose of 5.5 mmol/L ≈ 99 mg/dL → eA1C ≈ 5.1
        a1c = estimated_a1c(5.5)
        assert 4.5 < a1c < 6.0
