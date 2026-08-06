from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def add(self, log: AuditLog) -> None:
        self.db.add(log)

    async def list(
        self,
        *,
        event: str | None = None,
        level: str | None = None,
        user_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        count_stmt = select(func.count(AuditLog.id))
        if event:
            stmt = stmt.where(AuditLog.event == event)
            count_stmt = count_stmt.where(AuditLog.event == event)
        if level:
            stmt = stmt.where(AuditLog.level == level)
            count_stmt = count_stmt.where(AuditLog.level == level)
        if user_id is not None:
            stmt = stmt.where(AuditLog.user_id == user_id)
            count_stmt = count_stmt.where(AuditLog.user_id == user_id)
        stmt = (
            stmt.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        total = (await self.db.execute(count_stmt)).scalar_one()
        return items, total
