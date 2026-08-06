# AIAuto — Feature List

All features are implemented and covered by the automated test suite
unless marked otherwise.

## Core platform

1. **Central AI gateway** — staff never touch the ChatGPT account; one managed session serves the whole office
2. **JWT authentication** — short-lived access tokens + refresh tokens
3. **Refresh token rotation** — a used refresh token is revoked instantly; reuse is rejected
4. **Logout revocation** — access tokens are blacklisted server-side on logout
5. **Brute-force lockout** — accounts lock after N failed logins (configurable)
6. **Role-based access** — admin / staff separation enforced at the API layer
7. **Personal API keys** — `X-API-Key` auth for scripts and integrations, hashed at rest, shown once
8. **Per-IP rate limiting** — separate stricter budget for login attempts
9. **Full audit trail** — every login, submission, job event, download, update and error
10. **Audit report export** — one-click CSV for compliance reviews

## Queue & jobs

11. **Priority FIFO queue** (Redis sorted set) — strict FIFO within a priority level
12. **Admin priority boost** — admins can jump the queue; staff cannot self-promote
13. **Automatic retries** with configurable retry count
14. **Job cancellation** — including race-safe cancellation of already-dequeued jobs
15. **Manual retry** of failed/cancelled jobs
16. **Live queue dashboard** with execution order and the currently running job
17. **Queue position feedback** for staff while waiting
18. **Multiple worker support** — every worker registers with its own heartbeat
19. **Automatic failover** — jobs stuck on a dead worker are re-queued by the watchdog
20. **Orphan recovery** — waiting jobs missing from Redis are re-enqueued automatically

## AI providers

21. **ChatGPT browser automation** (Playwright) — attaches to the logged-in Chrome via CDP
22. **OpenAI API provider** — text + image generation with exact token usage
23. **Anthropic Claude API provider** — text, images-in, PDFs-in
24. **Google Gemini API provider** — text, images-in, PDFs-in
25. **Per-prompt provider selection** — staff pick a provider or use the default
26. **Provider auto-switching / failover chain** — e.g. browser → OpenAI → Claude
27. **Resilient selectors** — every ChatGPT UI element has fallback selectors in one file
28. **Login-expiry detection** — admins are alerted the moment the ChatGPT session logs out
29. **Conversation cleanup** — each ChatGPT conversation can be auto-deleted after capture
30. **Document extraction** — PDF/text upload content is inlined for API providers (pypdf)
31. **OCR hook** — optional pytesseract image-to-text when installed

## Results & files

32. **Image download** with automatic thumbnails
33. **File download** — PDF, DOCX, XLSX, PPTX, ZIP and any other attachment
34. **Secure file serving** — per-file authorization, path-traversal-proof storage
35. **Upload support** — staff attach files that are fed to the AI
36. **Chat/history export** — personal history as CSV or JSON (conversation backup)
37. **Copy & read-aloud** — clipboard copy and voice output for responses
38. **Storage limits** with automatic admin alerts

## Usage management

39. **Token usage tracking** — exact for API providers, estimated for browser
40. **Cost tracking** — per prompt, per user, per department, per provider
41. **User quotas** — daily/monthly limits per user
42. **Department quotas** — daily/monthly limits per department
43. **Global default limits** — admin-configurable fallback quota
44. **Usage analytics dashboard** — daily chart, top users, by-department, by-provider
45. **Processing-time statistics**

## Productivity

46. **Prompt template library** — personal and team-shared templates
47. **Template categories, tags and search**
48. **Favorite prompts** (starred templates)
49. **Usage-count ranking** — most-used templates float to the top
50. **One-click "Use"** — templates prefill the prompt box
51. **Scheduled prompts** — once / every N minutes / daily / weekly (workflow automation)
52. **Voice input** — dictate prompts (browser speech recognition)
53. **Voice output** — read responses aloud

## Notifications

54. **In-app notification center** with unread badge
55. **Realtime WebSocket updates** — submitted → processing → generating → downloading → completed
56. **Desktop notifications** (browser Notification API)
57. **Email notifications** (SMTP)
58. **Telegram notifications** (per-user chat IDs)
59. **Generic webhook channel** — connect Slack, WhatsApp gateways (Twilio), or internal systems
60. **Admin alerts** — disk usage, worker/login problems

## Operations

61. **One-click GitHub updates** — check (commit list, version, dates) + update now
62. **Automatic pre-update backup** (code zip + pg_dump)
63. **Protected paths** — `.env`, `uploads/`, `storage/`, `config.php`, `plugins/` never overwritten
64. **Automatic DB migrations** during update (Alembic)
65. **Automatic cache clear** during update
66. **Automatic rollback** on any update error
67. **Update history** with status and backup reference
68. **Manual backup button + scheduled daily backups**
69. **Restore wizard** — pick a backup, confirm, restore
70. **Live system health** — CPU, memory, disk, DB, Redis, worker fleet
71. **Backup retention pruning**
72. **Plugin system** — drop-in Python hooks on all platform events
73. **Announcement banner** — admin broadcast to every user
74. **Structured rotating logs** + audit log with filters

## Deployment & DX

75. **One-command setup** — `./setup.sh` / `setup.bat` (venv, deps, .env, DB, admin, frontend)
76. **One-command start** — `./start.sh` / `start.bat` with health verification ("System Ready")
77. **.env auto-creation** on first run with generated SECRET_KEY
78. **Docker Compose stack** (PostgreSQL, Redis, backend, frontend)
79. **Single-process mode** — backend serves the built frontend directly
80. **Dark/light theme**, **mobile-responsive UI**, **PWA** (installable, offline shell)
81. **67+ automated tests** — auth, isolation, quotas, templates, API keys, queue math, update safety
82. **Load-test script** (`scripts/loadtest.py`)
83. **OpenAPI docs** at `/api/docs`
