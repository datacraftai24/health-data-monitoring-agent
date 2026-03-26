"""Learned food response patterns model."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class FoodResponse(Base):
    __tablename__ = "food_responses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    food_name: Mapped[str | None] = mapped_column(String(100))
    food_category: Mapped[str | None] = mapped_column(String(50))
    avg_peak_glucose: Mapped[float | None] = mapped_column(Float)
    avg_time_to_peak_min: Mapped[int | None] = mapped_column(Integer)
    avg_time_to_baseline_min: Mapped[int | None] = mapped_column(Integer)
    crash_probability: Mapped[float | None] = mapped_column(Float)  # 0.0 - 1.0
    sample_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_eaten: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
