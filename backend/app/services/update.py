"""One-click GitHub auto-update system.

Once the repository, branch and token are saved (Admin → Update page),
no manual file upload is ever needed again:

  * "Check for Update"  → queries the GitHub API and reports the new
    version, commit messages, authors and dates.
  * "Update Now"        → full pipeline:
        1. take an automatic backup (code zip + optional pg_dump)
        2. download the branch tarball from GitHub
        3. safely extract and copy files over the installation,
           NEVER touching protected paths (.env, config.php, uploads/,
           storage/, backups/, ...)
        4. run database migrations (alembic upgrade head)
        5. clear the Redis cache
        6. record the new commit — and on ANY error, automatically
           roll back the files from the backup.

Progress is streamed over the WebSocket event bus (update.progress).
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR, ROOT_DIR, get_settings
from app.core.logging import get_logger
from app.core.security import decrypt_secret, encrypt_secret
from app.models.update import UpdateRecord, UpdateStatus
from app.repositories.setting import SettingRepository
from app.services import events
from app.services.queue import QueueService

logger = get_logger("update")

GITHUB_API = "https://api.github.com"

# Settings keys in the app_settings table
KEY_REPO = "update.repo"
KEY_BRANCH = "update.branch"
KEY_TOKEN = "update.token_encrypted"
KEY_PROTECTED = "update.protected_paths"
KEY_AUTO_RESTART = "update.auto_restart"
KEY_CURRENT_COMMIT = "update.current_commit"

# In-process live status for the admin UI
_run_state: dict = {"running": False, "step": "", "progress": 0, "log": []}


def run_state() -> dict:
    return {
        "running": _run_state["running"],
        "step": _run_state["step"],
        "progress": _run_state["progress"],
        "log_tail": _run_state["log"][-40:],
    }


def is_protected(rel_path: str, protected: list[str]) -> bool:
    """True if rel_path (posix, relative to repo root) is inside a protected path."""
    rel = rel_path.strip("/").replace("\\", "/")
    for p in protected:
        p = p.strip("/").replace("\\", "/")
        if not p:
            continue
        if rel == p or rel.startswith(p + "/"):
            return True
    return False


def safe_extract_tar(data: bytes, dest: Path) -> Path:
    """Extract a GitHub tarball, guarding against path traversal.
    Returns the single top-level directory GitHub puts everything under."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise RuntimeError(f"unsafe path in archive: {member.name}")
            if member.issym() or member.islnk():
                continue
        tar.extractall(dest, filter="data")
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("unexpected archive layout")
    return roots[0]


class UpdateService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings_repo = SettingRepository(db)
        self.app_settings = get_settings()

    # ---------------- configuration ----------------

    async def get_config(self) -> dict:
        stored = await self.settings_repo.get_many(
            [KEY_REPO, KEY_BRANCH, KEY_TOKEN, KEY_PROTECTED, KEY_AUTO_RESTART, KEY_CURRENT_COMMIT]
        )
        repo = stored.get(KEY_REPO) or self.app_settings.github_repo
        branch = stored.get(KEY_BRANCH) or self.app_settings.github_branch
        token_enc = stored.get(KEY_TOKEN) or ""
        token = decrypt_secret(token_enc) if token_enc else self.app_settings.github_token
        protected = stored.get(KEY_PROTECTED) or self.app_settings.protected_paths
        auto_restart = stored.get(KEY_AUTO_RESTART)
        if auto_restart is None:
            auto_restart = self.app_settings.update_auto_restart
        return {
            "repo": repo,
            "branch": branch,
            "token": token,
            "protected_paths": protected,
            "auto_restart": bool(auto_restart),
            "current_commit": stored.get(KEY_CURRENT_COMMIT) or "",
        }

    async def save_config(
        self,
        repo: str,
        branch: str,
        token: str,
        protected_paths: list[str] | None,
        auto_restart: bool | None,
    ) -> None:
        await self.settings_repo.set(KEY_REPO, repo)
        await self.settings_repo.set(KEY_BRANCH, branch)
        if token:  # empty means "keep existing"
            await self.settings_repo.set(KEY_TOKEN, encrypt_secret(token))
        if protected_paths is not None:
            # never allow removing the critical entries
            required = {".env", "storage", "backups", "uploads", "config.php"}
            merged = sorted(required | {p.strip().strip("/") for p in protected_paths if p.strip()})
            await self.settings_repo.set(KEY_PROTECTED, merged)
        if auto_restart is not None:
            await self.settings_repo.set(KEY_AUTO_RESTART, bool(auto_restart))
        await self.db.commit()

    def current_version(self) -> str:
        vf = ROOT_DIR / "VERSION"
        return vf.read_text(encoding="utf-8").strip() if vf.exists() else ""

    # ---------------- GitHub API ----------------

    def _client(self, token: str) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aiauto-updater",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=60,
                                 follow_redirects=True)

    async def check(self) -> dict:
        cfg = await self.get_config()
        if not cfg["repo"]:
            raise ValueError("Update not configured: set repository, branch and token first")
        async with self._client(cfg["token"]) as client:
            r = await client.get(f"/repos/{cfg['repo']}/branches/{cfg['branch']}")
            r.raise_for_status()
            latest = r.json()["commit"]
            latest_sha = latest["sha"]

            latest_version = ""
            vr = await client.get(
                f"/repos/{cfg['repo']}/contents/VERSION", params={"ref": cfg["branch"]}
            )
            if vr.status_code == 200 and vr.json().get("encoding") == "base64":
                import base64

                latest_version = base64.b64decode(vr.json()["content"]).decode().strip()

            current = cfg["current_commit"]
            commits: list[dict] = []
            behind = 0
            if current and current != latest_sha:
                cr = await client.get(f"/repos/{cfg['repo']}/compare/{current}...{latest_sha}")
                if cr.status_code == 200:
                    cmp_data = cr.json()
                    behind = cmp_data.get("ahead_by", 0)
                    commits = [
                        {
                            "sha": c["sha"][:10],
                            "message": c["commit"]["message"].split("\n")[0][:200],
                            "author": c["commit"]["author"]["name"],
                            "date": c["commit"]["author"]["date"],
                        }
                        for c in cmp_data.get("commits", [])[-30:]
                    ]
            elif not current:
                behind = 1
                commits = [
                    {
                        "sha": latest_sha[:10],
                        "message": latest["commit"]["message"].split("\n")[0][:200],
                        "author": latest["commit"]["author"]["name"],
                        "date": latest["commit"]["author"]["date"],
                    }
                ]

        return {
            "update_available": current != latest_sha,
            "current_commit": current,
            "current_version": self.current_version(),
            "latest_commit": latest_sha,
            "latest_version": latest_version,
            "commits_behind": behind,
            "commits": commits,
        }

    # ---------------- update pipeline ----------------

    async def _progress(self, step: str, progress: int, message: str) -> None:
        _run_state.update({"step": step, "progress": progress})
        _run_state["log"].append(f"[{datetime.now(timezone.utc):%H:%M:%S}] {message}")
        logger.info("update: %s (%s%%) %s", step, progress, message)
        try:
            await events.publish(
                events.UPDATE_PROGRESS,
                {"step": step, "progress": progress, "message": message},
                admin_only=True,
            )
        except Exception:
            pass  # realtime updates are best-effort

    def _backup_code(self, backup_dir: Path, protected: list[str]) -> Path:
        """Zip everything that the update may overwrite (i.e. non-protected files)."""
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_path = backup_dir / f"backup_{stamp}.zip"
        skip_always = {".git", "backups", "frontend/node_modules", "logs"}
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in ROOT_DIR.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(ROOT_DIR).as_posix()
                if is_protected(rel, protected) or is_protected(rel, list(skip_always)):
                    continue
                if "__pycache__" in rel:
                    continue
                zf.write(path, rel)
        return zip_path

    def _backup_database(self, backup_dir: Path) -> Path | None:
        """Best-effort pg_dump; returns dump path or None (e.g. SQLite / no pg_dump)."""
        url = self.app_settings.database_url
        if not url.startswith("postgresql"):
            return None
        if shutil.which("pg_dump") is None:
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dump_path = backup_dir / f"db_{stamp}.sql"
        dsn = url.replace("+asyncpg", "")
        try:
            with open(dump_path, "wb") as fh:
                subprocess.run(["pg_dump", "--dbname", dsn], stdout=fh, check=True, timeout=600)
            return dump_path
        except Exception as exc:
            logger.warning("pg_dump failed (continuing without DB dump): %s", exc)
            dump_path.unlink(missing_ok=True)
            return None

    def _apply_files(self, src_root: Path, protected: list[str]) -> int:
        """Copy new files over the installation, skipping protected paths."""
        copied = 0
        for path in src_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(src_root).as_posix()
            if is_protected(rel, protected) or rel.startswith(".git/"):
                continue
            dest = ROOT_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied += 1
        return copied

    def _rollback_files(self, backup_zip: Path, protected: list[str]) -> int:
        restored = 0
        with zipfile.ZipFile(backup_zip) as zf:
            for name in zf.namelist():
                if is_protected(name, protected):
                    continue
                target = (ROOT_DIR / name).resolve()
                if not str(target).startswith(str(ROOT_DIR.resolve())):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
        return restored

    def _run_migrations(self) -> str:
        """alembic upgrade head, executed in the backend directory."""
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise RuntimeError(f"database migration failed:\n{output[-2000:]}")
        return output

    def _prune_backups(self, backup_dir: Path, keep: int = 10) -> None:
        backups = sorted(backup_dir.glob("backup_*.zip"), reverse=True)
        for old in backups[keep:]:
            old.unlink(missing_ok=True)

    async def run_update(self) -> UpdateRecord:
        if _run_state["running"]:
            raise RuntimeError("an update is already running")
        _run_state.update({"running": True, "step": "starting", "progress": 0, "log": []})

        cfg = await self.get_config()
        record = UpdateRecord(from_commit=cfg["current_commit"], status=UpdateStatus.running)
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)

        backup_zip: Path | None = None
        protected = cfg["protected_paths"]
        try:
            check = await self.check()
            if not check["update_available"]:
                raise RuntimeError("already up to date")
            target_sha = check["latest_commit"]
            record.to_commit = target_sha

            await self._progress("backup", 10, "Creating automatic backup…")
            backup_zip = self._backup_code(self.app_settings.backup_path, protected)
            db_dump = self._backup_database(self.app_settings.backup_path)
            record.backup_path = str(backup_zip)
            await self._progress(
                "backup", 25,
                f"Backup ready: {backup_zip.name}" + (f" + {db_dump.name}" if db_dump else ""),
            )

            await self._progress("download", 30, f"Downloading {cfg['repo']}@{target_sha[:10]}…")
            async with self._client(cfg["token"]) as client:
                r = await client.get(f"/repos/{cfg['repo']}/tarball/{target_sha}")
                r.raise_for_status()
                tar_bytes = r.content
            await self._progress("download", 50, f"Downloaded {len(tar_bytes) // 1024} KiB")

            await self._progress("extract", 55, "Extracting and applying files…")
            tmp_dir = self.app_settings.backup_path / "_incoming"
            shutil.rmtree(tmp_dir, ignore_errors=True)
            src_root = safe_extract_tar(tar_bytes, tmp_dir)
            copied = self._apply_files(src_root, protected)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            await self._progress("apply", 70, f"Applied {copied} files (protected paths untouched)")

            await self._progress("migrate", 80, "Running database migrations…")
            migration_log = await asyncio.to_thread(self._run_migrations)
            await self._progress("migrate", 88, "Migrations complete")

            await self._progress("cache", 92, "Clearing cache…")
            cleared = await QueueService().clear_cache()
            await self._progress("cache", 95, f"Cleared {cleared} cache keys")

            await self.settings_repo.set(KEY_CURRENT_COMMIT, target_sha)
            record.status = UpdateStatus.success
            record.version = check["latest_version"] or self.current_version()
            record.log = "\n".join(_run_state["log"]) + "\n--- migrations ---\n" + migration_log[-4000:]
            record.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            self._prune_backups(self.app_settings.backup_path)
            await self._progress("done", 100, f"Update to {target_sha[:10]} successful ✔")

            if cfg["auto_restart"]:
                await self._progress("restart", 100, "Restarting service…")
                loop = asyncio.get_running_loop()
                loop.call_later(2, os._exit, 0)  # service manager restarts us
            return record

        except Exception as exc:
            logger.exception("update failed")
            await self._progress("error", 0, f"Update failed: {exc}")
            if backup_zip and backup_zip.exists():
                try:
                    restored = self._rollback_files(backup_zip, protected)
                    record.status = UpdateStatus.rolled_back
                    await self._progress(
                        "rolled_back", 0, f"Rolled back {restored} files from {backup_zip.name}"
                    )
                except Exception as rb_exc:
                    record.status = UpdateStatus.failed
                    await self._progress("rollback_failed", 0, f"Rollback failed: {rb_exc}")
            else:
                record.status = UpdateStatus.failed
            record.log = "\n".join(_run_state["log"])
            record.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise
        finally:
            _run_state["running"] = False
