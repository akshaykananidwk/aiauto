"""Runtime-configurable admin settings, persisted in the app_settings table
and merged over the .env defaults."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.setting import SettingRepository
from app.schemas.settings import AdminSettings, AdminSettingsUpdate

PREFIX = "app."


class AppSettingsService:
    def __init__(self, db: AsyncSession):
        self.repo = SettingRepository(db)
        self.db = db

    async def get(self) -> AdminSettings:
        env = get_settings()
        defaults = AdminSettings(
            max_concurrent_jobs=env.max_concurrent_jobs,
            max_queue_size=env.max_queue_size,
            job_retry_count=env.job_retry_count,
            job_timeout_seconds=env.job_timeout_seconds,
            response_timeout_seconds=env.response_timeout_seconds,
            storage_limit_gb=env.storage_limit_gb,
            download_dir=env.results_dir,
            browser_profile_path=env.chrome_profile_dir,
            delete_conversations_after_run=env.delete_conversations_after_run,
            default_daily_limit=env.default_daily_limit,
            default_monthly_limit=env.default_monthly_limit,
        )
        stored = await self.repo.get_many([PREFIX + k for k in defaults.model_dump()])
        merged = defaults.model_dump()
        for key, value in stored.items():
            merged[key.removeprefix(PREFIX)] = value
        return AdminSettings(**merged)

    async def effective(self) -> AdminSettings:
        """Merged settings with a short Redis cache — this is what
        enforcement paths (queue caps, timeouts, worker) must read so that
        admin panel changes take effect without a restart."""
        from app.services.cache import cache_get, cache_set

        cached = await cache_get("admin_settings")
        if cached is not None:
            try:
                return AdminSettings(**cached)
            except Exception:
                pass
        merged = await self.get()
        await cache_set("admin_settings", merged.model_dump(), ttl_seconds=15)
        return merged

    async def update(self, patch: AdminSettingsUpdate) -> AdminSettings:
        from app.services.cache import cache_delete

        for key, value in patch.model_dump(exclude_none=True).items():
            await self.repo.set(PREFIX + key, value)
        await self.db.commit()
        await cache_delete("admin_settings")
        return await self.get()
