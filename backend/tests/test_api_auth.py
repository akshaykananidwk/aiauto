"""Auth API: login, lockout, refresh rotation, logout revocation."""
import pytest

from tests.conftest import auth_headers, login


async def test_login_success(client):
    tokens = await login(client, "alice")
    assert tokens["access_token"] and tokens["refresh_token"]


async def test_login_wrong_password(client):
    res = await client.post("/api/v1/auth/login",
                            json={"username": "alice", "password": "wrong-password"})
    assert res.status_code == 401


async def test_login_unknown_user(client):
    res = await client.post("/api/v1/auth/login",
                            json={"username": "nobody", "password": "whatever1"})
    assert res.status_code == 401


async def test_me_requires_auth(client):
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401


async def test_me_returns_profile(client):
    headers = await auth_headers(client, "alice")
    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "alice"
    assert body["role"] == "staff"
    assert "hashed_password" not in body


async def test_brute_force_lockout(client):
    # LOGIN_MAX_FAILURES=3 in the test env
    for _ in range(3):
        await client.post("/api/v1/auth/login",
                          json={"username": "bob", "password": "bad-password"})
    res = await client.post("/api/v1/auth/login",
                            json={"username": "bob", "password": "password123"})
    assert res.status_code == 423  # locked even with the right password


async def test_refresh_rotation_blocks_reuse(client):
    tokens = await login(client, "alice")
    first = await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    # the original refresh token was rotated out — reuse must fail
    reused = await client.post("/api/v1/auth/refresh",
                               json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401
    # the new pair still works
    again = await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": first.json()["refresh_token"]})
    assert again.status_code == 200


async def test_logout_revokes_access_token(client):
    headers = await auth_headers(client, "alice")
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_access_token_rejected_as_refresh(client):
    tokens = await login(client, "alice")
    res = await client.post("/api/v1/auth/refresh",
                            json={"refresh_token": tokens["access_token"]})
    assert res.status_code == 401


async def test_change_password_requires_current(client):
    headers = await auth_headers(client, "bob")
    res = await client.post("/api/v1/auth/change-password", headers=headers,
                            json={"current_password": "nope", "new_password": "newpassword1"})
    assert res.status_code in (400, 423)  # wrong current (or locked from earlier test)
