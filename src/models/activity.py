"""Activity and workout models."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class ActivityData(Base):
    __tablename__ = "activity_data"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    steps: Mapped[int | None] = mapped_column(Integer)
    total_calories: Mapped[int | None] = mapped_column(Integer)
    active_calories: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)
    active_minutes: Mapped[int | None] = mapped_column(Integer)
    heart_rate_avg: Mapped[int | None] = mapped_column(Integer)
    heart_rate_resting: Mapped[int | None] = mapped_column(Integer)
    stress_avg: Mapped[int | None] = mapped_column(Integer)
    sleep_duration_min: Mapped[int | None] = mapped_column(Integer)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activity_type: Mapped[str | None] = mapped_column(String(50))
    duration_min: Mapped[int | None] = mapped_column(Integer)
    calories_burned: Mapped[int | None] = mapped_column(Integer)
    avg_heart_rate: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20), default="garmin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
