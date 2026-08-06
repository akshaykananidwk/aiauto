"""System health, resource monitoring, worker registry, and manual
backup / restore management."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.queue import WORKERS_PREFIX
from app.services.redis_client import get_redis

logger = get_logger("system")

try:
    import psutil
except ImportError:  # psutil is optional; metrics degrade gracefully
    psutil = None


class SystemService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def health(self) -> dict:
        db_ok = redis_ok = False
        try:
            await self.db.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            pass
        try:
            redis_ok = bool(await get_redis().ping())
        except Exception:
            pass

        cpu = mem = None
        if psutil is not None:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
            except Exception:
                pass

        disk_total, disk_used, disk_free = shutil.disk_usage(self.settings.root_dir)
        return {
            "database_ok": db_ok,
            "redis_ok": redis_ok,
            "cpu_percent": cpu,
            "memory_percent": mem,
            "disk_total_gb": round(disk_total / 1024**3, 1),
            "disk_used_percent": round(disk_used / disk_total * 100, 1),
            "disk_free_gb": round(disk_free / 1024**3, 1),
            "workers": await self.workers(),
        }

    async def workers(self) -> list[dict]:
        """All workers that have sent a heartbeat recently."""
        out = []
        try:
            redis = get_redis()
            async for key in redis.scan_iter(f"{WORKERS_PREFIX}*", count=100):
                worker_id = key.removeprefix(WORKERS_PREFIX)
                raw = await redis.hgetall(key)
                out.append({
                    "id": worker_id,
                    "heartbeat": raw.get("heartbeat"),
                    "provider": raw.get("provider", ""),
                    "chrome": raw.get("chrome", "unknown"),
                    "current_job": raw.get("current_job") or None,
                })
        except Exception as exc:
            logger.warning("worker scan failed: %s", exc)
        return sorted(out, key=lambda w: w["id"])

    # ---- backups ----

    def list_backups(self) -> list[dict]:
        backup_dir = self.settings.backup_path
        out = []
        for path in sorted(backup_dir.glob("backup_*.zip"), reverse=True):
            stat = path.stat()
            out.append({
                "name": path.name,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        for path in sorted(backup_dir.glob("db_*.sql"), reverse=True):
            stat = path.stat()
            out.append({
                "name": path.name,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        return out

    def resolve_backup(self, name: str) -> Path:
        """Resolve a backup by bare filename, refusing traversal."""
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError("invalid backup name")
        path = self.settings.backup_path / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path

    async def create_backup(self) -> dict:
        import asyncio

        from app.services.update import UpdateService

        svc = UpdateService(self.db)
        cfg = await svc.get_config()
        zip_path = await asyncio.to_thread(
            svc._backup_code, self.settings.backup_path, cfg["protected_paths"])
        db_dump = await asyncio.to_thread(svc._backup_database, self.settings.backup_path)
        return {"backup": zip_path.name, "db_dump": db_dump.name if db_dump else None}

    async def restore_backup(self, name: str) -> dict:
        """Restore code files from a named backup zip (protected paths are
        untouched — they were never inside the archive)."""
        import asyncio

        from app.services.update import UpdateService

        path = self.resolve_backup(name)
        if not path.name.endswith(".zip"):
            raise ValueError("only .zip code backups can be restored automatically; "
                             "restore db_* database backups with psql / file copy")
        svc = UpdateService(self.db)
        cfg = await svc.get_config()
        restored = await asyncio.to_thread(svc._rollback_files, path, cfg["protected_paths"])
        logger.warning("restored %s files from backup %s", restored, name)
        return {"restored_files": restored, "backup": name}
