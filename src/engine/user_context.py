"""User context profile — persistent, evolving knowledge about the user.

This is the core "memory" that makes the agent personal. It gets:
- Read by every agent on every interaction (injected into system prompts)
- Updated after meaningful conversations via Gemini extraction
- Stored in DB as a structured JSON document per user

Unlike UserMemory (key-value facts), this is a coherent narrative profile
that captures who the user is, what they're working on, their patterns, and
what the agent has learned about them.
"""

import json
import logging
from datetime import datetime, timezone

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.user import User

logger = logging.getLogger(__name__)

# Default profile structure for new users
DEFAULT_PROFILE = {
    "personal": {
        "name": "",
        "preferences": [],  # e.g., "prefers direct tone", "South Asian diet"
        "communication_style": "",  # learned from interactions
    },
    "health": {
        "conditions": [],  # e.g., "pre-diabetic", "reactive hypoglycemia"
        "known_spike_foods": [],  # e.g., "sooji chilla", "white rice > 1 cup"
        "known_safe_foods": [],  # e.g., "besan chilla", "paneer"
        "crash_triggers": [],  # e.g., "napping after high-carb meal", "skipping snack > 3h"
        "exercise_patterns": [],  # e.g., "pickleball MWF 8pm", "walks after lunch"
        "supplement_meds": [],
        "goals": [],  # e.g., "lose weight", "hit 120g protein daily"
    },
    "work": {
        "projects": [],  # e.g., "building ResidenceHive", "Twilio integration"
        "tools": [],  # e.g., "Trello", "Twilio", "Meta Business"
        "schedule_patterns": [],  # e.g., "deep work mornings", "calls afternoon"
        "current_focus": "",  # what they're working on right now
    },
    "habits": {
        "wake_time": "",
        "sleep_time": "",
        "meal_timing": [],  # e.g., "breakfast 8-9am", "dinner 7-8pm"
        "productivity_patterns": [],  # e.g., "best focus 9-11am", "energy dip 2-3pm"
        "known_blockers": [],  # e.g., "phone checking", "post-lunch nap"
    },
    "relationships": [],  # people mentioned: e.g., "Hamsa - business contact", "Matt - outreach"
    "pending_tasks": [],  # conversationally captured: "email Lifetime", "send doc to Hamsa"
    "last_updated": "",
}

EXTRACT_PROMPT = """You are a context extraction system. Analyze this conversation exchange and extract
any NEW information about the user that should be remembered for future interactions.

Current user profile:
{current_profile}

User said: {user_message}
Agent responded: {agent_response}

Extract ONLY new or updated facts. Return a JSON object with ONLY the fields that need updating.
Use the same structure as the current profile. For list fields, include only NEW items to add
(not the full list). For string fields, include the updated value.

If the user mentioned any tasks, to-dos, or things they need to do (even casually like
"I need to email X" or "send doc to Y"), capture them in "pending_tasks".

If there's nothing new to extract, return an empty JSON object: {}

Return ONLY valid JSON, no markdown."""


class UserContextManager:
    """Manages the persistent, evolving user context profile."""

    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    async def get_profile(self, db: AsyncSession, user: User) -> dict:
        """Get the user's context profile. Creates default if none exists."""
        # Stored in User.metabolic_profile JSON field under "user_context" key
        # (reusing existing JSON column to avoid migration)
        profile_data = user.metabolic_profile or {}
        context = profile_data.get("user_context")

        if not context:
            context = {**DEFAULT_PROFILE}
            context["personal"]["name"] = user.name or ""
            if user.hba1c:
                context["health"]["conditions"].append(f"HbA1c: {user.hba1c}%")

        return context

    async def get_profile_text(self, db: AsyncSession, user: User) -> str:
        """Get profile formatted as text for injection into system prompts."""
        profile = await self.get_profile(db, user)
        lines = []

        # Personal
        if profile.get("personal", {}).get("name"):
            lines.append(f"Name: {profile['personal']['name']}")
        if profile.get("personal", {}).get("preferences"):
            lines.append(f"Preferences: {', '.join(profile['personal']['preferences'])}")

        # Health
        h = profile.get("health", {})
        if h.get("conditions"):
            lines.append(f"Health: {', '.join(h['conditions'])}")
        if h.get("known_spike_foods"):
            lines.append(f"Spike foods: {', '.join(h['known_spike_foods'])}")
        if h.get("known_safe_foods"):
            lines.append(f"Safe foods: {', '.join(h['known_safe_foods'])}")
        if h.get("crash_triggers"):
            lines.append(f"Crash triggers: {', '.join(h['crash_triggers'])}")
        if h.get("goals"):
            lines.append(f"Goals: {', '.join(h['goals'])}")
        if h.get("exercise_patterns"):
            lines.append(f"Exercise: {', '.join(h['exercise_patterns'])}")

        # Work
        w = profile.get("work", {})
        if w.get("projects"):
            lines.append(f"Projects: {', '.join(w['projects'])}")
        if w.get("tools"):
            lines.append(f"Tools: {', '.join(w['tools'])}")
        if w.get("current_focus"):
            lines.append(f"Current focus: {w['current_focus']}")

        # Habits
        hab = profile.get("habits", {})
        if hab.get("productivity_patterns"):
            lines.append(f"Productivity: {', '.join(hab['productivity_patterns'])}")
        if hab.get("known_blockers"):
            lines.append(f"Blockers: {', '.join(hab['known_blockers'])}")

        # Pending tasks (critical — this is what "what's my todo list?" should surface)
        if profile.get("pending_tasks"):
            lines.append(f"Pending tasks: {', '.join(profile['pending_tasks'])}")

        # Relationships
        if profile.get("relationships"):
            lines.append(f"People: {', '.join(profile['relationships'])}")

        return "\n".join(lines) if lines else "No profile data yet."

    async def extract_and_update(
        self,
        db: AsyncSession,
        user: User,
        user_message: str,
        agent_response: str,
    ):
        """Extract new context from a conversation exchange and update the profile.

        Called after every meaningful agent interaction.
        """
        current = await self.get_profile(db, user)

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=EXTRACT_PROMPT.format(
                    current_profile=json.dumps(current, indent=2),
                    user_message=user_message,
                    agent_response=agent_response,
                ),
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=500,
                    response_mime_type="application/json",
                ),
            )

            updates = self._parse_json(response.text)
            if not updates:
                return  # Nothing new learned

            # Merge updates into current profile
            updated = self._merge_profile(current, updates)
            updated["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Save back to user record
            profile_data = user.metabolic_profile or {}
            profile_data["user_context"] = updated
            user.metabolic_profile = profile_data
            await db.commit()

            logger.info("User context updated for %s: %s", user.id, list(updates.keys()))

        except Exception:
            logger.exception("Failed to extract user context for %s", user.id)

    def _merge_profile(self, current: dict, updates: dict) -> dict:
        """Deep merge updates into current profile. Lists get appended (deduped), strings get replaced."""
        merged = {**current}

        for key, value in updates.items():
            if key not in merged:
                merged[key] = value
                continue

            if isinstance(value, dict) and isinstance(merged[key], dict):
                merged[key] = self._merge_profile(merged[key], value)
            elif isinstance(value, list) and isinstance(merged[key], list):
                # Append new items, deduplicate
                existing = set(str(x).lower() for x in merged[key])
                for item in value:
                    if str(item).lower() not in existing:
                        merged[key].append(item)
                        existing.add(str(item).lower())
            elif isinstance(value, str) and value:
                merged[key] = value

        return merged

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from Gemini response."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        try:
            result = json.loads(cleaned)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse context extraction response: %s", text[:200])
            return {}

    async def update_field(
        self, db: AsyncSession, user: User, path: str, value
    ):
        """Manually update a specific field in the profile.

        Args:
            path: Dot-separated path like "work.current_focus" or "health.known_spike_foods"
            value: New value (string replaces, list items get appended)
        """
        current = await self.get_profile(db, user)
        keys = path.split(".")

        target = current
        for k in keys[:-1]:
            target = target.setdefault(k, {})

        final_key = keys[-1]
        if isinstance(value, list) and isinstance(target.get(final_key), list):
            existing = set(str(x).lower() for x in target[final_key])
            for item in value:
                if str(item).lower() not in existing:
                    target[final_key].append(item)
        else:
            target[final_key] = value

        current["last_updated"] = datetime.now(timezone.utc).isoformat()

        profile_data = user.metabolic_profile or {}
        profile_data["user_context"] = current
        user.metabolic_profile = profile_data
        await db.commit()

    async def remove_pending_task(self, db: AsyncSession, user: User, task: str):
        """Remove a completed task from pending_tasks."""
        current = await self.get_profile(db, user)
        tasks = current.get("pending_tasks", [])
        current["pending_tasks"] = [t for t in tasks if t.lower() != task.lower()]
        current["last_updated"] = datetime.now(timezone.utc).isoformat()

        profile_data = user.metabolic_profile or {}
        profile_data["user_context"] = current
        user.metabolic_profile = profile_data
        await db.commit()


user_context_manager = UserContextManager()
