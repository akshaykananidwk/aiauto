"""Prompt API: submission, isolation between staff, cancel/retry, quotas."""
from tests.conftest import auth_headers


async def submit(client, headers, text="hello ai", **extra):
    data = {"prompt_text": text, "wants_image": "false", **extra}
    res = await client.post("/api/v1/prompts", headers=headers, data=data)
    return res


async def test_submit_and_list(client):
    headers = await auth_headers(client, "alice")
    res = await submit(client, headers, "summarise this quarter")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "waiting"
    assert body["queue_position"] == 1

    listing = await client.get("/api/v1/prompts", headers=headers)
    assert listing.status_code == 200
    assert any(p["id"] == body["id"] for p in listing.json()["items"])


async def test_staff_cannot_see_others_prompts(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    created = (await submit(client, alice, "alice private prompt")).json()

    # direct read is hidden
    res = await client.get(f"/api/v1/prompts/{created['id']}", headers=bob)
    assert res.status_code == 404
    # list never contains it, even with all_users (staff cannot escalate)
    listing = await client.get("/api/v1/prompts?all_users=true", headers=bob)
    assert all(p["id"] != created["id"] for p in listing.json()["items"])
    # and bob cannot cancel it either
    res = await client.post(f"/api/v1/prompts/{created['id']}/cancel", headers=bob)
    assert res.status_code == 404


async def test_admin_sees_all_prompts(client):
    alice = await auth_headers(client, "alice")
    admin = await auth_headers(client, "admin")
    created = (await submit(client, alice, "for admin eyes")).json()
    listing = await client.get("/api/v1/prompts?all_users=true", headers=admin)
    assert any(p["id"] == created["id"] for p in listing.json()["items"])


async def test_cancel_then_retry(client):
    headers = await auth_headers(client, "alice")
    prompt = (await submit(client, headers)).json()

    res = await client.post(f"/api/v1/prompts/{prompt['id']}/cancel", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"

    res = await client.post(f"/api/v1/prompts/{prompt['id']}/retry", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "waiting"

    # completed prompts cannot be cancelled
    res = await client.post(f"/api/v1/prompts/{prompt['id']}/cancel", headers=headers)
    assert res.status_code == 200  # still waiting → cancellable again
    res = await client.post(f"/api/v1/prompts/{prompt['id']}/cancel", headers=headers)
    assert res.status_code == 400  # already cancelled


async def test_staff_priority_is_ignored(client):
    headers = await auth_headers(client, "alice")
    res = await submit(client, headers, "try to jump the queue", priority="9")
    assert res.status_code == 201
    assert res.json()["priority"] == 0


async def test_daily_quota_enforced(client):
    admin = await auth_headers(client, "admin")
    bob = await auth_headers(client, "bob")
    me = await client.get("/api/v1/auth/me", headers=bob)
    bob_id = me.json()["id"]

    res = await client.patch(f"/api/v1/users/{bob_id}", headers=admin,
                             json={"daily_limit": 1})
    assert res.status_code == 200

    first = await submit(client, bob, "bob's first today")
    assert first.status_code == 201
    second = await submit(client, bob, "bob's second today")
    assert second.status_code == 429
    assert "limit" in second.json()["detail"]

    quota = await client.get("/api/v1/prompts/quota", headers=bob)
    assert quota.status_code == 200
    assert quota.json()["daily_limit"] == 1


async def test_history_export(client):
    headers = await auth_headers(client, "alice")
    await submit(client, headers, "exportable prompt")
    res = await client.get("/api/v1/prompts/export?fmt=csv", headers=headers)
    assert res.status_code == 200
    assert "exportable prompt" in res.text
    res = await client.get("/api/v1/prompts/export?fmt=json", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
