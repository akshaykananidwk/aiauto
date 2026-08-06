"""Usage analytics: time series, per-user/department breakdowns, and
processing-time statistics for the central ChatGPT automation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.models.user import User


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def daily_series(self, days: int = 30) -> list[dict]:
        """Prompts per calendar day (UTC) for the last N days."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        day = func.date(Prompt.created_at)
        stmt = (
            select(day.label("day"), func.count(Prompt.id))
            .where(Prompt.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.db.execute(stmt)).all()
        by_day = {str(d): c for d, c in rows}
        out = []
        today = datetime.now(timezone.utc).date()
        for offset in range(days - 1, -1, -1):
            key = str(today - timedelta(days=offset))
            out.append({"day": key, "count": by_day.get(key, 0)})
        return out

    async def top_users(self, days: int = 30, limit: int = 10) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                User.username,
                User.full_name,
                User.department,
                func.count(Prompt.id).label("prompts"),
            )
            .join(Prompt, Prompt.user_id == User.id)
            .where(Prompt.created_at >= since)
            .group_by(User.id)
            .order_by(func.count(Prompt.id).desc())
            .limit(limit)
        )
        return [
            {
                "username": r.username,
                "full_name": r.full_name,
                "department": r.department,
                "prompts": r.prompts,
            }
            for r in (await self.db.execute(stmt)).all()
        ]

    async def by_department(self, days: int = 30) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(Prompt.department, func.count(Prompt.id))
            .where(Prompt.created_at >= since)
            .group_by(Prompt.department)
            .order_by(func.count(Prompt.id).desc())
        )
        return [
            {"department": d or "(none)", "prompts": c}
            for d, c in (await self.db.execute(stmt)).all()
        ]

    async def totals(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        count = (
            await self.db.execute(
                select(func.count(Prompt.id)).where(Prompt.created_at >= since)
            )
        ).scalar_one()
        images = (
            await self.db.execute(
                select(func.count(PromptFile.id))
                .join(Prompt, PromptFile.prompt_id == Prompt.id)
                .where(Prompt.created_at >= since,
                       PromptFile.kind == FileKind.result_image)
            )
        ).scalar_one()

        # average processing seconds for completed prompts
        secs = func.avg(
            cast(func.extract("epoch", Prompt.completed_at) -
                 func.extract("epoch", Prompt.started_at), Float)
        )
        try:
            avg_secs = (
                await self.db.execute(
                    select(secs).where(
                        Prompt.status == PromptStatus.completed,
                        Prompt.created_at >= since,
                        Prompt.started_at.isnot(None),
                        Prompt.completed_at.isnot(None),
                    )
                )
            ).scalar()
        except Exception:  # SQLite has no extract(epoch)
            avg_secs = None
        return {
            "prompts": count or 0,
            "images": images or 0,
            "avg_processing_seconds": round(float(avg_secs), 1) if avg_secs else None,
        }
