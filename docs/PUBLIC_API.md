# AIAuto Public API — Developer Guide

Integrate your websites, desktop software, mobile apps, ERP and CRM
systems directly with the platform. Every job is processed internally by
the central ChatGPT Pro browser session — your applications never talk
to any third-party AI service.

**Base URL:** `https://your-server/api/public/v1`
**Interactive explorer:** `/api/docs` (click *Authorize*, paste your key)
**ReDoc reference:** `/api/redoc` · **Spec:** `/api/openapi.json` / `/api/openapi.yaml`
**SDK examples:** [`docs/sdk-examples/`](sdk-examples/)

## Authentication

Create a key on the platform's **API** page (each user manages their own
keys, with optional permissions, expiry, IP allowlist and rate limit).
Send it with every request:

```
X-API-Key: ak_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Keys are stored hashed (SHA-256); the plain key is shown exactly once.
Regenerating a key invalidates the old value immediately. Always use
HTTPS in production.

### Permissions (scopes)

| Scope | Allows |
|---|---|
| `jobs:read` | read job status/results, list jobs |
| `jobs:write` | submit, cancel, retry jobs |
| `files:read` | download result/uploaded files |
| `webhooks:manage` | manage webhooks via the API |

A key with no scopes selected has all permissions.

## Request & response format

Requests are JSON (`Content-Type: application/json`) except uploads,
which use `multipart/form-data`. Responses are JSON. Timestamps are ISO
8601 UTC. Errors always look like:

```json
{ "detail": "human-readable reason" }
```

| Code | Meaning |
|---|---|
| 400 | validation error / invalid state (e.g. cancelling a finished job) |
| 401 | missing, invalid, disabled or expired API key |
| 403 | missing scope or IP not allowed |
| 404 | not found (or belongs to another user) |
| 429 | rate limit or prompt quota exceeded — respect `Retry-After` |
| 5xx | server problem — retry with backoff |

## Rate limits

Default **60 requests/minute per key** (configurable per key). The
`X-RateLimit-Remaining` response header shows what is left in the
current window; on 429, wait for `Retry-After` seconds. Prompt quotas
(daily/monthly per user) also apply and return 429.

## Jobs — asynchronous processing

Submitting returns immediately with a **job id**; generation happens on
the master computer. Poll the job or register a webhook.

Job statuses: `waiting → processing → completed | failed | cancelled`
(plus `progress` 0–100 and `queue_position` while waiting).

### Submit

```bash
# text
curl -X POST https://server/api/public/v1/text \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a product description for a steel bottle"}'

# image
curl -X POST https://server/api/public/v1/images \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "A minimalist logo of a mountain, flat design"}'

# with file uploads (images, PDF, DOCX, XLSX, TXT, ZIP — validated & size-capped)
curl -X POST https://server/api/public/v1/jobs \
  -H "X-API-Key: $KEY" \
  -F "prompt=Summarise this document" -F "type=text" \
  -F "files=@report.pdf"
```

Response (`201`):

```json
{
  "id": "0dfbc6522fd840b993f2fcd1d2fe7d57",
  "type": "text", "status": "waiting", "progress": 10,
  "queue_position": 1, "prompt": "…", "response": null,
  "error": null, "created_at": "2026-08-07T09:00:00Z",
  "files": []
}
```

### Poll / manage

```
GET  /jobs/{id}                 job with response text + files when done
GET  /jobs?status=completed     filters: status, type, created_after,
                                created_before, page, page_size (max 100)
POST /jobs/{id}/cancel
POST /jobs/{id}/retry           failed/cancelled jobs only
GET  /files/{file_id}           download a result file (binary)
GET  /me                        identify the key + limits
```

Completed jobs include their files:

```json
"files": [{ "id": 12, "name": "image_1.png", "kind": "result_image",
            "mime_type": "image/png", "size_bytes": 431922,
            "url": "/api/public/v1/files/12" }]
```

Pagination: `page` (1-based) + `page_size`; responses carry
`total`, `page`, `page_size`.

> Streaming responses are not available — generation runs through a
> browser session, so results arrive as complete jobs. Use webhooks for
> push-style delivery.

## Webhooks

Register a URL and receive events instead of polling:
`job.submitted`, `job.started`, `job.completed`, `job.failed`,
`image.ready`, `file.ready`.

```bash
curl -X POST https://server/api/public/v1/webhooks \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://yourapp.com/aiauto-hook", "events": ["job.completed","job.failed"]}'
```

The response contains the signing `secret` (`whsec_…`) **once**.
Deliveries are POSTs with:

```
X-AIAuto-Event:     job.completed
X-AIAuto-Timestamp: 1786050000
X-AIAuto-Signature: hex(HMAC_SHA256(secret, "{timestamp}.{raw_body}"))
```

Verify (Python):

```python
import hmac, hashlib, time

def verify(secret, timestamp, body: bytes, signature) -> bool:
    if abs(time.time() - int(timestamp)) > 300:   # replay protection
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Failed deliveries are retried (after 10 s and 60 s). Respond `2xx`
quickly; do heavy work asynchronously.

## Best practices

- Poll with backoff (2–5 s) or prefer webhooks; jobs behind a queue can
  take minutes when the office is busy.
- Store the job `id` — it is the permanent reference for results/files.
- Treat `failed` as final after the platform's automatic retries; the
  `error` field explains why.
- Scope keys minimally (a reporting script needs only `jobs:read` +
  `files:read`) and set expiry dates for temporary integrations.
- Rotate keys with *Regenerate* — the old value dies instantly.
- Never embed keys in client-side code (browsers, mobile apps you
  distribute); proxy through your own backend.

## Security summary

API-key auth (hashed at rest) · per-key rate limits · optional IP
allowlists & expiry · scoped permissions · signed webhooks with
timestamp replay protection · full audit logging · strict input and
file validation · errors never leak internals.
