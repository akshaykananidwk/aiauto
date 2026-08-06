# Changelog

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
