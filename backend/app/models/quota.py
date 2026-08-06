from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TZDateTime, utcnow


class DepartmentQuota(Base):
    """Prompt limits per department. 0 means unlimited."""

    __tablename__ = "department_quotas"

    department: Mapped[str] = mapped_column(String(128), primary_key=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
