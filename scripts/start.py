#!/usr/bin/env python3
"""AIAuto one-click start — the ONLY file you need to run.

    Double-click start.bat (or run: python scripts/start.py)

It automatically, in order:
  1. verifies the environment (venv, configuration; .env auto-created)
  2. starts Redis if it isn't running (Windows service / local binary)
  3. starts the backend (API + frontend + scheduler + WebSocket)
  4. opens Chrome with the dedicated profile and remote debugging —
     reconnecting to an existing window instead of opening duplicates
  5. starts the browser-automation worker
  6. verifies EVERY component (DB, Redis, backend, worker, Chrome)
  and only then prints "System Ready".

Flags:
  --server-only   central server without Chrome/worker (worker runs elsewhere)
  --no-chrome     start the worker but do not launch/verify Chrome here
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
IS_WINDOWS = os.name == "nt"
VENV_PY = BACKEND / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
    "python.exe" if IS_WINDOWS else "python")

OK, WARN, FAIL = "✔", "⚠", "✘"
procs: list[tuple[str, subprocess.Popen]] = []
CFG: dict = {}


def say(mark: str, msg: str) -> None:
    print(f"  {mark} {msg}")


def spawn(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    say("▶", f"starting {name}…")
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd)
    procs.append((name, proc))
    return proc


def stop_all() -> None:
    for _name, proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for _name, proc in procs:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def die(msg: str) -> None:
    print(f"\n{FAIL} STARTUP FAILED: {msg}")
    print("  Started services were stopped. Fix the problem and run start again.")
    stop_all()
    sys.exit(1)


# ---------- step 1: environment + configuration ----------

def load_config() -> dict:
    if not VENV_PY.exists():
        die("backend virtual environment missing — run setup first "
            f"({'setup.bat' if IS_WINDOWS else './setup.sh'})")
    code = (
        "import json\n"
        "from app.core.config import get_settings\n"
        "s = get_settings()\n"
        "print(json.dumps({'redis_url': s.redis_url, 'cdp': s.chrome_cdp_url,\n"
        "  'profile': s.chrome_profile_dir, 'chatgpt': s.chatgpt_url,\n"
        "  'env': s.env}))"
    )
    result = subprocess.run([str(VENV_PY), "-c", code], cwd=BACKEND,
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(result.stderr[-1200:])
        die("configuration is invalid — check .env")
    cfg = json.loads(result.stdout.strip().splitlines()[-1])
    say(OK, "environment verified, configuration valid (.env loaded)")
    return cfg


# ---------- step 2: Redis ----------

def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def redis_reachable(host: str, port: int) -> bool:
    return port_open(host, port)


def try_start_redis() -> None:
    if IS_WINDOWS:
        for service in ("Memurai", "Redis"):
            subprocess.run(["net", "start", service], capture_output=True, timeout=60)
        for binary in ("memurai.exe", "redis-server.exe", "redis-server"):
            try:
                subprocess.Popen([binary], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                break
            except FileNotFoundError:
                continue
    else:
        subprocess.run(["redis-server", "--daemonize", "yes"], capture_output=True)


def ensure_redis() -> None:
    parsed = urlparse(CFG["redis_url"])
    host, port = parsed.hostname or "localhost", parsed.port or 6379
    if redis_reachable(host, port):
        say(OK, f"Redis running ({host}:{port})")
        return
    if host not in ("localhost", "127.0.0.1"):
        die(f"Redis at {host}:{port} is unreachable (remote — start it there)")
    say(WARN, "Redis not running — starting it…")
    try_start_redis()
    for _ in range(10):
        if redis_reachable(host, port):
            say(OK, "Redis started")
            return
        time.sleep(1)
    die("could not start Redis automatically.\n"
        "  Install it as a service (see docs/INSTALLATION.md → 'Redis on Windows'):\n"
        "  easiest: Memurai (https://www.memurai.com) — installs as an auto-start service")


# ---------- step 3/6: backend + health ----------

def fetch_health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                    timeout=8) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def wait_health(port: int, predicate, timeout: int, what: str) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        health = fetch_health(port)
        if health and predicate(health):
            return health
        time.sleep(1.5)
    return None


# ---------- step 4: Chrome ----------

def cdp_alive(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=2):
            return True
    except Exception:
        return False


def find_chrome() -> str | None:
    if IS_WINDOWS:
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LocalAppData", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for path in candidates:
            if path.is_file():
                return str(path)
        return None
    import shutil

    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def ensure_chrome() -> bool:
    cdp = CFG["cdp"] or "http://localhost:9222"
    if cdp_alive(cdp):
        say(OK, "Chrome already running with remote debugging — reconnecting "
                "(no duplicate window)")
        return True
    chrome = find_chrome()
    if chrome is None:
        say(FAIL, "Google Chrome not found — install it or start it manually with "
                  "scripts/start_master_chrome.bat")
        return False
    profile = CFG["profile"] or str(Path.home() / "aiauto-chrome")
    port = urlparse(cdp).port or 9222
    say("▶", f"opening Chrome (profile {profile}, debug port {port})…")
    subprocess.Popen([
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        CFG["chatgpt"],
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if cdp_alive(cdp):
            say(OK, "Chrome connected (existing ChatGPT login is preserved)")
            return True
        time.sleep(1)
    say(FAIL, "Chrome did not expose the debugging port within 30 s")
    return False


# ---------- main ----------

def main() -> int:
    global CFG
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--server-only", action="store_true",
                        help="no Chrome/worker on this machine")
    parser.add_argument("--no-chrome", action="store_true",
                        help="start the worker but do not manage Chrome")
    # kept for backwards compatibility; full mode is now the default
    parser.add_argument("--with-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    run_worker = not args.server_only

    print("┌──────────────────────────────────────────────┐")
    print("│  AIAuto — one-click startup                  │")
    print("└──────────────────────────────────────────────┘")

    print("\n[1/6] Environment & configuration")
    CFG = load_config()

    print("\n[2/6] Redis")
    ensure_redis()

    print("\n[3/6] Backend (API + frontend + scheduler + WebSocket)")
    # pre-flight: is the port already taken? Running start.bat twice must
    # REUSE the existing backend, never fight it for the port.
    existing = fetch_health(args.port)
    if existing and existing.get("app"):
        say(OK, f"backend already running on port {args.port} — reusing it "
                "(close this window's twin if you started start.bat twice)")
    else:
        if port_open("127.0.0.1", args.port):
            die(f"port {args.port} is used by another program (not AIAuto).\n"
                f"  Find it:   netstat -ano | findstr :{args.port}\n"
                f"  Kill it:   taskkill /F /PID <pid>\n"
                f"  …or start on another port:  start.bat --port 8001")
        spawn("backend", [VENV_PY, "-m", "uvicorn", "app.main:app",
                          "--host", args.host, "--port", str(args.port)], BACKEND)
    health = wait_health(args.port, lambda h: h.get("database"), 90, "backend")
    if health is None:
        die("backend did not become healthy — check logs/aiauto.log")
    say(OK, "backend healthy (database OK)")
    if not health.get("redis"):
        die("backend cannot reach Redis — check REDIS_URL in .env")
    say(OK, "Redis connection verified")

    chrome_ok = True
    if run_worker:
        if not args.no_chrome:
            print("\n[4/6] Chrome (ChatGPT Pro session)")
            chrome_ok = ensure_chrome()
        else:
            print("\n[4/6] Chrome — skipped (--no-chrome)")

        print("\n[5/6] Browser-automation worker")
        pre = fetch_health(args.port) or {}
        if pre.get("worker"):
            say(OK, "a worker is already online — not starting a duplicate")
        else:
            spawn("worker", [VENV_PY, "-m", "worker.main"], BACKEND)
        health = wait_health(args.port, lambda h: h.get("worker"), 45, "worker")
        if health is None:
            die("worker did not come online — check the worker output above")
        say(OK, "worker online")
        if not args.no_chrome:
            health = wait_health(args.port, lambda h: h.get("chrome"), 30, "chrome")
            if health is None:
                chrome_ok = False
                say(WARN, "worker cannot reach Chrome yet")
            else:
                say(OK, "browser automation connected to Chrome")
    else:
        print("\n[4/6] Chrome — skipped (--server-only)")
        print("[5/6] Worker — skipped (--server-only)")

    print("\n[6/6] Final verification")
    health = fetch_health(args.port) or {}
    checks = {
        "Backend responding": bool(health),
        "Database connected": health.get("database", False),
        "Redis connected": health.get("redis", False),
    }
    if run_worker:
        checks["Worker online"] = health.get("worker", False)
        if not args.no_chrome:
            checks["Chrome/browser automation"] = health.get("chrome", False) and chrome_ok
    for label, passed in checks.items():
        say(OK if passed else FAIL, label)

    if all(checks.values()):
        print(f"""
══════════════════════════════════════════════════
  ✔ System Ready
══════════════════════════════════════════════════
  Web app:      http://localhost:{args.port}
  API docs:     http://localhost:{args.port}/api/docs   (interactive explorer)
  Public API:   http://localhost:{args.port}/api/public/v1  (X-API-Key)
  Health:       http://localhost:{args.port}/api/health
{'' if run_worker else '  Worker:       run start on the master computer (default mode)'}
  ChatGPT login: if prompts fail with "logged out", sign in once in the
  Chrome window that just opened — the profile remembers it afterwards.
  Press Ctrl+C to stop (Chrome stays open to preserve the session).
""")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f"""
══════════════════════════════════════════════════
  {WARN} System started with problems: {', '.join(failed)}
══════════════════════════════════════════════════
  Everything else is running. Fix the item(s) above; the platform will
  recover automatically (services retry on their own). Press Ctrl+C to stop.
""")

    restarts: dict[str, list[float]] = {}
    try:
        while True:
            for name, proc in list(procs):
                code = proc.poll()
                if code is None:
                    continue
                # crash-loop guard: a service that dies 3 times within 90 s
                # has a real problem — stop hammering it and say so clearly
                history = [t for t in restarts.get(name, []) if time.time() - t < 90]
                history.append(time.time())
                restarts[name] = history
                procs.remove((name, proc))
                if len(history) >= 3:
                    say(FAIL, f"{name} keeps crashing (exit code {code}).")
                    if name == "backend" and code == 3:
                        say(FAIL, f"exit code 3 usually means port {args.port} is taken "
                                  "by ANOTHER AIAuto window or a stale process.")
                        say(FAIL, "Close other start.bat windows, or run: "
                                  f"netstat -ano | findstr :{args.port}  → "
                                  "taskkill /F /PID <pid>")
                    say(FAIL, "Not restarting it again — fix the cause, then run "
                              "start.bat once more. (Ctrl+C to stop the rest.)")
                    continue
                say(FAIL, f"{name} exited with code {code} — restarting in 3 s")
                time.sleep(3)
                if name == "backend":
                    # if another healthy backend already owns the port, just
                    # attach to it instead of colliding forever
                    if fetch_health(args.port):
                        say(OK, "another AIAuto backend is serving the port — reusing it")
                        continue
                    spawn(name, [VENV_PY, "-m", "uvicorn", "app.main:app",
                                 "--host", args.host, "--port", str(args.port)], BACKEND)
                else:
                    spawn(name, [VENV_PY, "-m", "worker.main"], BACKEND)
                break
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping services… (Chrome is left running on purpose)")
        stop_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
