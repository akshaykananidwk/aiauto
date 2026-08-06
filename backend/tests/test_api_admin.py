"""Admin endpoints: role enforcement, settings, quotas, notifications."""
from tests.conftest import auth_headers


ADMIN_PATHS = [
    "/api/v1/admin/queue",
    "/api/v1/admin/logs",
    "/api/v1/admin/settings",
    "/api/v1/admin/quotas",
    "/api/v1/admin/analytics",
    "/api/v1/admin/system/health",
    "/api/v1/admin/system/backups",
    "/api/v1/admin/update/config",
    "/api/v1/dashboard/admin",
    "/api/v1/users",
]


async def test_staff_forbidden_from_admin_endpoints(client):
    headers = await auth_headers(client, "alice")
    for path in ADMIN_PATHS:
        res = await client.get(path, headers=headers)
        assert res.status_code == 403, f"{path} returned {res.status_code} for staff"


async def test_admin_settings_roundtrip_and_announcement(client):
    admin = await auth_headers(client, "admin")
    staff = await auth_headers(client, "alice")

    res = await client.put("/api/v1/admin/settings", headers=admin,
                           json={"announcement": "Maintenance tonight 22:00",
                                 "default_daily_limit": 100})
    assert res.status_code == 200
    assert res.json()["announcement"] == "Maintenance tonight 22:00"
    assert res.json()["default_daily_limit"] == 100

    # staff see the announcement through the public endpoint
    res = await client.get("/api/v1/dashboard/announcement", headers=staff)
    assert res.json()["announcement"] == "Maintenance tonight 22:00"

    # clear again to not affect other tests
    res = await client.put("/api/v1/admin/settings", headers=admin,
                           json={"announcement": "", "default_daily_limit": 0})
    assert res.status_code == 200


async def test_department_quota_crud(client):
    admin = await auth_headers(client, "admin")
    res = await client.put("/api/v1/admin/quotas", headers=admin,
                           json={"department": "Sales", "daily_limit": 50, "monthly_limit": 500})
    assert res.status_code == 200
    assert res.json()["daily_limit"] == 50

    listing = await client.get("/api/v1/admin/quotas", headers=admin)
    assert any(q["department"] == "Sales" for q in listing.json())

    res = await client.delete("/api/v1/admin/quotas/Sales", headers=admin)
    assert res.status_code == 200
    listing = await client.get("/api/v1/admin/quotas", headers=admin)
    assert all(q["department"] != "Sales" for q in listing.json())


async def test_system_health_shape(client):
    admin = await auth_headers(client, "admin")
    res = await client.get("/api/v1/admin/system/health", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert body["database_ok"] is True
    assert "disk_used_percent" in body
    assert isinstance(body["workers"], list)


async def test_analytics_shape(client):
    admin = await auth_headers(client, "admin")
    res = await client.get("/api/v1/admin/analytics?days=7", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert {"totals", "daily", "top_users", "by_department", "by_provider"} <= body.keys()
    assert len(body["daily"]) == 7


async def test_notifications_flow(client, db):
    from app.models.user import User
    from sqlalchemy import select
    from app.services.notify import NotificationService

    alice = (await db.execute(select(User).where(User.username == "alice"))).scalar_one()
    svc = NotificationService(db)
    await svc.notify(alice, "info", "Test notification", "body here",
                     external=False, commit=True)

    headers = await auth_headers(client, "alice")
    res = await client.get("/api/v1/notifications", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["unread"] >= 1
    notif = next(n for n in body["items"] if n["title"] == "Test notification")

    res = await client.post(f"/api/v1/notifications/{notif['id']}/read", headers=headers)
    assert res.status_code == 200

    # bob cannot read alice's notification
    bob = await auth_headers(client, "bob")
    res = await client.post(f"/api/v1/notifications/{notif['id']}/read", headers=bob)
    assert res.status_code == 404

    res = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert res.status_code == 200
    res = await client.get("/api/v1/notifications?unread_only=true", headers=headers)
    assert res.json()["unread"] == 0


async def test_health_endpoint_public(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["database"] is True
