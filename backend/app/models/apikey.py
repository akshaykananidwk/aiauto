from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZDateTime

# Scopes an API key can hold. "jobs:write" is required to submit work.
API_SCOPES = ["jobs:read", "jobs:write", "files:read", "webhooks:manage"]


class ApiKey(TimestampMixin, Base):
    """API key for the platform's OWN public REST API (X-API-Key header).

    Lets customers' websites, ERPs, CRMs and apps submit jobs that are
    processed by the central ChatGPT browser worker. Only a SHA-256 hash
    of the key is stored; the plain key is shown exactly once."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # display hint "ak_ab12…"
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # subset of API_SCOPES; None/empty = all scopes
    scopes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    # optional list of allowed client IPs (exact match); None/empty = any
    ip_allowlist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # per-key requests/minute; 0 = use the platform default
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
