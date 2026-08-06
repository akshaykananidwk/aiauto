# API Reference

Base URL: `/api/v1` · Interactive docs: `GET /api/docs` (Swagger UI).

Authentication: `Authorization: Bearer <access_token>` on every request.
Access tokens expire after 30 min (default) — refresh with the refresh token.

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
| POST | `/prompts` | `multipart/form-data`: `prompt_text`, `wants_image` (bool), `priority` (admin only), `computer_name`, `files` (0..n uploads). → PromptOut, 201 |
| GET | `/prompts` | own prompts; admin may pass `all_users=true`. Filters: `status`, `search`, `page`, `page_size` |
| GET | `/prompts/{id}` | includes `queue_position` while waiting |
| POST | `/prompts/{id}/cancel` | waiting/processing only |
| POST | `/prompts/{id}/retry` | failed/cancelled only |

Statuses: `waiting → processing → completed | failed | cancelled`.

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
| PATCH | `/users/{id}` | update fields, reset password, enable |
| DELETE | `/users/{id}` | deactivate (soft) |
| GET | `/admin/queue` | live queue in execution order + running job |
| GET | `/admin/logs` | audit log; filters `event`, `level`, `user_id`, paging |
| GET/PUT | `/admin/settings` | runtime settings |

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
