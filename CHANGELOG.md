# Changelog

## 1.3.5 — Worker survives Chrome closing mid-job

Production logs showed the exact remaining failure chain: Chrome (the
debug-port one) closed mid-generation → `TargetClosedError` burned a
retry → the worker's fallback launched a SECOND Chrome without the debug
port (which start.bat could not find) → more `TargetClosedError`s until
everything was restarted by hand.

- **Worker now relaunches the REAL Chrome**: when the CDP endpoint is
  gone, the worker starts Google Chrome itself with the same profile and
  debug port (exactly like start.bat) and re-attaches — one Chrome,
  always reachable, login preserved. The debug-less Playwright fallback
  is now a true last resort (Chrome not installed)
- **Browser-gone failures no longer burn retries**: `TargetClosedError`,
  CDP `ECONNREFUSED` and friends are classified as environment faults —
  the job goes straight back into the queue, Chrome is reopened, and the
  prompt retries automatically (same treatment internet outages got in
  1.3.3). No more jobs failing permanently because a window was closed
  at the wrong moment
- Clear user-facing status while it happens: "The AI browser on the
  master computer closed mid-job — it was reopened and the job will
  retry automatically."
- 7 new tests (113 total)

## 1.3.4 — Image flow proven end-to-end + built-in diagnostics

- **The website display flow is now PROVEN, not assumed**: a real-browser
  end-to-end test (`scripts/e2e_display_check.py`) drives the actual UI —
  login → submit image prompt → live status → thumbnail renders → viewer
  → Copy Image (real PNG on the clipboard) → Download (actual browser
  download) → Open-in-tab inline. All 11 checks pass; when an image
  reaches the server it WILL display, copy, download and save
- **Image-Capture Diagnostics in the admin panel** (System page): when
  the worker cannot capture a generated image (or times out), it saves a
  screenshot + HTML of exactly what the ChatGPT page showed; those dumps
  and the worker/backend log tails are now viewable directly in the
  website — the real cause of a failed image is one click away instead
  of buried on the master computer
- **Timeout dumps**: a generation timeout now also saves a debug
  screenshot ("it just never finished" becomes a diagnosable fact)
- **Live stage line on the prompt page**: while a job runs the page now
  shows exactly what is happening ("Generating the image… this can take
  a few minutes", "Image ready — downloading it to the server…") instead
  of a bare "processing" badge
- **Per-process log files**: the worker now logs to `logs/worker.log`
  (backend keeps `logs/aiauto.log`) — on Windows two processes sharing
  one rotating log file break rotation
- Newer ChatGPT UI selectors for generated images ("Making image…",
  backend-api content URLs, dalle test-ids)
- 10 new tests (106 total)

## 1.3.3 — Worker resilience (no more stuck queue after an error)

- **Double-worker bug fixed (root cause of `TargetClosedError`)**: after a
  platform update the worker restarted itself with `os.execv`, which on
  Windows leaves the old process's child running — TWO workers then fight
  over the same Chrome, closing each other's pages
  (`Target page, context or browser has been closed`) and stealing each
  other's queue pops, so a second prompt seemed to "not get picked up
  until restart". The worker now simply exits after an update and the
  supervisor (start.bat / run_worker.bat) restarts it on the new code
- **One worker per computer, enforced**: on startup the worker checks the
  live-worker registry for a twin on the same machine and yields instead
  of fighting over Chrome (a stale heartbeat from a crashed predecessor is
  waited out, never mistaken for a live twin); clean shutdown deregisters
  the heartbeat immediately so restarts are never blocked.
  `AIAUTO_ALLOW_MULTI_WORKER=1` overrides for multi-Chrome setups
- **Internet outages no longer kill jobs**: a `net::ERR_*` failure
  (address unreachable, DNS, disconnected, timed out…) now puts the
  prompt straight back in the queue WITHOUT consuming a retry, and the
  worker pauses 60s before trying again — jobs run automatically once
  the master computer's connection returns instead of failing
- **Chrome tab/window closed mid-job? Reconnect, don't die**: the browser
  manager detects closed-target errors, drops the stale CDP connection
  and reconnects from scratch before giving up
- run_worker.bat now auto-restarts the worker in a loop (update/crash safe)
- 13 new regression tests (96 total)

## 1.3.2 — Copy Image + download/save flow overhaul

- **📋 Copy Image button** in the image viewer: copies the actual image
  to the clipboard (PNG, converted via canvas when needed) so it pastes
  straight into Paint, Word, WhatsApp, Photoshop…; on plain-HTTP
  deployments (where browsers block the clipboard API) it shows the
  right-click → "Copy image" guidance instead
- **Inline view mode**: file links now include a `view_url`
  (Content-Disposition: inline) — the viewer and "Open in tab" display
  the real image, so the browser's native right-click/long-press
  Save image / Copy image gestures finally work; `url` still forces a
  download. Mobile gallery: Open in tab → long-press → Save image
- **Download feedback**: clicking Download now confirms where the file
  goes (browser Downloads), removing the "nothing happened" impression
- **Service worker rewritten network-first for the app shell**: the PWA
  can no longer keep serving a stale cached frontend after a platform
  update — a likely cause of fixes "not arriving" on staff machines;
  hashed assets stay cache-first, API calls are never cached

## 1.3.1 — Image download & stability fixes (end-to-end pass)

- **In-page image download**: images are now fetched INSIDE the ChatGPT
  page (same session, works for blob: URLs) with the request-context and
  screenshot methods as fallbacks — the most reliable capture chain
- **Longer settle for image replies** (5 stable seconds): the
  progressive render can keep src/size constant while pixels still load
- **Diagnostic dumps**: when an image cannot be captured, a full-page
  screenshot + HTML snapshot is saved to logs/ so the exact cause is
  visible instead of guessing
- **Worker auto-restarts after updates**: the worker watches the VERSION
  file and re-executes itself when the one-click updater installs new
  code — it can no longer keep running an old version silently
- **Native downloads (mobile gallery fix)**: files now download through
  short-lived signed links (`/files/{id}/link`) so browsers save them
  natively — desktop Downloads folder AND mobile Gallery/Photos both
  work; images open in a viewer with Download / Open-in-tab buttons and
  support long-press/right-click → Save image

## 1.3.0 — Public platform API + one-click startup

### Public REST API (`/api/public/v1`)
- API keys per user: create/rename/regenerate/disable/delete, scoped
  permissions, expiry dates, IP allowlists, per-key rate limits, usage
  statistics; keys hashed at rest and shown exactly once
- Async job endpoints: submit text/image jobs (JSON) or jobs with file
  uploads (multipart), poll status/progress, cancel, retry, list with
  status/type/date filters and pagination, download result files
- Webhooks: job.submitted/started/completed/failed, image.ready,
  file.ready — HMAC-SHA256 signed with timestamp replay protection and
  automatic retries (10s/60s backoff)
- Developer portal page in the web app: keys, webhooks (test button),
  usage dashboard with daily chart
- Docs: docs/PUBLIC_API.md guide, SDK examples (Python, Node.js/React,
  PHP/Laravel, C#, Kotlin, Flutter), Swagger explorer, ReDoc, OpenAPI
  JSON + YAML downloads
- All jobs processed exclusively by the central ChatGPT browser worker —
  no external AI provider anywhere

### One-click startup
- start.bat now does EVERYTHING: verifies environment + config, starts
  Redis (Windows service or local binary) if it is not running, starts
  the backend, opens Chrome with the dedicated logged-in profile and
  remote debugging (reconnecting instead of opening duplicate windows),
  starts the browser-automation worker, and verifies every component
  (DB, Redis, backend, worker, Chrome) before printing "System Ready"
- /api/health now reports worker and Chrome status; crashed services
  are restarted automatically; clear per-step errors on failure
- `--server-only` runs the central server without Chrome/worker

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
