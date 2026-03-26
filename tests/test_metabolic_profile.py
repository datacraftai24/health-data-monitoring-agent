"""Tests for metabolic profile."""

from src.engine.metabolic_profile import MetabolicProfile


class TestMetabolicProfile:
    def test_phase_observation(self):
        profile = MetabolicProfile(days_of_data=3)
        profile.update_phase()
        assert profile.phase == "observation"

    def test_phase_pattern_matching(self):
        profile = MetabolicProfile(days_of_data=10)
        profile.update_phase()
        assert profile.phase == "pattern_matching"

    def test_phase_predictive(self):
        profile = MetabolicProfile(days_of_data=20)
        profile.update_phase()
        assert profile.phase == "predictive"

    def test_update_food_response(self):
        profile = MetabolicProfile()
        profile.update_food_response("rice", peak_glucose=9.0, time_to_peak_min=45, crashed=False)
        profile.update_food_response("rice", peak_glucose=8.0, time_to_peak_min=40, crashed=True)

        fr = profile.food_responses["rice"]
        assert fr.sample_count == 2
        assert fr.avg_peak == 8.5
        assert fr.crash_probability == 0.5

    def test_get_crash_risk_unknown_food(self):
        profile = MetabolicProfile()
        assert profile.get_crash_risk_for_food("unknown") == 0.0

    def test_serialization_roundtrip(self):
        profile = MetabolicProfile(
            user_id="test-123",
            days_of_data=14,
            avg_fasting_glucose=5.2,
        )
        profile.update_food_response("dal", peak_glucose=7.0, time_to_peak_min=30, crashed=False)

        data = profile.to_dict()
        restored = MetabolicProfile.from_dict(data)

        assert restored.user_id == "test-123"
        assert restored.days_of_data == 14
        assert restored.avg_fasting_glucose == 5.2
        assert "dal" in restored.food_responses

    def test_predicted_peak_requires_samples(self):
        profile = MetabolicProfile()
        profile.update_food_response("rice", peak_glucose=9.0, time_to_peak_min=45, crashed=False)
        # Only 1 sample — should return None
        assert profile.get_predicted_peak("rice") is None

        profile.update_food_response("rice", peak_glucose=8.0, time_to_peak_min=40, crashed=False)
        # 2 samples — should return a value
        assert profile.get_predicted_peak("rice") is not None
