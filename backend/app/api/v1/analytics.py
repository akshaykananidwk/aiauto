"""Admin analytics: usage charts, cost tracking, token reports."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.repositories.audit import AuditRepository
from app.services.analytics import AnalyticsService
from app.services.cache import cache_get, cache_set

router = APIRouter(prefix="/admin/analytics", tags=["analytics"],
                   dependencies=[Depends(get_current_admin)])


@router.get("")
async def analytics_overview(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cache_key = f"analytics:{days}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    svc = AnalyticsService(db)
    result = {
        "days": days,
        "totals": await svc.totals(days),
        "daily": await svc.daily_series(min(days, 60)),
        "top_users": await svc.top_users(days),
        "by_department": await svc.by_department(days),
        "by_provider": await svc.by_provider(days),
    }
    await cache_set(cache_key, result, ttl_seconds=60)
    return result


@router.get("/audit-report")
async def audit_report_csv(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export the audit log as CSV."""
    items, _total = await AuditRepository(db).list(page=1, page_size=10000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "event", "level", "user_id", "message"])
    for log in items:
        writer.writerow([log.created_at.isoformat(), log.event, log.level,
                         log.user_id or "", log.message])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_report.csv"},
    )
