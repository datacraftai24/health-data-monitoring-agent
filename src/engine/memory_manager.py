"""Memory manager — CRUD + context retrieval for agent RAG."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user_memory import UserMemory

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages user memories for agent context retrieval."""

    async def get_context(
        self, db: AsyncSession, user_id: str, category: str | None = None, limit: int = 20
    ) -> list[dict]:
        """Fetch relevant memories for an agent's context."""
        query = select(UserMemory).where(UserMemory.user_id == user_id)
        if category:
            query = query.where(UserMemory.category == category)
        query = query.order_by(UserMemory.updated_at.desc()).limit(limit)

        result = await db.execute(query)
        memories = result.scalars().all()
        return [
            {"key": m.key, "value": m.value, "category": m.category, "confidence": m.confidence}
            for m in memories
        ]

    async def get_context_text(
        self, db: AsyncSession, user_id: str, category: str | None = None, limit: int = 10
    ) -> str:
        """Get memories formatted as text for Gemini prompts."""
        memories = await self.get_context(db, user_id, category, limit)
        if not memories:
            return "No learned patterns yet."
        lines = []
        for m in memories:
            lines.append(f"- {m['key']}: {m['value']}")
        return "\n".join(lines)

    async def update(
        self, db: AsyncSession, user_id: str, key: str, value: str, category: str,
        confidence: float = 1.0,
    ):
        """Upsert a memory — update if key+category exists, create otherwise."""
        result = await db.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.key == key,
                UserMemory.category == category,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            existing.confidence = confidence
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(UserMemory(
                user_id=user_id,
                key=key,
                value=value,
                category=category,
                confidence=confidence,
            ))
        await db.commit()

    async def delete(self, db: AsyncSession, user_id: str, key: str, category: str):
        """Delete a specific memory."""
        result = await db.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.key == key,
                UserMemory.category == category,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            await db.delete(existing)
            await db.commit()


memory_manager = MemoryManager()
