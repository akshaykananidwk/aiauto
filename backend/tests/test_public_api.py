"""Public platform API: key management, auth, scopes, limits, jobs, webhooks."""
from datetime import datetime, timedelta, timezone

from app.core.security import sign_webhook
from tests.conftest import auth_headers


async def make_key(client, username="alice", **kwargs):
    headers = await auth_headers(client, username)
    res = await client.post("/api/v1/developer/keys", headers=headers,
                            json={"name": "test-key", **kwargs})
    assert res.status_code == 201, res.text
    return res.json(), headers


async def test_key_lifecycle_and_auth(client):
    key, session = await make_key(client)
    plain = key["plain_key"]
    assert plain.startswith("ak_")

    # authenticates the public API
    me = await client.get("/api/public/v1/me", headers={"X-API-Key": plain})
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "alice"

    # plain key never returned again
    listing = await client.get("/api/v1/developer/keys", headers=session)
    assert all("plain_key" not in k for k in listing.json())

    # rename + disable
    res = await client.patch(f"/api/v1/developer/keys/{key['id']}", headers=session,
                             json={"name": "renamed", "is_active": False})
    assert res.json()["name"] == "renamed"
    assert (await client.get("/api/public/v1/me",
                             headers={"X-API-Key": plain})).status_code == 401

    # re-enable + regenerate → old secret dead, new works
    await client.patch(f"/api/v1/developer/keys/{key['id']}", headers=session,
                       json={"is_active": True})
    regen = await client.post(f"/api/v1/developer/keys/{key['id']}/regenerate",
                              headers=session)
    new_plain = regen.json()["plain_key"]
    assert (await client.get("/api/public/v1/me",
                             headers={"X-API-Key": plain})).status_code == 401
    assert (await client.get("/api/public/v1/me",
                             headers={"X-API-Key": new_plain})).status_code == 200

    # delete → gone
    res = await client.delete(f"/api/v1/developer/keys/{key['id']}", headers=session)
    assert res.status_code == 200
    assert (await client.get("/api/public/v1/me",
                             headers={"X-API-Key": new_plain})).status_code == 401


async def test_missing_and_invalid_keys(client):
    assert (await client.get("/api/public/v1/me")).status_code == 401
    assert (await client.get("/api/public/v1/me",
                             headers={"X-API-Key": "ak_fake"})).status_code == 401


async def test_expired_key_rejected(client):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    key, _ = await make_key(client, expires_at=past)
    res = await client.get("/api/public/v1/me", headers={"X-API-Key": key["plain_key"]})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"]


async def test_scope_enforcement(client):
    key, _ = await make_key(client, scopes=["jobs:read"])
    headers = {"X-API-Key": key["plain_key"]}
    assert (await client.get("/api/public/v1/jobs", headers=headers)).status_code == 200
    res = await client.post("/api/public/v1/text", headers=headers,
                            json={"prompt": "not allowed"})
    assert res.status_code == 403
    assert "jobs:write" in res.json()["detail"]


async def test_ip_allowlist(client):
    key, _ = await make_key(client, ip_allowlist=["10.9.9.9"])
    res = await client.get("/api/public/v1/me", headers={"X-API-Key": key["plain_key"]})
    assert res.status_code == 403


async def test_per_key_rate_limit(client):
    key, _ = await make_key(client, rate_limit_per_minute=2)
    headers = {"X-API-Key": key["plain_key"]}
    assert (await client.get("/api/public/v1/me", headers=headers)).status_code == 200
    assert (await client.get("/api/public/v1/me", headers=headers)).status_code == 200
    assert (await client.get("/api/public/v1/me", headers=headers)).status_code == 429


async def test_job_workflow(client):
    key, _ = await make_key(client, username="bob")
    headers = {"X-API-Key": key["plain_key"]}

    created = await client.post("/api/public/v1/text", headers=headers,
                                json={"prompt": "api job test"})
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["type"] == "text" and job["status"] == "waiting"

    fetched = await client.get(f"/api/public/v1/jobs/{job['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["prompt"] == "api job test"

    listing = await client.get("/api/public/v1/jobs?status=waiting", headers=headers)
    assert any(j["id"] == job["id"] for j in listing.json()["items"])

    cancelled = await client.post(f"/api/public/v1/jobs/{job['id']}/cancel",
                                  headers=headers)
    assert cancelled.json()["status"] == "cancelled"
    retried = await client.post(f"/api/public/v1/jobs/{job['id']}/retry",
                                headers=headers)
    assert retried.json()["status"] == "waiting"

    # image convenience endpoint
    image = await client.post("/api/public/v1/images", headers=headers,
                              json={"prompt": "draw a cat"})
    assert image.status_code == 201
    assert image.json()["type"] == "image"


async def test_jobs_are_isolated_between_keys(client):
    alice_key, _ = await make_key(client, username="alice")
    bob_key, _ = await make_key(client, username="bob")
    job = (await client.post("/api/public/v1/text",
                             headers={"X-API-Key": alice_key["plain_key"]},
                             json={"prompt": "alice's api job"})).json()
    res = await client.get(f"/api/public/v1/jobs/{job['id']}",
                           headers={"X-API-Key": bob_key["plain_key"]})
    assert res.status_code == 404


async def test_webhook_management_and_signature(client):
    key, session = await make_key(client)
    headers = {"X-API-Key": key["plain_key"]}

    created = await client.post("/api/public/v1/webhooks", headers=headers,
                                json={"url": "https://example.com/hook",
                                      "events": ["job.completed"]})
    assert created.status_code == 201, created.text
    hook = created.json()
    assert hook["secret"].startswith("whsec_")  # shown exactly once

    listing = await client.get("/api/public/v1/webhooks", headers=headers)
    assert all("secret" not in h for h in listing.json())

    res = await client.post("/api/public/v1/webhooks", headers=headers,
                            json={"url": "https://example.com/x",
                                  "events": ["bad.event"]})
    assert res.status_code == 400

    # signature is deterministic HMAC-SHA256 over "timestamp.body"
    sig = sign_webhook("whsec_abc", "1786050000", b'{"event":"x"}')
    assert sig == sign_webhook("whsec_abc", "1786050000", b'{"event":"x"}')
    assert sig != sign_webhook("whsec_abc", "1786050001", b'{"event":"x"}')

    deleted = await client.delete(f"/api/public/v1/webhooks/{hook['id']}",
                                  headers=headers)
    assert deleted.status_code == 200


async def test_usage_dashboard(client):
    key, session = await make_key(client)
    await client.get("/api/public/v1/me", headers={"X-API-Key": key["plain_key"]})
    res = await client.get("/api/v1/developer/usage", headers=session)
    assert res.status_code == 200
    body = res.json()
    assert body["active_keys"] >= 1
    assert "total_requests" in body and "days" in body


async def test_openapi_documents_available(client):
    assert (await client.get("/api/openapi.json")).status_code == 200
    yaml_res = await client.get("/api/openapi.yaml")
    assert yaml_res.status_code == 200
    assert "openapi:" in yaml_res.text
