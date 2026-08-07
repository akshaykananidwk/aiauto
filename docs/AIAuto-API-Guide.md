# AIAuto Platform API — Integration Guide

> Share this document with any developer who needs to integrate with the
> AIAuto platform. It is self-contained: authentication, the complete
> image-generation flow, text jobs, file downloads, webhooks and
> ready-to-run code examples are all here.

## 1. What this API is

AIAuto is a central AI automation platform. Your application submits a
**job** (text or image) over a simple REST API; the platform's central
server queues it, generates the result, and stores the output (text +
image files) for you to fetch. Your app never talks to any third-party
AI service and needs **no AI API keys of its own** — just one AIAuto
platform key.

```
Your app ──▶ AIAuto REST API ──▶ queue ──▶ AI generation ──▶ result stored
   ▲                                                            │
   └────────────── poll the job  /  receive a webhook ◀─────────┘
```

Everything is **asynchronous**: submitting returns a `job id`
immediately; the result arrives seconds-to-minutes later depending on
the queue. There is no streaming — results arrive as complete jobs.

## 2. Base URL & docs

| What | URL |
|---|---|
| Base URL | `http://<server>/api/public/v1` |
| Interactive explorer (Swagger) | `http://<server>/api/docs` |
| ReDoc reference | `http://<server>/api/redoc` |
| OpenAPI spec | `/api/openapi.json` · `/api/openapi.yaml` |

Replace `<server>` with the address the platform admin gives you
(e.g. `192.168.1.50:8000` on the office network). Use HTTPS in
production.

## 3. Authentication

Ask the platform admin (or any platform user) for an **API key** — they
create it on the platform's *Developer / API* page. Send it with every
request:

```
X-API-Key: ak_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- The plain key is shown **once** at creation — store it securely.
- Keys can carry scoped permissions, an expiry date, an IP allowlist
  and a custom rate limit. A key with no scopes selected can do
  everything.
- **Never** embed the key in a browser app or distributed mobile app —
  call the API from your own backend.

| Scope | Allows |
|---|---|
| `jobs:read` | read job status/results, list jobs |
| `jobs:write` | submit, cancel, retry jobs |
| `files:read` | download result files (images!) |
| `webhooks:manage` | manage webhooks via the API |

## 4. THE IMAGE FLOW (step by step)

This is the flow most integrations need. Three calls:

### Step 1 — submit the image job

```bash
curl -X POST http://<server>/api/public/v1/images \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "A premium gold-themed poster of Dwarkadhish temple, ornate details"}'
```

Response `201`:

```json
{
  "id": "e6b5dde7b53f4ffc9283bbe84d717999",
  "type": "image",
  "status": "waiting",
  "progress": 10,
  "queue_position": 1,
  "prompt": "A premium gold-themed poster…",
  "response": null,
  "error": null,
  "created_at": "2026-08-07T09:00:00Z",
  "files": []
}
```

Save the `id` — it is the permanent reference.

### Step 2 — poll until it finishes

```bash
curl http://<server>/api/public/v1/jobs/e6b5dde7b53f4ffc9283bbe84d717999 \
  -H "X-API-Key: $KEY"
```

`status` moves `waiting → processing → completed` (or `failed` /
`cancelled`). Poll every 3–5 seconds. Image generation typically takes
**1–4 minutes** (plus queue time), so be patient and use a generous
overall timeout (10+ minutes). When completed:

```json
{
  "id": "e6b5dde7…",
  "status": "completed",
  "progress": 100,
  "response": "Here is your generated image.",
  "files": [
    {
      "id": 42,
      "name": "image_1.png",
      "kind": "result_image",
      "mime_type": "image/png",
      "size_bytes": 431922,
      "url": "/api/public/v1/files/42"
    }
  ]
}
```

### Step 3 — download the image file

```bash
curl -o result.png http://<server>/api/public/v1/files/42 \
  -H "X-API-Key: $KEY"
```

The body is the raw binary image — save it, display it, attach it,
anything. Files stay downloadable later; re-fetch by id at any time.

### Complete Python example (copy-paste ready)

```python
import time
import requests

BASE = "http://<server>/api/public/v1"
HEADERS = {"X-API-Key": "ak_your_key_here"}

def generate_image(prompt: str, timeout_s: int = 900) -> bytes:
    # 1) submit
    job = requests.post(f"{BASE}/images", headers=HEADERS,
                        json={"prompt": prompt}, timeout=30).json()
    job_id = job["id"]
    print("submitted:", job_id)

    # 2) poll
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = requests.get(f"{BASE}/jobs/{job_id}", headers=HEADERS,
                           timeout=30).json()
        print(f"  status={job['status']} progress={job.get('progress')}")
        if job["status"] == "completed":
            break
        if job["status"] in ("failed", "cancelled"):
            raise RuntimeError(f"job {job['status']}: {job.get('error')}")
        time.sleep(4)
    else:
        raise TimeoutError("image did not finish in time")

    # 3) download the first result image
    images = [f for f in job["files"] if f["kind"] == "result_image"]
    if not images:
        raise RuntimeError("job completed but returned no image")
    resp = requests.get(f"{BASE}{images[0]['url']}", headers=HEADERS,
                        timeout=60)
    resp.raise_for_status()
    return resp.content

if __name__ == "__main__":
    png = generate_image("A minimalist mountain logo, flat design")
    with open("logo.png", "wb") as fh:
        fh.write(png)
    print("saved logo.png")
```

### Complete Node.js example

```js
const BASE = "http://<server>/api/public/v1";
const HEADERS = { "X-API-Key": "ak_your_key_here" };

async function generateImage(prompt) {
  // 1) submit
  let res = await fetch(`${BASE}/images`, {
    method: "POST",
    headers: { ...HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  const { id } = await res.json();

  // 2) poll (up to 15 min)
  for (let i = 0; i < 225; i++) {
    await new Promise(r => setTimeout(r, 4000));
    res = await fetch(`${BASE}/jobs/${id}`, { headers: HEADERS });
    const job = await res.json();
    if (job.status === "completed") {
      const img = job.files.find(f => f.kind === "result_image");
      if (!img) throw new Error("completed but no image");
      // 3) download
      const file = await fetch(`${BASE}${img.url}`, { headers: HEADERS });
      return Buffer.from(await file.arrayBuffer());
    }
    if (["failed", "cancelled"].includes(job.status))
      throw new Error(`job ${job.status}: ${job.error}`);
  }
  throw new Error("timed out");
}

generateImage("A minimalist mountain logo, flat design")
  .then(buf => require("fs").writeFileSync("logo.png", buf));
```

### PHP example

```php
<?php
$base = "http://<server>/api/public/v1";
$key  = "ak_your_key_here";

function call($method, $url, $key, $json = null) {
    $ch = curl_init($url);
    $headers = ["X-API-Key: $key"];
    if ($json !== null) {
        $headers[] = "Content-Type: application/json";
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($json));
    }
    curl_setopt_array($ch, [CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_HTTPHEADER => $headers, CURLOPT_RETURNTRANSFER => true]);
    $out = curl_exec($ch); curl_close($ch);
    return $out;
}

$job = json_decode(call("POST", "$base/images", $key,
    ["prompt" => "A minimalist mountain logo, flat design"]), true);

do {
    sleep(4);
    $job = json_decode(call("GET", "$base/jobs/{$job['id']}", $key), true);
} while (in_array($job["status"], ["waiting", "processing"]));

if ($job["status"] === "completed") {
    foreach ($job["files"] as $f) {
        if ($f["kind"] === "result_image") {
            file_put_contents("result.png", call("GET", $base . $f["url"], $key));
            echo "saved result.png\n";
        }
    }
} else {
    echo "job {$job['status']}: {$job['error']}\n";
}
```

## 5. Text jobs

Identical flow, different endpoint — the answer arrives in `response`:

```bash
curl -X POST http://<server>/api/public/v1/text \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"prompt": "Write a 3-line product description for a steel bottle"}'
```

Poll `GET /jobs/{id}` until `completed`, then read the `response` field.

## 6. Jobs with file uploads

Attach documents/images the AI should work on (`multipart/form-data`;
PDF, DOCX, XLSX, TXT, images, ZIP — validated and size-capped):

```bash
curl -X POST http://<server>/api/public/v1/jobs \
  -H "X-API-Key: $KEY" \
  -F "prompt=Summarise this document in 5 bullet points" \
  -F "type=text" \
  -F "files=@report.pdf"
```

## 7. All endpoints at a glance

| Method & path | Purpose |
|---|---|
| `POST /text` | submit a text job (JSON) |
| `POST /images` | submit an image job (JSON) |
| `POST /jobs` | submit with file uploads (multipart) |
| `GET /jobs/{id}` | job status + result + files |
| `GET /jobs` | list jobs — filters: `status`, `type`, `created_after`, `created_before`, `page`, `page_size` (max 100) |
| `POST /jobs/{id}/cancel` | cancel a waiting/processing job |
| `POST /jobs/{id}/retry` | re-queue a failed/cancelled job |
| `GET /files/{file_id}` | download a result file (binary) |
| `GET /me` | identify the key, see limits/usage |
| `POST /webhooks` · `GET /webhooks` · `DELETE /webhooks/{id}` | manage webhooks |

## 8. Webhooks (instead of polling)

Register a URL once; the platform POSTs events to it:
`job.submitted`, `job.started`, `job.completed`, `job.failed`,
`image.ready`, `file.ready`.

```bash
curl -X POST http://<server>/api/public/v1/webhooks \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://yourapp.com/aiauto-hook",
       "events": ["job.completed", "job.failed"]}'
```

The response contains the signing `secret` (`whsec_…`) **once**. Every
delivery carries:

```
X-AIAuto-Event:     job.completed
X-AIAuto-Timestamp: 1786050000
X-AIAuto-Signature: hex(HMAC_SHA256(secret, "{timestamp}.{raw_body}"))
```

Verify before trusting (Python):

```python
import hashlib, hmac, time

def verify(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:      # replay protection
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

On `job.completed` / `image.ready`, fetch `GET /jobs/{id}` and download
the files. Respond `2xx` quickly (failed deliveries retry after 10 s
and 60 s); do heavy work asynchronously.

## 9. Errors, statuses & limits

**Job statuses:** `waiting → processing → completed | failed | cancelled`
(plus `progress` 0–100 and `queue_position` while waiting).

**HTTP errors** — body is always `{ "detail": "reason" }`:

| Code | Meaning | What to do |
|---|---|---|
| 400 | validation / invalid state | fix the request |
| 401 | missing/invalid/expired key | check the key |
| 403 | missing scope or IP not allowed | ask for the right key |
| 404 | not found (or another user's job) | check the id |
| 429 | rate limit or quota exceeded | wait `Retry-After` seconds |
| 5xx | server problem | retry with backoff |

**Rate limit:** default 60 requests/minute per key (the
`X-RateLimit-Remaining` header shows what is left). Daily/monthly
prompt quotas may also apply per user.

**Transient failures:** the platform automatically retries generation
internally (including browser/network hiccups on the generation
machine). Treat `failed` as final — the `error` field says why — and use
`POST /jobs/{id}/retry` if you want another attempt.

## 10. Integration best practices

- **Prefer webhooks over polling** for anything high-volume; if you
  poll, use 3–5 s intervals with an overall timeout of 10–15 minutes
  for images.
- **Store job ids** in your database — they are the permanent link to
  results and files.
- **Download and store important images on your side**; don't hot-link
  the API from end-user browsers (they don't have your key anyway).
- **Scope keys minimally** (e.g. a reporting script only needs
  `jobs:read` + `files:read`) and set expiry dates for temporary work.
- **Rotate keys** with *Regenerate* on the platform — the old value
  stops working instantly.
- Handle `429` by honouring `Retry-After`, and `5xx` with exponential
  backoff (2 s → 4 s → 8 s).

---

*Questions? The interactive explorer at `/api/docs` lets you try every
endpoint live with your key (click Authorize → paste the key).*
