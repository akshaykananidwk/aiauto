# AIAuto — Central AI Automation Platform

An enterprise-grade platform that lets office staff use centrally managed
AI — a **single ChatGPT Pro session** and/or **official AI APIs** —
without ever seeing the account, the browser, or each other's data.

```
Staff PC ──▶ Login ──▶ Prompt ──▶ Central Server (FastAPI + Redis queue)
                                        │
                                        ▼
                          Master PC worker (Playwright / APIs)
                          ChatGPT Pro ▸ OpenAI ▸ Claude ▸ Gemini
                                        │   (automatic failover)
             text / images / files  ◀───┘
                                        │
Staff PC ◀── WebSocket live status ◀────┘
```

> **Note on Terms of Service:** automating the ChatGPT *web UI* may violate
> OpenAI's terms and can break when the UI changes. The platform is
> provider-pluggable — set `AI_PROVIDER=openai|anthropic|gemini` to use
> official APIs with the identical staff experience, or configure a
> failover chain mixing both. Browser automation mode exists because this
> project was specified around it — use it at your own discretion.

## Highlights

**83 features** — see [FEATURES.md](FEATURES.md) for the full list.

- **Privacy-first**: staff see only their own prompts, results and history;
  admins see everything; nobody touches the AI accounts.
- **Multi-provider AI** with per-prompt selection, auto-failover, token
  and cost tracking, usage analytics.
- **Enterprise auth**: JWT + rotation + revocation, brute-force lockout,
  role-based access, personal API keys, full audit trail.
- **Queue** with priorities, retries, cancellation, multi-worker failover
  and a live dashboard.
- **Productivity**: shared prompt library (categories/tags/favorites),
  scheduled prompts, voice input/output, exports.
- **Notifications**: in-app center, WebSocket live status, email,
  Telegram, webhooks (Slack/WhatsApp gateways), desktop notifications.
- **Operations**: one-click GitHub updates with auto-backup + rollback,
  scheduled backups, restore wizard, system health monitoring, plugins.
- **Modern UI**: React, dark/light theme, mobile-responsive, installable PWA.

## Quick start (one command)

```bash
git clone <your-repo-url> aiauto && cd aiauto
./setup.sh            # Windows: setup.bat
./start.sh            # Windows: start.bat   (add --with-worker on the master PC)
```

`setup` verifies requirements, creates the venv, installs Python + Node
packages, generates `.env` with a fresh SECRET_KEY, migrates the database
(SQLite fallback works out of the box), seeds the admin account (prints
the initial password), and builds the frontend. `start` launches
everything and reports **System Ready** once every service is healthy.

Then open **http://localhost:8000** — API docs at `/api/docs`.

### Docker instead

```bash
cp .env.example .env      # set SECRET_KEY + POSTGRES_PASSWORD
docker compose up -d --build
```

Frontend: http://localhost:8080 · API: http://localhost:8000

### Master computer (Windows)

The worker that drives ChatGPT runs natively where Chrome is logged in:

1. `scripts\start_master_chrome.bat` → log into ChatGPT Pro once
2. `start.bat --with-worker` (or `scripts\run_worker.bat`)

See [docs/INSTALLATION.md](docs/INSTALLATION.md) for details.

## Tech stack

Python 3.11+ · FastAPI · SQLAlchemy 2 (async) · PostgreSQL / SQLite ·
Redis · Playwright · React 18 + Vite · Docker · Windows-compatible

## Repository layout

```
backend/
  app/            FastAPI application (clean architecture)
    core/         config, security (JWT/bcrypt/Fernet), logging, rate limiting
    db/           engine/session, declarative base
    models/       SQLAlchemy models
    schemas/      Pydantic request/response models
    repositories/ data access layer
    services/     business logic (queue, quota, notify, analytics, update…)
    api/v1/       HTTP + WebSocket endpoints
  worker/         master-computer worker + AI providers
  alembic/        database migrations
  tests/          67+ automated tests
frontend/         React app (staff + admin dashboards, PWA)
plugins/          drop-in Python plugins
scripts/          setup, start, admin bootstrap, load test, Windows helpers
docs/             installation, deployment, API, update system
```

## Documentation

- [Feature list](FEATURES.md)
- [Installation guide](docs/INSTALLATION.md)
- [Deployment guide](docs/DEPLOYMENT.md) — HTTPS, services, scaling
- [API reference](docs/API.md)
- [Update system](docs/UPDATE_SYSTEM.md) — one-click updates & rollback
- [Security overview](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Testing

```bash
cd backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                            # 67 tests
python ../scripts/loadtest.py --password <admin-pw>   # quick load check
```
