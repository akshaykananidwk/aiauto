"""Usage analytics: time series, per-user/department breakdowns, token
and cost reporting, processing-time statistics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
            select(day.label("day"), func.count(Prompt.id), func.sum(Prompt.cost_usd))
            .where(Prompt.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        rows = (await self.db.execute(stmt)).all()
        by_day = {str(d): {"count": c, "cost": round(float(cost or 0), 4)} for d, c, cost in rows}
        out = []
        today = datetime.now(timezone.utc).date()
        for offset in range(days - 1, -1, -1):
            key = str(today - timedelta(days=offset))
            entry = by_day.get(key, {"count": 0, "cost": 0})
            out.append({"day": key, **entry})
        return out

    async def top_users(self, days: int = 30, limit: int = 10) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                User.username,
                User.full_name,
                User.department,
                func.count(Prompt.id).label("prompts"),
                func.sum(Prompt.input_tokens + Prompt.output_tokens).label("tokens"),
                func.sum(Prompt.cost_usd).label("cost"),
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
                "tokens": int(r.tokens or 0),
                "cost": round(float(r.cost or 0), 4),
            }
            for r in (await self.db.execute(stmt)).all()
        ]

    async def by_department(self, days: int = 30) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                Prompt.department,
                func.count(Prompt.id),
                func.sum(Prompt.cost_usd),
            )
            .where(Prompt.created_at >= since)
            .group_by(Prompt.department)
            .order_by(func.count(Prompt.id).desc())
        )
        return [
            {"department": d or "(none)", "prompts": c, "cost": round(float(cost or 0), 4)}
            for d, c, cost in (await self.db.execute(stmt)).all()
        ]

    async def by_provider(self, days: int = 30) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                Prompt.provider,
                func.count(Prompt.id),
                func.sum(Prompt.input_tokens),
                func.sum(Prompt.output_tokens),
                func.sum(Prompt.cost_usd),
            )
            .where(Prompt.created_at >= since)
            .group_by(Prompt.provider)
        )
        return [
            {
                "provider": p or "(unset)",
                "prompts": c,
                "input_tokens": int(i or 0),
                "output_tokens": int(o or 0),
                "cost": round(float(cost or 0), 4),
            }
            for p, c, i, o, cost in (await self.db.execute(stmt)).all()
        ]

    async def totals(self, days: int = 30) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = select(
            func.count(Prompt.id),
            func.sum(Prompt.input_tokens),
            func.sum(Prompt.output_tokens),
            func.sum(Prompt.cost_usd),
        ).where(Prompt.created_at >= since)
        count, in_tok, out_tok, cost = (await self.db.execute(stmt)).one()

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
            "input_tokens": int(in_tok or 0),
            "output_tokens": int(out_tok or 0),
            "cost": round(float(cost or 0), 4),
            "avg_processing_seconds": round(float(avg_secs), 1) if avg_secs else None,
        }
