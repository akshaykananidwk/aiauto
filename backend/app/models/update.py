from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, TZDateTime


class UpdateStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"
    rolled_back = "rolled_back"


class UpdateRecord(TimestampMixin, Base):
    __tablename__ = "update_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_commit: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    to_commit: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    status: Mapped[UpdateStatus] = mapped_column(
        Enum(UpdateStatus, name="update_status"), default=UpdateStatus.running, nullable=False
    )
    log: Mapped[str] = mapped_column(Text, default="", nullable=False)
    backup_path: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
