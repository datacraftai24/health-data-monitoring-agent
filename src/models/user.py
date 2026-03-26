"""User profile model."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(Integer)

    # Health profile
    hba1c: Mapped[float | None] = mapped_column(Float)
    hba1c_date: Mapped[date | None] = mapped_column(Date)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)
    daily_calorie_target: Mapped[int | None] = mapped_column(Integer)
    daily_protein_target_g: Mapped[int | None] = mapped_column(Integer)

    # Glucose thresholds
    glucose_low_threshold: Mapped[float] = mapped_column(Float, default=3.9)
    glucose_high_threshold: Mapped[float] = mapped_column(Float, default=10.0)
    glucose_target_low: Mapped[float] = mapped_column(Float, default=3.9)
    glucose_target_high: Mapped[float] = mapped_column(Float, default=9.0)

    # Preferences
    preferred_channel: Mapped[str] = mapped_column(String(20), default="whatsapp")
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Toronto")

    # API tokens (encrypted at rest via DB-level encryption)
    libre_auth_token: Mapped[str | None] = mapped_column(String)
    libre_patient_id: Mapped[str | None] = mapped_column(String(50))
    garmin_oauth_token: Mapped[str | None] = mapped_column(String)
    garmin_oauth_secret: Mapped[str | None] = mapped_column(String)

    # Learned metabolic profile
    metabolic_profile: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
