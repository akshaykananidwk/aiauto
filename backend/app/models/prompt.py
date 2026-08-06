from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, TZDateTime


class PromptStatus(str, enum.Enum):
    waiting = "waiting"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


def _new_id() -> str:
    return uuid.uuid4().hex


class Prompt(TimestampMixin, Base):
    __tablename__ = "prompts"
    __table_args__ = (Index("ix_prompts_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PromptStatus] = mapped_column(
        Enum(PromptStatus, name="prompt_status"),
        default=PromptStatus.waiting,
        index=True,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # higher = sooner
    wants_image: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # request context, captured at submission time
    computer_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # AI provider used and usage accounting (token counts are estimates
    # for the browser provider, exact for API providers)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    scheduled_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    user = relationship("User", back_populates="prompts", lazy="joined")
    files = relationship(
        "PromptFile", back_populates="prompt", lazy="selectin", cascade="all, delete-orphan"
    )
