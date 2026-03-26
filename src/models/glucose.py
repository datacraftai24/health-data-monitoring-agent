"""Glucose reading model (TimescaleDB hypertable)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    glucose_mmol: Mapped[float] = mapped_column(Float, nullable=False)
    trend_arrow: Mapped[int | None] = mapped_column(Integer)  # 1-5
    is_high: Mapped[bool] = mapped_column(Boolean, default=False)
    is_low: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="libre")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
