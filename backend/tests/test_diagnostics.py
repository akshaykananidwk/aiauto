"""Admin image-capture diagnostics endpoints (v1.3.4)."""
import pytest

from app.core.config import ROOT_DIR
from tests.conftest import auth_headers

LOGS = ROOT_DIR / "logs"


@pytest.fixture
def debug_dump():
    LOGS.mkdir(exist_ok=True)
    dump = LOGS / "debug_test_20260101_000000.png"
    dump.write_bytes(b"\x89PNG\r\n\x1a\nfake-dump-data")
    log = LOGS / "worker.log"
    existed = log.exists()
    if not existed:
        log.write_text("line1\nline2\ncapture failed here\n", encoding="utf-8")
    yield dump
    dump.unlink(missing_ok=True)
    if not existed:
        log.unlink(missing_ok=True)


async def test_staff_cannot_access_diagnostics(client):
    headers = await auth_headers(client, "alice")
    res = await client.get("/api/v1/admin/system/diagnostics", headers=headers)
    assert res.status_code == 403


async def test_admin_sees_dumps_and_logs(client, debug_dump):
    headers = await auth_headers(client, "admin")
    res = await client.get("/api/v1/admin/system/diagnostics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert any(d["name"] == debug_dump.name for d in data["debug_dumps"])
    assert any(l["name"] == "worker.log" for l in data["logs"])


async def test_admin_opens_dump_inline(client, debug_dump):
    headers = await auth_headers(client, "admin")
    res = await client.get(
        f"/api/v1/admin/system/diagnostics/file?name={debug_dump.name}",
        headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")


async def test_log_tail_returns_last_lines(client, debug_dump):
    headers = await auth_headers(client, "admin")
    res = await client.get(
        "/api/v1/admin/system/diagnostics/tail?name=worker.log&lines=10",
        headers=headers)
    assert res.status_code == 200
    assert res.json()["lines"]  # non-empty tail


@pytest.mark.parametrize("name", [
    "../.env", "..%2F.env", "aiauto.db", "x" * 200, "debug.exe", ".env",
])
async def test_traversal_and_bad_names_rejected(client, name):
    headers = await auth_headers(client, "admin")
    res = await client.get(
        f"/api/v1/admin/system/diagnostics/file?name={name}", headers=headers)
    assert res.status_code in (400, 404)
