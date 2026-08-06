"""Prompt quotas: per-user overrides > department quota > global default.
A limit of 0 (or NULL at every level) means unlimited. Cancelled prompts
do not count against quota."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.prompt import Prompt, PromptStatus
from app.models.quota import DepartmentQuota
from app.models.user import User


class QuotaExceededError(Exception):
    pass


class QuotaService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def effective_limits(self, user: User) -> tuple[int, int]:
        """Returns (daily, monthly); 0 = unlimited."""
        daily, monthly = user.daily_limit, user.monthly_limit
        if daily is None or monthly is None:
            dept = await self.db.get(DepartmentQuota, user.department) if user.department else None
            if daily is None:
                daily = dept.daily_limit if dept else None
            if monthly is None:
                monthly = dept.monthly_limit if dept else None
        if daily is None or monthly is None:
            # global defaults are admin-configurable (DB) over env defaults
            from app.repositories.setting import SettingRepository

            stored = await SettingRepository(self.db).get_many(
                ["app.default_daily_limit", "app.default_monthly_limit"]
            )
            if daily is None:
                daily = stored.get("app.default_daily_limit", self.settings.default_daily_limit)
            if monthly is None:
                monthly = stored.get("app.default_monthly_limit",
                                     self.settings.default_monthly_limit)
        return int(daily or 0), int(monthly or 0)

    async def _count_since(self, user_id: int, since: datetime) -> int:
        stmt = select(func.count(Prompt.id)).where(
            Prompt.user_id == user_id,
            Prompt.created_at >= since,
            Prompt.status != PromptStatus.cancelled,
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def usage(self, user: User) -> dict:
        now = datetime.now(timezone.utc)
        daily_limit, monthly_limit = await self.effective_limits(user)
        return {
            "daily_used": await self._count_since(user.id, now - timedelta(days=1)),
            "daily_limit": daily_limit,
            "monthly_used": await self._count_since(user.id, now - timedelta(days=30)),
            "monthly_limit": monthly_limit,
        }

    async def check(self, user: User) -> None:
        """Raises QuotaExceededError when submitting would exceed a limit."""
        info = await self.usage(user)
        if info["daily_limit"] and info["daily_used"] >= info["daily_limit"]:
            raise QuotaExceededError(
                f"daily prompt limit reached ({info['daily_used']}/{info['daily_limit']})"
            )
        if info["monthly_limit"] and info["monthly_used"] >= info["monthly_limit"]:
            raise QuotaExceededError(
                f"monthly prompt limit reached ({info['monthly_used']}/{info['monthly_limit']})"
            )
