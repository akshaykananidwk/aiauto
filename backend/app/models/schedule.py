from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZDateTime


class ScheduleType(str, enum.Enum):
    once = "once"
    interval = "interval"  # every N minutes
    daily = "daily"        # at HH:MM
    weekly = "weekly"      # weekday at HH:MM


class ScheduledPrompt(TimestampMixin, Base):
    __tablename__ = "scheduled_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    wants_image: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    schedule_type: Mapped[ScheduleType] = mapped_column(
        Enum(ScheduleType, name="schedule_type"), nullable=False
    )
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_at_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM" UTC
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0=Mon .. 6=Sun
    next_run_at: Mapped[datetime | None] = mapped_column(
        TZDateTime, nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_prompt_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
