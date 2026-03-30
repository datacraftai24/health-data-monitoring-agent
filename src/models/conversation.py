"""Conversation log model — stores all user-bot interactions."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "in" or "out"
    intent: Mapped[str | None] = mapped_column(String(50))  # classified intent
    agent: Mapped[str | None] = mapped_column(String(50))  # which agent handled it
    message: Mapped[str] = mapped_column(Text, nullable=False)
    has_photo: Mapped[bool] = mapped_column(default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
