"""Daily summary model."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_summary_user_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # Glucose stats
    glucose_avg: Mapped[float | None] = mapped_column(Float)
    glucose_min: Mapped[float | None] = mapped_column(Float)
    glucose_max: Mapped[float | None] = mapped_column(Float)
    time_in_range_pct: Mapped[float | None] = mapped_column(Float)
    time_below_range_pct: Mapped[float | None] = mapped_column(Float)
    time_above_range_pct: Mapped[float | None] = mapped_column(Float)
    crash_count: Mapped[int | None] = mapped_column(Integer)
    spike_count: Mapped[int | None] = mapped_column(Integer)

    # Activity stats
    total_steps: Mapped[int | None] = mapped_column(Integer)
    total_active_calories: Mapped[int | None] = mapped_column(Integer)
    workout_minutes: Mapped[int | None] = mapped_column(Integer)

    # Nutrition stats
    total_calories: Mapped[int | None] = mapped_column(Integer)
    total_protein_g: Mapped[float | None] = mapped_column(Float)
    total_carbs_g: Mapped[float | None] = mapped_column(Float)
    total_fat_g: Mapped[float | None] = mapped_column(Float)
    meals_logged: Mapped[int | None] = mapped_column(Integer)

    # Scores (0-100)
    glucose_score: Mapped[int | None] = mapped_column(Integer)
    nutrition_score: Mapped[int | None] = mapped_column(Integer)
    activity_score: Mapped[int | None] = mapped_column(Integer)
    overall_score: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
