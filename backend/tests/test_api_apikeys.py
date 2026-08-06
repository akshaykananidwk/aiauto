"""Personal API keys: creation, use as auth, revocation."""
from tests.conftest import auth_headers


async def test_api_key_lifecycle(client):
    headers = await auth_headers(client, "alice")

    created = await client.post("/api/v1/api-keys", headers=headers,
                                json={"name": "test-script"})
    assert created.status_code == 201, created.text
    body = created.json()
    plain = body["plain_key"]
    assert plain.startswith("ak_")

    # the plain key is never returned again
    listing = await client.get("/api/v1/api-keys", headers=headers)
    assert listing.status_code == 200
    assert all("plain_key" not in k for k in listing.json())

    # the key authenticates without a JWT
    me = await client.get("/api/v1/auth/me", headers={"X-API-Key": plain})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    # revoke → key stops working
    res = await client.delete(f"/api/v1/api-keys/{body['id']}", headers=headers)
    assert res.status_code == 200
    me = await client.get("/api/v1/auth/me", headers={"X-API-Key": plain})
    assert me.status_code == 401


async def test_invalid_api_key_rejected(client):
    res = await client.get("/api/v1/auth/me", headers={"X-API-Key": "ak_totally_fake"})
    assert res.status_code == 401


async def test_cannot_revoke_someone_elses_key(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    key = (await client.post("/api/v1/api-keys", headers=alice,
                             json={"name": "alice-key"})).json()
    res = await client.delete(f"/api/v1/api-keys/{key['id']}", headers=bob)
    assert res.status_code == 404
