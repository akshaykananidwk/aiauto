"""One-click GitHub auto-update system.

Once the repository, branch and token are saved (Admin → Update page),
no manual file upload is ever needed again:

  * "Check for Update"  → queries the GitHub API and reports the new
    version, commit messages, authors and dates.
  * "Update Now"        → full pipeline:
        1. take an automatic backup (code zip + database backup)
        2. download the branch tarball from GitHub
        3. safely extract and copy files over the installation,
           NEVER touching protected paths (.env, config.php, uploads/,
           storage/, backups/, plugins/, ...)
        4. install changed Python dependencies (pip) and rebuild the
           frontend when its sources changed
        5. run database migrations (alembic upgrade head)
        6. clear the Redis cache (best-effort)
        7. record the new commit — and on ANY error, automatically
           roll back: database migrations are downgraded to the
           pre-update revision, then files are restored from the backup.

Blocking work (zip, pg_dump, extract, pip, npm, alembic) runs in worker
threads so the API stays responsive during an update. Progress is
streamed over the WebSocket event bus (update.progress).
"""
from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
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


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest() if path.exists() else ""


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
            required = {".env", "storage", "backups", "uploads", "config.php", "plugins"}
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

    # ---------------- update pipeline helpers ----------------

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
        skip_always = {".git", "backups", "frontend/node_modules", "frontend/dist", "logs",
                       "backend/.venv"}
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
        """Database backup before migrating.

        SQLite: copy the database file (failure is FATAL — aborts the update).
        PostgreSQL: pg_dump when available (failure is FATAL; a missing
        pg_dump binary only logs a warning so container deployments that
        dump externally still work)."""
        url = self.app_settings.database_url
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if url.startswith("sqlite"):
            db_file = Path(url.split("///", 1)[-1])
            if db_file.exists():
                dump_path = backup_dir / f"db_{stamp}.sqlite"
                shutil.copy2(db_file, dump_path)
                return dump_path
            return None
        if not url.startswith("postgresql"):
            return None
        if shutil.which("pg_dump") is None:
            logger.warning("pg_dump not found — continuing WITHOUT a database backup")
            return None
        dump_path = backup_dir / f"db_{stamp}.sql"
        dsn = url.replace("+asyncpg", "")
        try:
            with open(dump_path, "wb") as fh:
                subprocess.run(["pg_dump", "--dbname", dsn], stdout=fh, check=True, timeout=600)
            return dump_path
        except Exception as exc:
            dump_path.unlink(missing_ok=True)
            raise RuntimeError(f"database backup (pg_dump) failed: {exc}") from exc

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

    def _run_alembic(self, *args: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise RuntimeError(f"alembic {' '.join(args)} failed:\n{output[-2000:]}")
        return output

    def _alembic_current(self) -> str | None:
        """Current DB revision. '' = genuinely unversioned DB;
        None = could not determine (do NOT downgrade blindly in that case,
        'downgrade base' on a versioned DB would destroy the schema)."""
        try:
            output = self._run_alembic("current")
            for line in output.splitlines():
                line = line.strip()
                if line and not line.startswith(("INFO", "WARN")):
                    return line.split(" ")[0]
            return ""
        except Exception as exc:
            logger.warning("could not read current alembic revision: %s", exc)
            return None

    def _install_python_deps(self) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=BACKEND_DIR, capture_output=True, text=True, timeout=1500,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            raise RuntimeError(f"pip install failed:\n{output[-2000:]}")
        return output

    def _rebuild_frontend(self) -> str | None:
        """npm install + build when npm is available; None when it isn't
        (e.g. the Docker backend container — its frontend image is built
        separately)."""
        npm = shutil.which("npm")
        frontend = ROOT_DIR / "frontend"
        if npm is None or not frontend.is_dir():
            return None
        for args in (["install", "--no-audit", "--no-fund"], ["run", "build"]):
            result = subprocess.run([npm, *args], cwd=frontend,
                                    capture_output=True, text=True, timeout=1500)
            if result.returncode != 0:
                raise RuntimeError(
                    f"frontend build failed (npm {' '.join(args)}):\n"
                    f"{(result.stdout or '') + (result.stderr or '')[-1500:]}"
                )
        return "frontend rebuilt"

    async def _prune_backups(self, backup_dir: Path) -> None:
        keep = 10
        try:
            from app.services.app_settings import AppSettingsService

            keep = (await AppSettingsService(self.db).effective()).backup_keep_count
        except Exception:
            pass
        for pattern in ("backup_*.zip", "db_*.sql", "db_*.sqlite"):
            for old in sorted(backup_dir.glob(pattern), reverse=True)[keep:]:
                old.unlink(missing_ok=True)

    def _assert_sane_root(self) -> None:
        """Refuse to run against a mislaid installation — updating from
        ROOT_DIR='/' would back up and overwrite the wrong tree."""
        if str(ROOT_DIR) in ("/", ""):
            raise RuntimeError(
                "updater refused: repository root resolves to '/' — set AIAUTO_ROOT "
                "to the installation directory (see docs/DEPLOYMENT.md)"
            )
        if not (ROOT_DIR / "VERSION").exists() and not (ROOT_DIR / ".env.example").exists():
            raise RuntimeError(
                f"updater refused: {ROOT_DIR} does not look like an AIAuto installation "
                "(no VERSION/.env.example marker) — set AIAUTO_ROOT correctly"
            )

    # ---------------- update pipeline ----------------

    async def run_update(self) -> UpdateRecord:
        if _run_state["running"]:
            raise RuntimeError("an update is already running")
        _run_state.update({"running": True, "step": "starting", "progress": 0, "log": []})

        record: UpdateRecord | None = None
        backup_zip: Path | None = None
        protected: list[str] = []
        cfg: dict = {}
        pre_update_revision: str | None = ""
        migrations_ran = False
        deps_installed = False
        update_committed = False
        try:
            # everything — including the sanity guard — runs inside this
            # try so the finally always releases the running flag
            self._assert_sane_root()
            cfg = await self.get_config()
            protected = cfg["protected_paths"]
            record = UpdateRecord(from_commit=cfg["current_commit"],
                                  status=UpdateStatus.running)
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)

            check = await self.check()
            if not check["update_available"]:
                raise RuntimeError("already up to date")
            target_sha = check["latest_commit"]
            record.to_commit = target_sha

            await self._progress("backup", 8, "Creating automatic backup…")
            backup_zip = await asyncio.to_thread(
                self._backup_code, self.app_settings.backup_path, protected)
            db_dump = await asyncio.to_thread(
                self._backup_database, self.app_settings.backup_path)
            record.backup_path = str(backup_zip)
            await self._progress(
                "backup", 20,
                f"Backup ready: {backup_zip.name}" + (f" + {db_dump.name}" if db_dump else ""),
            )

            await self._progress("download", 25, f"Downloading {cfg['repo']}@{target_sha[:10]}…")
            async with self._client(cfg["token"]) as client:
                r = await client.get(f"/repos/{cfg['repo']}/tarball/{target_sha}")
                r.raise_for_status()
                tar_bytes = r.content
            await self._progress("download", 40, f"Downloaded {len(tar_bytes) // 1024} KiB")

            await self._progress("extract", 45, "Extracting and applying files…")
            req_hash_before = _file_hash(BACKEND_DIR / "requirements.txt")
            tmp_dir = self.app_settings.backup_path / "_incoming"
            shutil.rmtree(tmp_dir, ignore_errors=True)
            src_root = await asyncio.to_thread(safe_extract_tar, tar_bytes, tmp_dir)
            copied = await asyncio.to_thread(self._apply_files, src_root, protected)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            await self._progress("apply", 55, f"Applied {copied} files (protected paths untouched)")

            if _file_hash(BACKEND_DIR / "requirements.txt") != req_hash_before:
                await self._progress("deps", 60, "requirements.txt changed — installing "
                                                "Python dependencies…")
                await asyncio.to_thread(self._install_python_deps)
                deps_installed = True
                await self._progress("deps", 68, "Python dependencies installed")

            frontend_note = await asyncio.to_thread(self._rebuild_frontend)
            if frontend_note:
                await self._progress("frontend", 72, frontend_note)

            await self._progress("migrate", 78, "Running database migrations…")
            pre_update_revision = await asyncio.to_thread(self._alembic_current)
            # set BEFORE upgrading: a mid-chain migration failure must still
            # trigger a downgrade of the partially-applied chain
            migrations_ran = True
            migration_log = await asyncio.to_thread(self._run_alembic, "upgrade", "head")
            await self._progress("migrate", 86, "Migrations complete")

            # durable success FIRST; everything after this is best-effort
            await self.settings_repo.set(KEY_CURRENT_COMMIT, target_sha)
            record.status = UpdateStatus.success
            record.version = check["latest_version"] or self.current_version()
            record.log = "\n".join(_run_state["log"]) + \
                "\n--- migrations ---\n" + migration_log[-4000:]
            record.finished_at = datetime.now(timezone.utc)
            await self.db.commit()
            update_committed = True

            # post-commit tail: nothing here may trigger the rollback path
            try:
                await self._progress("cache", 92, "Clearing cache…")
                cleared = await QueueService().clear_cache()
                await self._progress("cache", 95, f"Cleared {cleared} cache keys")
            except Exception as exc:
                await self._progress("cache", 95, f"Cache clear skipped (non-fatal): {exc}")
            try:
                await self._prune_backups(self.app_settings.backup_path)
                await self._progress("done", 100, f"Update to {target_sha[:10]} successful ✔")
                if cfg["auto_restart"]:
                    await self._progress("restart", 100, "Restarting service…")
                    loop = asyncio.get_running_loop()
                    loop.call_later(2, os._exit, 0)  # service manager restarts us
            except Exception as exc:
                logger.warning("post-update housekeeping failed (non-fatal): %s", exc)
            return record

        except Exception as exc:
            logger.exception("update failed")
            await self._progress("error", 0, f"Update failed: {exc}")
            if update_committed:
                # the update itself already succeeded durably — never roll it
                # back because of a post-commit hiccup
                raise
            rollback_ok = True

            if migrations_ran:
                # migrations must be reverted BEFORE restoring old files —
                # the new migration scripts are still on disk right now
                if pre_update_revision is None:
                    # unknown starting revision: downgrading blindly could
                    # destroy a versioned schema — require manual restore
                    rollback_ok = False
                    await self._progress(
                        "rollback_failed", 0,
                        "Pre-update DB revision unknown — automatic downgrade skipped. "
                        "Restore the db_* backup from backups/ manually.",
                    )
                else:
                    target_rev = pre_update_revision or "base"
                    try:
                        await asyncio.to_thread(self._run_alembic, "downgrade", target_rev)
                        await self._progress("rolled_back", 0,
                                             f"Database downgraded to {target_rev}")
                    except Exception as db_exc:
                        rollback_ok = False
                        await self._progress(
                            "rollback_failed", 0,
                            f"DATABASE DOWNGRADE FAILED — schema may be ahead of code. "
                            f"Restore the db backup from backups/. Error: {db_exc}",
                        )

            if backup_zip and backup_zip.exists():
                try:
                    restored = await asyncio.to_thread(
                        self._rollback_files, backup_zip, protected)
                    await self._progress(
                        "rolled_back", 0, f"Rolled back {restored} files from {backup_zip.name}"
                    )
                    if deps_installed:
                        try:
                            await asyncio.to_thread(self._install_python_deps)
                            await self._progress("rolled_back", 0,
                                                 "Reinstalled original dependencies")
                        except Exception as pip_exc:
                            rollback_ok = False
                            await self._progress("rollback_failed", 0,
                                                 f"Dependency reinstall failed: {pip_exc}")
                except Exception as rb_exc:
                    rollback_ok = False
                    await self._progress("rollback_failed", 0, f"File rollback failed: {rb_exc}")
            else:
                rollback_ok = False

            if record is not None:
                await self.db.rollback()  # clear any failed transaction state
                record.status = UpdateStatus.rolled_back if rollback_ok else UpdateStatus.failed
                record.log = "\n".join(_run_state["log"])
                record.finished_at = datetime.now(timezone.utc)
                self.db.add(record)
                await self.db.commit()
            raise
        finally:
            _run_state["running"] = False
