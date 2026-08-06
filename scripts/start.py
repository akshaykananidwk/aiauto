#!/usr/bin/env python3
"""AIAuto one-command start.

    python scripts/start.py [--with-worker] [--port 8000]

Starts the backend API (which serves the built frontend, the WebSocket
hub and the scheduler), optionally the AI worker, verifies every service
is healthy, then reports "System Ready". Ctrl+C stops everything.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
IS_WINDOWS = os.name == "nt"
VENV_PY = BACKEND / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
    "python.exe" if IS_WINDOWS else "python")

procs: list[tuple[str, subprocess.Popen]] = []


def spawn(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    print(f"  ▶ starting {name}…")
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd)
    procs.append((name, proc))
    return proc


def wait_for_health(port: int, timeout: int = 90) -> dict | None:
    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:
                return json.loads(resp.read())
        except Exception:
            time.sleep(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--with-worker", action="store_true",
                        help="also run the AI worker on this machine")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    if not VENV_PY.exists():
        print("Backend virtual environment missing — run: python scripts/setup.py")
        return 1

    print("┌──────────────────────────────────────────────┐")
    print("│  AIAuto — starting services                  │")
    print("└──────────────────────────────────────────────┘")

    spawn("backend (API + frontend + scheduler + WebSocket)",
          [VENV_PY, "-m", "uvicorn", "app.main:app",
           "--host", args.host, "--port", str(args.port)], BACKEND)

    print("  … waiting for the backend to become healthy")
    health = wait_for_health(args.port)
    if health is None:
        print("  ✘ backend did not become healthy within 60 s — check logs/aiauto.log")
        stop_all()
        return 1
    print(f"  ✔ backend healthy (database={'OK' if health['database'] else 'FAIL'}, "
          f"redis={'OK' if health['redis'] else 'FAIL'})")
    if not health["database"]:
        print("  ✘ database unreachable — fix DATABASE_URL in .env")
        stop_all()
        return 1
    if not health["redis"]:
        print("  ⚠ Redis unreachable — queue and realtime updates will not work "
              "until Redis is up (docker compose up -d redis)")

    if args.with_worker:
        spawn("worker (AI automation)", [VENV_PY, "-m", "worker.main"], BACKEND)
        time.sleep(2)

    frontend_note = "" if (ROOT / "frontend" / "dist").is_dir() else \
        "  ⚠ frontend/dist missing — run setup with Node installed for the web UI\n"
    print(f"""
══════════════════════════════════════════════════
  ✔ System Ready
══════════════════════════════════════════════════
{frontend_note}  Web app:    http://localhost:{args.port}
  API docs:   http://localhost:{args.port}/api/docs
  Health:     http://localhost:{args.port}/api/health
{'' if args.with_worker else '  Worker:     start it on the master computer (scripts/run_worker.bat)'}
  Press Ctrl+C to stop.
""")
    try:
        while True:
            for name, proc in procs:
                code = proc.poll()
                if code is not None:
                    print(f"  ✘ {name} exited with code {code} — restarting in 3 s")
                    time.sleep(3)
                    procs.remove((name, proc))
                    if "backend" in name:
                        spawn(name, [VENV_PY, "-m", "uvicorn", "app.main:app",
                                     "--host", args.host, "--port", str(args.port)], BACKEND)
                    else:
                        spawn(name, [VENV_PY, "-m", "worker.main"], BACKEND)
                    break
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping…")
        stop_all()
    return 0


def stop_all() -> None:
    for name, proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for _name, proc in procs:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
