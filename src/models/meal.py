"""Meal log model."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meal_type: Mapped[str | None] = mapped_column(String(20))  # breakfast, lunch, dinner, snack
    description: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    items: Mapped[dict | None] = mapped_column(JSON)  # Array of food items with macros
    total_calories: Mapped[int | None] = mapped_column(Integer)
    total_protein_g: Mapped[float | None] = mapped_column(Float)
    total_carbs_g: Mapped[float | None] = mapped_column(Float)
    total_fat_g: Mapped[float | None] = mapped_column(Float)
    total_fiber_g: Mapped[float | None] = mapped_column(Float)
    avg_gi_score: Mapped[str | None] = mapped_column(String(10))  # low, medium, high
    predicted_spike: Mapped[float | None] = mapped_column(Float)
    actual_peak: Mapped[float | None] = mapped_column(Float)
    actual_peak_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
