"""Focus system models — daily focus tracking, blocks, ideas, todos, tune requests."""

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class DailyFocus(Base):
    __tablename__ = "daily_focus"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Morning Activation Ritual
    ritual_shower: Mapped[bool] = mapped_column(Boolean, default=False)
    ritual_real_clothes: Mapped[bool] = mapped_column(Boolean, default=False)
    ritual_face_ice: Mapped[bool] = mapped_column(Boolean, default=False)
    ritual_phone_away: Mapped[bool] = mapped_column(Boolean, default=False)
    ritual_one_thing_set: Mapped[bool] = mapped_column(Boolean, default=False)
    ritual_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # The ONE Thing
    one_thing: Mapped[str | None] = mapped_column(Text)
    one_thing_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    one_thing_done: Mapped[bool] = mapped_column(Boolean, default=False)
    one_thing_done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phone Accountability
    phone_pickups: Mapped[int] = mapped_column(Integer, default=0)

    # End of Day
    wins: Mapped[str | None] = mapped_column(Text)
    daily_win: Mapped[str | None] = mapped_column(Text)
    daily_win_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    energy_rating: Mapped[int | None] = mapped_column(Integer)

    # Streak
    streak_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "date"),)


class FocusBlock(Base):
    __tablename__ = "focus_blocks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    daily_focus_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    task_description: Mapped[str | None] = mapped_column(Text)


class ParkedIdea(Base):
    __tablename__ = "parked_ideas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_taken: Mapped[str | None] = mapped_column(String(50))


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    daily_focus_id: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_for_date: Mapped[date] = mapped_column(Date, nullable=False)


class TuneRequest(Base):
    __tablename__ = "tune_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_recommendation: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class FocusWeeklySummary(Base):
    __tablename__ = "focus_weekly_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    week_end: Mapped[date] = mapped_column(Date, nullable=False)

    ritual_completion_days: Mapped[int | None] = mapped_column(Integer)
    focus_blocks_completed: Mapped[int | None] = mapped_column(Integer)
    one_thing_completed_days: Mapped[int | None] = mapped_column(Integer)
    avg_phone_pickups: Mapped[float | None] = mapped_column(Float)
    ideas_parked: Mapped[int | None] = mapped_column(Integer)
    total_focus_minutes: Mapped[int | None] = mapped_column(Integer)

    ai_analysis: Mapped[str | None] = mapped_column(Text)
    ai_recommendations: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
