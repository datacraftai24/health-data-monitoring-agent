"""Tests for the food analyzer module."""

from src.ai.food_analyzer import FoodAnalyzer


class TestFoodAnalyzerParsing:
    """Test the response parsing logic (no API calls needed)."""

    def setup_method(self):
        self.analyzer = FoodAnalyzer()

    def test_parse_valid_json(self):
        """Should parse valid JSON response."""
        response = '{"items": [{"name": "rice", "calories": 200}], "total_calories": 200}'
        result = self.analyzer._parse_response(response)
        assert result["total_calories"] == 200
        assert len(result["items"]) == 1

    def test_parse_json_with_code_blocks(self):
        """Should handle JSON wrapped in markdown code blocks."""
        response = '```json\n{"items": [], "total_calories": 500}\n```'
        result = self.analyzer._parse_response(response)
        assert result["total_calories"] == 500

    def test_parse_invalid_json(self):
        """Should return fallback dict for invalid JSON."""
        response = "This is not JSON at all"
        result = self.analyzer._parse_response(response)
        assert result["total_calories"] == 0
        assert "Unable to analyze" in result["recommendation"]

    def test_build_system_prompt_with_profile(self):
        """Should include user profile data in system prompt."""
        prompt = self.analyzer._build_system_prompt(
            user_profile={"hba1c": 6.2, "daily_calorie_target": 1700},
            current_glucose=5.5,
        )
        assert "6.2" in prompt
        assert "1700" in prompt
        assert "5.5" in prompt

    def test_build_system_prompt_with_food_history(self):
        """Should include food history in system prompt."""
        history = [
            {"food_name": "rice", "avg_peak_glucose": 9.0, "crash_probability": 0.3},
        ]
        prompt = self.analyzer._build_system_prompt(food_history=history)
        assert "rice" in prompt
        assert "9.0" in prompt
