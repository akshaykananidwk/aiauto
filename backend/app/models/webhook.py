from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZDateTime

WEBHOOK_EVENTS = [
    "job.submitted",
    "job.started",
    "job.completed",
    "job.failed",
    "image.ready",
    "file.ready",
]


class Webhook(TimestampMixin, Base):
    """Outbound webhook registered by a user. Deliveries are signed with
    HMAC-SHA256 (X-AIAuto-Signature) and retried with backoff."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    # signing secret, encrypted at rest (Fernet)
    secret_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    # subset of WEBHOOK_EVENTS; None/empty = all events
    events: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_delivery_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
