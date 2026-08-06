# AIAuto — Feature List

All processing runs through ONE AI backend: the master computer's
logged-in **ChatGPT Pro browser session**. There are no external AI API
integrations anywhere in the platform — no API keys, no per-token costs.

## Core platform

1. **Central AI gateway** — staff never touch the ChatGPT account; one managed session serves the whole office
2. **JWT authentication** — short-lived access tokens + refresh tokens
3. **Refresh token rotation** — a used refresh token is revoked instantly; reuse is rejected
4. **Logout revocation** — access tokens are blacklisted server-side on logout
5. **Brute-force lockout** — accounts lock after N failed logins (configurable)
6. **Role-based access** — admin / staff separation enforced at the API layer
7. **Per-IP rate limiting** — separate stricter budget for login attempts
8. **Full audit trail** — every login, submission, job event, download, update and error
9. **Audit report export** — one-click CSV for compliance reviews

## Queue & jobs

10. **Priority FIFO queue** (Redis sorted set) — strict FIFO within a priority level
11. **Admin priority boost** — admins can jump the queue; staff cannot self-promote
12. **Automatic retries** with configurable retry count
13. **Job cancellation** — including race-safe cancellation of already-running jobs
14. **Manual retry** of failed/cancelled jobs
15. **Live queue dashboard** with execution order and the currently running job
16. **Queue position feedback** for staff while waiting
17. **Multiple worker support** — every worker registers with its own heartbeat
18. **Automatic failover** — jobs stuck on a dead worker are re-queued by the watchdog
19. **Orphan recovery** — waiting jobs missing from Redis are re-enqueued automatically

## ChatGPT browser automation

20. **Playwright automation** — attaches to the already-running, logged-in Chrome via CDP
21. **Persistent-profile fallback** — launches Chrome with the logged-in profile if CDP is down
22. **No re-login ever** — the master computer stays permanently signed in
23. **Resilient selectors** — every ChatGPT UI element has fallback selectors in one file
24. **Reliable completion detection** — anchored to a pre-send message baseline + stability check
25. **Login-expiry detection** — admins are alerted the moment the ChatGPT session logs out
26. **Conversation cleanup** — each conversation can be auto-deleted after capture
27. **File uploads to ChatGPT** — staff attachments are fed into the browser session

## Results & files

28. **Image download** with automatic thumbnails
29. **File download** — PDF, DOCX, XLSX, PPTX, ZIP and any other attachment
30. **Secure file serving** — per-file authorization, path-traversal-proof storage
31. **Chat/history export** — personal history as CSV or JSON (conversation backup)
32. **Copy & read-aloud** — clipboard copy and voice output for responses
33. **Storage limits** with automatic admin alerts

## Usage management

34. **User quotas** — daily/monthly prompt limits per user
35. **Department quotas** — daily/monthly limits per department
36. **Global default limits** — admin-configurable fallback quota
37. **Usage analytics dashboard** — daily chart, top users, by-department, images generated
38. **Processing-time statistics**

## Productivity

39. **Prompt template library** — personal and team-shared templates
40. **Template categories, tags and search**
41. **Favorite prompts** (starred templates)
42. **Usage-count ranking** — most-used templates float to the top
43. **One-click "Use"** — templates prefill the prompt box
44. **Scheduled prompts** — once / every N minutes / daily / weekly (workflow automation)
45. **Voice input** — dictate prompts (browser speech recognition)
46. **Voice output** — read responses aloud

## Notifications

47. **In-app notification center** with unread badge
48. **Realtime WebSocket updates** — submitted → processing → generating → downloading → completed
49. **Desktop notifications** (browser Notification API)
50. **Email notifications** (SMTP)
51. **Telegram notifications** (per-user chat IDs)
52. **Generic webhook channel** — connect Slack, WhatsApp gateways (Twilio), or internal systems
53. **Admin alerts** — disk usage, worker/login problems

## Operations

54. **One-click GitHub updates** — check (commit list, version, dates) + update now
55. **Automatic pre-update backup** (code zip + database backup)
56. **Protected paths** — `.env`, `uploads/`, `storage/`, `config.php`, `plugins/` never overwritten
57. **Automatic DB migrations** during update (Alembic), downgraded on rollback
58. **Dependency install + frontend rebuild** during update when they changed
59. **Automatic rollback** on any update error
60. **Update history** with status and backup reference
61. **Manual backup button + scheduled daily backups**
62. **Restore wizard** — pick a backup, confirm, restore
63. **Live system health** — CPU, memory, disk, DB, Redis, worker fleet
64. **Backup retention pruning**
65. **Plugin system** — drop-in Python hooks on all platform events
66. **Announcement banner** — admin broadcast to every user
67. **Structured rotating logs** + audit log with filters

## Deployment & DX

68. **One-command setup** — `./setup.sh` / `setup.bat` (venv, deps, .env, DB, admin, frontend)
69. **One-command start** — `./start.sh` / `start.bat` with health verification ("System Ready")
70. **.env auto-creation** on first run with generated SECRET_KEY
71. **Docker Compose stack** (PostgreSQL, Redis, backend, frontend)
72. **Single-process mode** — backend serves the built frontend directly
73. **Dark/light theme**, **mobile-responsive UI**, **PWA** (installable, offline shell)
74. **70+ automated tests** — auth, isolation, quotas, templates, queue math, update safety
75. **Load-test script** (`scripts/loadtest.py`)
76. **OpenAPI docs** at `/api/docs`
