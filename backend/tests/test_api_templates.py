"""Prompt library: sharing rules, favorites, search, ownership."""
from tests.conftest import auth_headers


async def make(client, headers, **kwargs):
    body = {"title": "Weekly report", "body": "Write my weekly report about X", **kwargs}
    res = await client.post("/api/v1/templates", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


async def test_private_template_hidden_from_others(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    tpl = await make(client, alice, title="Alice private tpl", is_shared=False)

    bob_list = await client.get("/api/v1/templates", headers=bob)
    assert all(t["id"] != tpl["id"] for t in bob_list.json())

    shared = await make(client, alice, title="Alice shared tpl", is_shared=True)
    bob_list = await client.get("/api/v1/templates", headers=bob)
    assert any(t["id"] == shared["id"] for t in bob_list.json())


async def test_only_owner_can_edit_or_delete(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    tpl = await make(client, alice, title="Shared but owned", is_shared=True)

    res = await client.patch(f"/api/v1/templates/{tpl['id']}", headers=bob,
                             json={"title": "hijacked"})
    assert res.status_code == 403
    res = await client.delete(f"/api/v1/templates/{tpl['id']}", headers=bob)
    assert res.status_code == 403
    # owner can
    res = await client.patch(f"/api/v1/templates/{tpl['id']}", headers=alice,
                             json={"title": "renamed"})
    assert res.status_code == 200
    assert res.json()["title"] == "renamed"


async def test_favorites_and_search(client):
    alice = await auth_headers(client, "alice")
    tpl = await make(client, alice, title="Findable marketing plan",
                     category="Marketing", tags=["plan", "q3"])

    res = await client.post(f"/api/v1/templates/{tpl['id']}/favorite", headers=alice)
    assert res.json()["favorite"] is True

    favs = await client.get("/api/v1/templates?favorites_only=true", headers=alice)
    assert any(t["id"] == tpl["id"] for t in favs.json())

    hits = await client.get("/api/v1/templates?search=Findable", headers=alice)
    assert any(t["id"] == tpl["id"] for t in hits.json())

    by_tag = await client.get("/api/v1/templates?tag=q3", headers=alice)
    assert any(t["id"] == tpl["id"] for t in by_tag.json())

    cats = await client.get("/api/v1/templates/categories", headers=alice)
    assert "Marketing" in cats.json()

    # toggle off
    res = await client.post(f"/api/v1/templates/{tpl['id']}/favorite", headers=alice)
    assert res.json()["favorite"] is False


async def test_use_increments_counter(client):
    alice = await auth_headers(client, "alice")
    tpl = await make(client, alice, title="Counted tpl")
    res = await client.post(f"/api/v1/templates/{tpl['id']}/use", headers=alice)
    assert res.json()["usage_count"] == tpl["usage_count"] + 1
