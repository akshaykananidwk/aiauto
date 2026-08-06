# Changelog

## 1.2.1 — Image pipeline reliability

Root-cause fix for generated images not reaching the website:

- **Image-aware completion detection**: the worker now waits until the
  reply's images are fully loaded and stable (src + natural size
  unchanged, no "Creating image…" indicator, image `complete`), not just
  until the caption text stops changing — ChatGPT keeps rendering an
  image long after the text stabilises, and image-only replies contain
  no text at all (previously a guaranteed timeout)
- **Zero images = failure, never success**: an image prompt that yields
  no downloadable image is auto-retried and then FAILED with a clear
  error (the ChatGPT conversation is kept for inspection) instead of
  being marked completed without results
- **Hardened capture**: validated HTTP downloads (content-type +
  minimum size), element-screenshot fallback for blob: URLs, size
  filtering (no avatars/icons), page-wide fallback scope, and up to 4
  capture attempts with waits
- **Disk verification**: every result file is verified on disk before
  its DB row is written; persist failures roll back the completion and
  go through the normal retry path instead of wedging the job
- **Frontend safety net**: prompt pages poll every 8s while a job runs
  (20s on the dashboard) so results always appear even if a WebSocket
  event is lost; images without thumbnails now preview from the full
  file instead of a placeholder icon

## 1.2.0 — Browser-only architecture

**Breaking:** all external AI API integrations are removed. The platform
now runs exclusively through the master computer's logged-in ChatGPT Pro
browser session — no API keys, no per-token costs, one subscription.

### Removed
- OpenAI / Anthropic Claude / Google Gemini API providers and their
  settings (`AI_PROVIDER`, `AI_FAILOVER_CHAIN`, all `*_API_KEY` vars)
- Per-prompt provider selection and provider failover
- Personal API keys (`X-API-Key` auth, the API Keys page, `api_keys` table)
- Token usage and cost tracking (prompt columns, pricing tables,
  analytics breakdowns)
- Document-extraction helper that only served API providers (pypdf dep)
- Migration `0003` drops the removed table/columns automatically

### Improved
- `/api/health` is hard-capped (a down Redis can never stall it) and the
  Redis client fails fast with socket timeouts
- `start.py` waits longer and tolerates slow first responses
- Windows Redis installation guide + troubleshooting for
  `ModuleNotFoundError` when the wrong Python is used

## 1.1.0 — Enterprise release

### Security
- Brute-force lockout, JWT revocation on logout, refresh-token rotation
- Personal API keys (`X-API-Key`), hashed at rest
- Fail-secure revocation checks; expanded automated authz tests

### AI providers
- Multi-provider support: ChatGPT browser, OpenAI, Anthropic Claude, Google Gemini
- Per-prompt provider selection and automatic failover chain
- Token usage + cost tracking per prompt; document text extraction (pypdf, optional OCR)

### Productivity
- Prompt template library (categories, tags, search, favorites, team sharing)
- Scheduled prompts (once / interval / daily / weekly)
- Voice input & output, prompt history export (CSV/JSON)

### Operations
- Notification center + email / Telegram / webhook channels, desktop notifications
- User & department quotas with global defaults
- Usage analytics dashboard (daily chart, top users, departments, providers, cost)
- System health page: CPU/memory/disk, worker fleet, DB/Redis status
- Manual + scheduled backups, restore wizard, disk usage alerts
- Multi-worker registry with heartbeats; watchdog re-queues jobs from dead workers
- Plugin system (drop-in Python hooks)

### Platform
- One-command setup (`setup.sh` / `setup.bat`) and start (`start.sh` / `start.bat`)
- `.env` auto-created on first run with generated SECRET_KEY
- Backend serves the built frontend (single-process mode)
- Dark/light theme, mobile-responsive UI, PWA support
- GZip compression, Redis caching, composite DB indexes, SQLite NullPool
- Test suite grown to 67 tests (auth, isolation, quotas, templates, keys, scheduler math)

## 1.0.0 — Initial release

- FastAPI backend, Redis priority queue, Playwright ChatGPT automation
- Staff/admin dashboards (React), realtime WebSocket updates
- Image & file capture with thumbnails, audit logging, admin settings
- One-click GitHub update system with backup, protected paths, migrations,
  cache clear and automatic rollback
- Docker Compose stack, installation/deployment/API documentation
