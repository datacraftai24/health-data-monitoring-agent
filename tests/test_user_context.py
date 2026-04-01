"""Tests for user context profile system."""

from src.engine.user_context import UserContextManager, DEFAULT_PROFILE


class TestUserContextManager:
    def setup_method(self):
        self.manager = UserContextManager()

    def test_merge_new_list_items(self):
        """Should append new items to lists without duplicating existing."""
        current = {
            "health": {
                "known_spike_foods": ["white rice", "sooji chilla"],
            }
        }
        updates = {
            "health": {
                "known_spike_foods": ["naan", "white rice"],  # "white rice" already exists
            }
        }
        merged = self.manager._merge_profile(current, updates)
        assert len(merged["health"]["known_spike_foods"]) == 3
        assert "naan" in merged["health"]["known_spike_foods"]
        assert "white rice" in merged["health"]["known_spike_foods"]

    def test_merge_string_field(self):
        """Should replace string fields with new value."""
        current = {"work": {"current_focus": "ResidenceHive"}}
        updates = {"work": {"current_focus": "MetaboCoach"}}
        merged = self.manager._merge_profile(current, updates)
        assert merged["work"]["current_focus"] == "MetaboCoach"

    def test_merge_empty_updates(self):
        """Should not modify profile with empty updates."""
        current = {"personal": {"name": "Test"}}
        merged = self.manager._merge_profile(current, {})
        assert merged == current

    def test_merge_nested_dict(self):
        """Should deep merge nested dicts."""
        current = {
            "health": {"conditions": ["pre-diabetic"], "goals": []},
            "work": {"projects": ["ResidenceHive"]},
        }
        updates = {
            "health": {"goals": ["lose 5kg"]},
            "work": {"tools": ["Twilio"]},
        }
        merged = self.manager._merge_profile(current, updates)
        assert merged["health"]["conditions"] == ["pre-diabetic"]
        assert merged["health"]["goals"] == ["lose 5kg"]
        assert merged["work"]["projects"] == ["ResidenceHive"]
        assert merged["work"]["tools"] == ["Twilio"]

    def test_merge_pending_tasks(self):
        """Should capture conversationally mentioned tasks."""
        current = {"pending_tasks": ["email Lifetime"]}
        updates = {"pending_tasks": ["send doc to Hamsa", "email Lifetime"]}
        merged = self.manager._merge_profile(current, updates)
        assert len(merged["pending_tasks"]) == 2
        assert "send doc to Hamsa" in merged["pending_tasks"]

    def test_parse_valid_json(self):
        result = self.manager._parse_json('{"health": {"goals": ["lose weight"]}}')
        assert result["health"]["goals"] == ["lose weight"]

    def test_parse_empty_json(self):
        result = self.manager._parse_json("{}")
        assert result == {}

    def test_parse_invalid_json(self):
        result = self.manager._parse_json("not json")
        assert result == {}

    def test_parse_json_with_code_blocks(self):
        result = self.manager._parse_json('```json\n{"test": true}\n```')
        assert result["test"] is True

    def test_default_profile_structure(self):
        """Default profile should have all expected sections."""
        assert "personal" in DEFAULT_PROFILE
        assert "health" in DEFAULT_PROFILE
        assert "work" in DEFAULT_PROFILE
        assert "habits" in DEFAULT_PROFILE
        assert "pending_tasks" in DEFAULT_PROFILE
        assert "relationships" in DEFAULT_PROFILE

    def test_deduplication_case_insensitive(self):
        """Should not add 'Rice' if 'rice' already exists."""
        current = {"health": {"known_spike_foods": ["rice"]}}
        updates = {"health": {"known_spike_foods": ["Rice", "naan"]}}
        merged = self.manager._merge_profile(current, updates)
        assert len(merged["health"]["known_spike_foods"]) == 2
