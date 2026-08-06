# Installation Guide

## Fastest path — one command

```bash
git clone <your-repo-url> aiauto && cd aiauto
./setup.sh          # Windows: setup.bat
./start.sh          # Windows: start.bat  (--with-worker on the master PC)
```

Setup installs everything (venv, Python + Node packages, .env with a
generated SECRET_KEY, database migrations, admin account — the initial
password is printed once, frontend build) and `start` verifies every
service before printing **System Ready**. The backend serves the built
frontend, so a single process gives you the whole app at
http://localhost:8000. The rest of this guide covers the manual and
Docker paths plus master-computer specifics.

Two machines are involved:

| Machine | Runs | Notes |
|---|---|---|
| **Central server** | FastAPI backend, PostgreSQL, Redis, frontend | Linux or Windows; Docker recommended |
| **Master computer** | Worker + Chrome logged into ChatGPT Pro | Windows, keeps a visible Chrome session |

They may be the same physical machine.

## 1. Central server

### Option A — Docker (recommended)

```bash
git clone <your-repo-url> aiauto && cd aiauto
cp .env.example .env
# Edit .env:  SECRET_KEY (long random), POSTGRES_PASSWORD, CORS_ORIGINS
docker compose up -d --build
```

Create the first admin:

```bash
docker compose exec backend sh -c "cd /app && python ../scripts/create_admin.py --password 'YourStrongPass1'"
```

> If the scripts folder is not inside the container, run it from the host
> with a local Python (Option B venv) pointing DATABASE_URL at the server.

Apply migrations (Docker backend auto-creates tables on first boot; for
production upgrades use Alembic):

```bash
docker compose exec backend alembic upgrade head
```

### Option B — Native (Windows or Linux)

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux: source .venv/bin/activate
pip install -r requirements.txt
cd .. && cp .env.example .env        # edit values
cd backend
alembic upgrade head
python ../scripts/create_admin.py --password 'YourStrongPass1'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

PostgreSQL and Redis must be reachable at the URLs in `.env`.
(For a quick trial you can use `DATABASE_URL=sqlite+aiosqlite:///./storage/aiauto.db`.)

### Frontend (native dev)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
npm run build      # production build in dist/ — serve with nginx (see nginx.conf)
```

## 2. Master computer (Windows)

1. Install Python 3.13 and Google Chrome.
2. `cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt`
3. `.venv\Scripts\playwright install chrome` (registers the Chrome channel)
4. Edit the shared `.env` (or a local copy) so `REDIS_URL` and `DATABASE_URL`
   point at the central server, and set:
   ```
   CHROME_CDP_URL=http://localhost:9222
   CHROME_PROFILE_DIR=C:\aiauto-chrome
   ```
5. Start Chrome with debugging enabled — double-click
   `scripts\start_master_chrome.bat` — and **log into ChatGPT Pro once**
   in that window. The profile keeps the login permanently.
6. Start the worker: `scripts\run_worker.bat`
   (or `python -m worker.main` inside the venv).

The admin dashboard now shows *Worker online / Chrome connected*.

To run the worker as a Windows service, use NSSM:

```
nssm install AIAutoWorker "C:\aiauto\backend\.venv\Scripts\python.exe" "-m worker.main"
nssm set AIAutoWorker AppDirectory C:\aiauto\backend
```

## 3. First login

1. Open the frontend, sign in with the admin account.
2. **Users** → create staff accounts (role `staff`).
3. **Update** → save your GitHub repository, branch, and a fine-grained
   personal access token (read-only `Contents` permission is enough).
4. Staff sign in from their own computers and start submitting prompts.

## Redis on Windows

Redis is required for the queue, realtime updates, rate limiting and
login lockout. Official Redis has no native Windows build — pick one:

1. **Memurai** (Redis-7-compatible, native Windows service, free Developer
   edition): https://www.memurai.com → install, it runs on port 6379
   automatically. Recommended for the single-machine office setup.
2. **Docker Desktop**: `docker run -d --name redis -p 6379:6379 --restart unless-stopped redis:7`
3. **WSL2**: `sudo apt install redis-server && sudo service redis-server start`
4. **Redis for Windows port** (free `.msi`, but old — Redis 5.0):
   https://github.com/tporadowski/redis/releases → install
   `Redis-x64-*.msi` with "Run as service" checked. AIAuto supports this
   server (the client speaks the classic RESP2 protocol), but prefer
   Memurai or Docker for anything long-term.

Verify it works: `redis-cli ping` → `PONG` (or check the Admin → System
page shows *Redis OK* after starting the backend).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` running scripts | You're on the wrong Python. Call the venv interpreter explicitly: `backend\.venv\Scripts\python.exe ..\scripts\create_admin.py …` — and if the module really is missing, run `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` |
| `Error … connecting to localhost:6379` | Redis is not running — see "Redis on Windows" above |
| Worker offline in dashboard | Worker process not running, or Redis unreachable from master PC |
| Chrome disconnected | Chrome not started with `--remote-debugging-port=9222`; use the .bat |
| "login expired" failures | Open the master Chrome window and log into ChatGPT again |
| 429 responses | Rate limit hit — raise `RATE_LIMIT_PER_MINUTE` |
| Uploads rejected | Raise `MAX_UPLOAD_MB` and nginx `client_max_body_size` |
