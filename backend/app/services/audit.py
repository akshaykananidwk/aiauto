from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditLog

logger = get_logger("audit")


async def audit(
    db: AsyncSession,
    event: str,
    message: str = "",
    *,
    user_id: int | None = None,
    level: str = "info",
    meta: dict[str, Any] | None = None,
    commit: bool = False,
) -> None:
    """Write an audit entry to the DB and application log."""
    db.add(AuditLog(user_id=user_id, event=event, level=level, message=message, meta=meta))
    log_fn = getattr(logger, level, logger.info)
    log_fn("%s | user=%s | %s", event, user_id, message)
    if commit:
        await db.commit()
