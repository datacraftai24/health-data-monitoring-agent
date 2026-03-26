"""Alert and glucose event models."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class GlucoseEvent(Base):
    __tablename__ = "glucose_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(30))  # crash, spike, prolonged_high, overnight_low
    glucose_value: Mapped[float | None] = mapped_column(Float)
    trigger_meal_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("meals.id"))
    trigger_activity_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("workouts.id"))
    was_predicted: Mapped[bool] = mapped_column(Boolean, default=False)
    was_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    alert_type: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[str | None] = mapped_column(String(10))  # critical, high, medium, low
    message: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str | None] = mapped_column(String(20))
    was_read: Mapped[bool] = mapped_column(Boolean, default=False)
    user_response: Mapped[str | None] = mapped_column(Text)
    glucose_at_alert: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
