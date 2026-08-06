# AIAuto — Central AI Automation Platform

A production-ready platform that lets office staff use a **single, centrally
managed ChatGPT Pro session** without ever seeing the account, the browser,
or each other's conversations.

```
Staff PC ──▶ Login ──▶ Prompt ──▶ Central Server (FastAPI + Redis queue)
                                        │
                                        ▼
                            Master PC worker (Playwright)
                            drives the logged-in ChatGPT Pro Chrome
                                        │
             text / images / files  ◀───┘
                                        │
Staff PC ◀── WebSocket live status ◀────┘
```

> **Note on Terms of Service:** automating the ChatGPT *web UI* may violate
> OpenAI's terms and can break when the UI changes. The platform ships with a
> pluggable provider: set `AI_PROVIDER=api` and an `OPENAI_API_KEY` to use the
> official OpenAI API with the exact same staff experience. Browser automation
> mode is provided because it is what this project was specified to do — use
> it at your own discretion.

## Features

- **Roles & auth** — admin + staff, JWT (access/refresh), bcrypt hashing,
  rate limiting, full audit trail.
- **Queue** — Redis-backed FIFO with priorities, automatic retries,
  cancellation, live queue dashboard.
- **Browser automation** — attaches to the already-running, logged-in Chrome
  via CDP (or launches a persistent profile), sends the prompt, waits for
  completion, captures text, downloads generated **images and files**
  (PDF/DOCX/XLSX/PPTX/ZIP/…), builds thumbnails, and can delete each
  conversation from the ChatGPT account afterwards.
- **Privacy** — staff see only their own history; admin sees everything;
  nobody but the worker touches ChatGPT.
- **Realtime** — WebSocket events: Submitted → Processing → Generating image
  → Downloading → Completed.
- **One-click GitHub updates** — save repo/branch/token once; *Check for
  Update* shows new commits (version, message, author, date); *Update Now*
  downloads from GitHub, backs up first, never overwrites `.env` /
  `uploads/` / `storage/` / `config.php`, runs DB migrations automatically,
  clears the cache, and **rolls back automatically on any error**.
- **Admin settings** — concurrency, queue size, timeouts, retries, storage
  limits, browser profile path, backup retention — editable from the UI.

## Tech Stack

Python 3.13 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL (or SQLite for
testing) · Redis · Playwright · React 18 + Vite · Docker · Windows-compatible.

## Repository Layout

```
backend/
  app/            FastAPI application (clean architecture)
    core/         config, security (JWT/bcrypt/Fernet), logging, rate limiting
    db/           engine/session, declarative base
    models/       SQLAlchemy models
    schemas/      Pydantic request/response models
    repositories/ data access layer
    services/     business logic (queue, prompts, storage, update system…)
    api/v1/       HTTP + WebSocket endpoints
    ws/           WebSocket manager (Redis pub/sub bridge)
  worker/         master-computer worker + Playwright automation
  alembic/        database migrations
  tests/          unit tests
frontend/         React app (staff + admin dashboards)
scripts/          admin bootstrap, Windows helper scripts
docs/             installation, deployment, API, update-system docs
```

## Quick Start (Docker)

```bash
cp .env.example .env             # edit SECRET_KEY at minimum!
docker compose up -d --build
docker compose exec backend python /app/../scripts/create_admin.py --password 'ChangeMe123'
# or: docker compose exec backend python -c "..." — see docs/INSTALLATION.md
```

Frontend: http://localhost:8080 · API docs: http://localhost:8000/api/docs

The **worker runs natively on the Windows master computer** (it needs the
visible logged-in Chrome). See `docs/INSTALLATION.md`.

## Documentation

- [Installation guide](docs/INSTALLATION.md)
- [Deployment guide](docs/DEPLOYMENT.md)
- [API reference](docs/API.md)
- [Update system](docs/UPDATE_SYSTEM.md)

## Testing

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt pytest pytest-asyncio
pytest
```
