# AIAuto — Central AI Automation Platform

An enterprise-grade platform that lets office staff use a centrally
managed **ChatGPT Pro browser session** — without ever seeing the
account, the browser, or each other's data. There are **no external AI
API integrations**: one master computer, one subscription, zero per-token
costs.

```
Staff PC ──▶ Login ──▶ Prompt ──▶ Central Server (FastAPI + Redis queue)
                                        │
                                        ▼
                        Master PC worker (Playwright)
                        logged-in ChatGPT Pro browser session
                                        │
             text / images / files  ◀───┘
                                        │
Staff PC ◀── WebSocket live status ◀────┘
```

> **Note on Terms of Service:** automating the ChatGPT *web UI* may
> violate OpenAI's terms and can break when the UI changes (selectors are
> centralised in one file to make fixes one-liners). This project is
> intentionally built around a single browser session — use it at your
> own discretion.

## Highlights

**76 features** — see [FEATURES.md](FEATURES.md) for the full list.

- **Privacy-first**: staff see only their own prompts, results and history;
  admins see everything; nobody touches the ChatGPT account.
- **Browser-automation only**: no AI API keys, no per-token billing — the
  ChatGPT Pro subscription is the entire AI cost.
- **Enterprise auth**: JWT + rotation + revocation, brute-force lockout,
  role-based access, full audit trail.
- **Queue** with priorities, retries, cancellation, multi-worker failover
  and a live dashboard.
- **Productivity**: shared prompt library (categories/tags/favorites),
  scheduled prompts, voice input/output, exports.
- **Notifications**: in-app center, WebSocket live status, email,
  Telegram, webhooks (Slack/WhatsApp gateways), desktop notifications.
- **Operations**: one-click GitHub updates with auto-backup + rollback,
  scheduled backups, restore wizard, system health monitoring, plugins.
- **Public REST API**: your customers' apps, ERPs and CRMs integrate via
  API keys (scopes, expiry, IP allowlists, rate limits), async jobs,
  signed webhooks, Swagger/ReDoc docs and SDK examples — all processed
  by the same central ChatGPT session.
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

Just double-click `start.bat` — it starts Redis, the backend, Chrome
(with the dedicated logged-in profile; reconnects instead of opening
duplicates) and the worker, then verifies everything before printing
**System Ready**. Log into ChatGPT Pro once in the Chrome window it
opens; the profile remembers it. On a central server without Chrome,
use `start.bat --server-only`.

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
  worker/         master-computer worker (ChatGPT browser automation)
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
- [API reference](docs/API.md) (internal) · [Public API guide](docs/PUBLIC_API.md) + [SDK examples](docs/sdk-examples/)
- [Update system](docs/UPDATE_SYSTEM.md) — one-click updates & rollback
- [Security overview](SECURITY.md)
- [Changelog](CHANGELOG.md)

## Testing

```bash
cd backend
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
python ../scripts/loadtest.py --password <admin-pw>   # quick load check
```
