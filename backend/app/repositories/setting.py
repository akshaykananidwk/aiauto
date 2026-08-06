from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import AppSetting


class SettingRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str, default: Any = None) -> Any:
        row = await self.db.get(AppSetting, key)
        return row.value if row is not None else default

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        res = await self.db.execute(select(AppSetting).where(AppSetting.key.in_(keys)))
        return {row.key: row.value for row in res.scalars().all()}

    async def set(self, key: str, value: Any) -> None:
        row = await self.db.get(AppSetting, key)
        if row is None:
            self.db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
