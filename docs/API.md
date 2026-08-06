# API Reference

Base URL: `/api/v1` · Interactive docs: `GET /api/docs` (Swagger UI).

Authentication: `Authorization: Bearer <access_token>` **or** an
`X-API-Key: ak_…` header (create keys under *API Keys* in the app).
Access tokens expire after 30 min (default) — refresh with the refresh
token. Refresh tokens rotate: each refresh invalidates the previous one.

## Auth

| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/auth/login` | `{username, password, computer_name?}` | → `{access_token, refresh_token}` |
| POST | `/auth/refresh` | `{refresh_token}` | new token pair |
| POST | `/auth/logout` | — | audit-logged |
| GET | `/auth/me` | — | current user |
| POST | `/auth/change-password` | `{current_password, new_password}` | |

## Prompts

| Method | Path | Notes |
|---|---|---|
| POST | `/prompts` | `multipart/form-data`: `prompt_text`, `wants_image` (bool), `priority` (admin only), `provider` (`""`/`browser`/`openai`/`anthropic`/`gemini`), `computer_name`, `files` (0..n uploads). → PromptOut, 201. 429 when over quota |
| GET | `/prompts` | own prompts; admin may pass `all_users=true`. Filters: `status`, `search`, `page`, `page_size` |
| GET | `/prompts/quota` | caller's quota usage `{daily_used, daily_limit, monthly_used, monthly_limit}` |
| GET | `/prompts/export?fmt=json\|csv` | full personal history export |
| GET | `/prompts/{id}` | includes `queue_position` while waiting, provider/model/tokens/cost when done |
| POST | `/prompts/{id}/cancel` | waiting/processing only |
| POST | `/prompts/{id}/retry` | failed/cancelled only |

Statuses: `waiting → processing → completed | failed | cancelled`.

## Templates (prompt library)

| Method | Path | Notes |
|---|---|---|
| GET | `/templates` | visible = own + shared. Filters: `search`, `category`, `tag`, `favorites_only` |
| GET | `/templates/categories` | distinct visible categories |
| POST | `/templates` | `{title, body, category?, tags?, is_shared?}` |
| PATCH/DELETE | `/templates/{id}` | owner or admin only |
| POST | `/templates/{id}/favorite` | toggle; returns `{favorite: bool}` |
| POST | `/templates/{id}/use` | increments the usage counter |

## Scheduled prompts

| Method | Path | Notes |
|---|---|---|
| GET | `/schedules` | own (admin: all) |
| POST | `/schedules` | `schedule_type`: `once` (+`run_once_at`), `interval` (+`interval_minutes`), `daily`/`weekly` (+`run_at_time` "HH:MM" UTC, `weekday` 0-6) |
| PATCH | `/schedules/{id}` | pause/resume (`is_active`), retiming |
| DELETE | `/schedules/{id}` | |

## Notifications

| Method | Path | Notes |
|---|---|---|
| GET | `/notifications` | `unread_only`, paging; returns `{items, unread, total}` |
| POST | `/notifications/{id}/read` · `/notifications/read-all` | |

## API keys

| Method | Path | Notes |
|---|---|---|
| GET | `/api-keys` | prefixes only, never the full key |
| POST | `/api-keys` | returns `plain_key` exactly once |
| DELETE | `/api-keys/{id}` | revoke |

## Files

| Method | Path | Notes |
|---|---|---|
| GET | `/files/{id}/download` | authorized owner or admin; streams the file |
| GET | `/files/{id}/thumbnail` | PNG thumbnail (images only) |

## Dashboards

| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/staff` | own queue + usage stats |
| GET | `/dashboard/admin` | global stats, worker/Chrome/Playwright status |

## Admin

| Method | Path | Notes |
|---|---|---|
| GET | `/users` / POST `/users` | list / create |
| PATCH | `/users/{id}` | update fields, reset password, quotas (`daily_limit`, `monthly_limit`), `telegram_chat_id` |
| DELETE | `/users/{id}` | deactivate (soft) |
| GET | `/admin/queue` | live queue in execution order + running job |
| GET | `/admin/logs` | audit log; filters `event`, `level`, `user_id`, paging |
| GET/PUT | `/admin/settings` | runtime settings incl. default quotas + announcement |
| GET/PUT/DELETE | `/admin/quotas` | department quotas |
| GET | `/admin/analytics?days=N` | totals, daily series, top users, by department/provider |
| GET | `/admin/analytics/audit-report` | audit log as CSV |
| GET | `/admin/system/health` | CPU/mem/disk, DB/Redis status, worker fleet |
| GET/POST | `/admin/system/backups` | list / create backup |
| POST | `/admin/system/backups/restore` | `{name, confirm: true}` — restore wizard |
| GET | `/dashboard/announcement` | current banner (any authenticated user) |

## Update system (admin)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/update/config` | repo/branch, whether a token is stored, protected paths, current version+commit |
| PUT | `/admin/update/config` | `{repo, branch, token?, protected_paths?, auto_restart?}` — empty token keeps the stored one |
| POST | `/admin/update/check` | → `{update_available, latest_version, commits_behind, commits[{sha,message,author,date}]}` |
| POST | `/admin/update/run` | 202; runs the full pipeline in the background |
| GET | `/admin/update/status` | `{running, step, progress, log_tail}` |
| GET | `/admin/update/history` | past update records incl. rollbacks |

## WebSocket

`GET /api/v1/ws?token=<access_token>`

Server pushes JSON events; staff receive events for their own prompts,
admins receive everything:

```json
{"type": "prompt.completed", "user_id": 7, "admin_only": false,
 "data": {"prompt_id": "…", "images": 2, "files": 1}}
```

Types: `prompt.submitted`, `prompt.processing`, `prompt.generating_image`,
`prompt.downloading`, `prompt.completed`, `prompt.failed`,
`prompt.cancelled`, `queue.updated`, `worker.status`, `update.progress`.

## Errors

Errors return `{"detail": "message"}` with conventional status codes
(400 validation/domain, 401 auth, 403 role, 404 not found/hidden,
409 conflict, 429 rate-limited, 502 GitHub unreachable).
