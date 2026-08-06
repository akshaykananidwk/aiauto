#!/usr/bin/env python3
"""AIAuto one-command setup.

    python scripts/setup.py [--admin-password X] [--skip-frontend] [--dev]

Steps (all idempotent — safe to re-run):
  1. verify system requirements (Python, Node, disk space)
  2. create backend virtual environment + install Python packages
  3. create .env from .env.example with a generated SECRET_KEY
  4. create runtime folders (storage, uploads, results, backups, logs, plugins)
  5. run database migrations (alembic upgrade head, with create_all fallback)
  6. seed the initial admin account
  7. install Node packages and build the frontend
  8. run a doctor check (DB, Redis, config) and print next steps
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WINDOWS = os.name == "nt"
VENV_DIR = BACKEND / ".venv"
VENV_BIN = VENV_DIR / ("Scripts" if IS_WINDOWS else "bin")
VENV_PY = VENV_BIN / ("python.exe" if IS_WINDOWS else "python")

OK, WARN, FAIL = "✔", "⚠", "✘"
errors: list[str] = []
warnings: list[str] = []


def step(title: str) -> None:
    print(f"\n=== {title} ===")


def ok(msg: str) -> None:
    print(f"  {OK} {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  {WARN} {msg}")


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  {FAIL} {msg}")


def run(cmd: list[str], cwd: Path | None = None, quiet: bool = True) -> bool:
    try:
        result = subprocess.run(
            [str(c) for c in cmd], cwd=cwd or ROOT,
            capture_output=quiet, text=True, timeout=1800,
        )
        if result.returncode != 0:
            if quiet and result.stderr:
                print(result.stderr[-1500:])
            return False
        return True
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        return False


def check_requirements() -> None:
    step("1/8 System requirements")
    if sys.version_info < (3, 11):
        fail(f"Python 3.11+ required (found {sys.version.split()[0]})")
    else:
        ok(f"Python {sys.version.split()[0]}")
    node = shutil.which("node")
    if node:
        version = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()
        ok(f"Node {version}")
    else:
        warn("Node.js not found — frontend build will be skipped "
             "(install Node 18+ and re-run, or use the Docker stack)")
    free_gb = shutil.disk_usage(ROOT).free / 1024**3
    if free_gb < 2:
        warn(f"only {free_gb:.1f} GB free disk space")
    else:
        ok(f"{free_gb:.0f} GB free disk space")


def create_venv() -> None:
    step("2/8 Python virtual environment")
    if not VENV_PY.exists():
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        ok(f"created {VENV_DIR}")
    else:
        ok("virtual environment exists")
    print("  installing Python packages (this can take a few minutes)…")
    req = "requirements-dev.txt" if ARGS.dev else "requirements.txt"
    if run([VENV_PY, "-m", "pip", "install", "-q", "-r", req], cwd=BACKEND):
        ok("Python packages installed")
    else:
        fail("pip install failed — check your internet connection and re-run")


def create_env_file() -> None:
    step("3/8 Configuration (.env)")
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if env_path.exists():
        ok(".env already exists (left untouched)")
        return
    if not example.exists():
        fail(".env.example is missing")
        return
    content = example.read_text(encoding="utf-8").replace(
        "SECRET_KEY=change-me-to-a-long-random-string",
        f"SECRET_KEY={secrets.token_urlsafe(64)}",
    )
    env_path.write_text(content, encoding="utf-8")
    ok(".env created with a generated SECRET_KEY — edit it to configure "
       "PostgreSQL/Redis (SQLite fallback works for evaluation)")


def create_folders() -> None:
    step("4/8 Runtime folders")
    for name in ("storage", "storage/uploads", "storage/results",
                 "backups", "logs", "plugins"):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    ok("storage/, backups/, logs/, plugins/ ready")


def run_migrations() -> None:
    step("5/8 Database")
    if run([VENV_PY, "-m", "alembic", "upgrade", "head"], cwd=BACKEND):
        ok("migrations applied (alembic upgrade head)")
        return
    warn("alembic failed (database unreachable?) — falling back to create_all")
    code = ("import asyncio; from app.db.session import init_db; "
            "asyncio.run(init_db()); print('tables ready')")
    if run([VENV_PY, "-c", code], cwd=BACKEND):
        ok("tables created")
    else:
        fail("could not initialise the database — check DATABASE_URL in .env")


def seed_admin() -> None:
    step("6/8 Admin account")
    password = ARGS.admin_password or secrets.token_urlsafe(12)
    cmd = [str(VENV_PY), str(ROOT / "scripts" / "create_admin.py"),
           "--username", "admin", "--password", password]
    # an explicit --admin-password means the operator WANTS this password
    # set; otherwise an existing admin account is never touched on re-runs
    if ARGS.admin_password:
        cmd.append("--reset")
    try:
        result = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True,
                                timeout=300)
    except Exception:
        result = None
    if result is None or result.returncode != 0:
        if result is not None and result.stderr:
            print(result.stderr[-800:])
        fail("could not create the admin account (database problem?)")
        return
    if "ALREADY_EXISTS" in result.stdout:
        ok("admin account already exists (left untouched)")
    elif ARGS.admin_password:
        ok("admin account ready (password from --admin-password)")
    else:
        ok("admin account ready — INITIAL PASSWORD (change after first login):")
        print(f"\n      username: admin\n      password: {password}\n")


def build_frontend() -> None:
    step("7/8 Frontend")
    if ARGS.skip_frontend:
        ok("skipped (--skip-frontend)")
        return
    npm = shutil.which("npm")
    if not npm:
        warn("npm not found — skipping frontend build")
        return
    print("  installing Node packages…")
    if not run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND):
        fail("npm install failed")
        return
    print("  building production bundle…")
    if run([npm, "run", "build"], cwd=FRONTEND):
        ok("frontend built → frontend/dist (served automatically by the backend)")
    else:
        fail("frontend build failed")


def doctor() -> None:
    step("8/8 Doctor")
    code = """
import asyncio
async def main():
    from sqlalchemy import text
    from app.db.session import async_session_factory
    try:
        async with async_session_factory() as db:
            await db.execute(text('SELECT 1'))
        print('DB_OK')
    except Exception as e:
        print('DB_FAIL', type(e).__name__)
    try:
        from app.services.redis_client import get_redis
        await asyncio.wait_for(get_redis().ping(), 3)
        print('REDIS_OK')
    except Exception as e:
        print('REDIS_FAIL', type(e).__name__)
asyncio.run(main())
"""
    result = subprocess.run([str(VENV_PY), "-c", code], cwd=BACKEND,
                            capture_output=True, text=True)
    output = result.stdout
    if "DB_OK" in output:
        ok("database reachable")
    else:
        fail("database NOT reachable — check DATABASE_URL in .env")
    if "REDIS_OK" in output:
        ok("Redis reachable")
    else:
        warn("Redis NOT reachable — queue/realtime need Redis "
             "(install Redis or run: docker compose up -d redis)")


def main() -> int:
    print("┌──────────────────────────────────────────────┐")
    print("│  AIAuto — one-command setup                  │")
    print("└──────────────────────────────────────────────┘")
    check_requirements()
    if errors:
        print("\nFatal requirement problems — aborting.")
        return 1
    create_venv()
    create_env_file()
    create_folders()
    run_migrations()
    seed_admin()
    build_frontend()
    doctor()

    print("\n" + "=" * 50)
    if errors:
        print(f"Setup finished with {len(errors)} error(s):")
        for e in errors:
            print(f"  {FAIL} {e}")
        return 1
    print("Setup complete ✔")
    if warnings:
        print(f"({len(warnings)} warning(s) above)")
    start_cmd = "start.bat" if IS_WINDOWS else "./start.sh"
    print(f"""
Next steps:
  1. Review .env (database, Redis, ChatGPT browser settings)
  2. Start everything:        {start_cmd}
  3. Open the app:            http://localhost:8000
  4. Master computer (worker): see docs/INSTALLATION.md
""")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-password", default="", help="initial admin password")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--dev", action="store_true", help="install dev/test dependencies too")
    ARGS = parser.parse_args()
    sys.exit(main())
