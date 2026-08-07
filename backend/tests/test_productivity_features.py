"""v1.5.0 productivity features: size presets, regenerate, reference
images, prompt improver, full-text search, multi-account, timing
analytics and retention cleanup."""
import io

import pytest
from PIL import Image

from app.services.image_presets import (
    IMAGE_PRESETS,
    fit_to_preset,
    is_valid,
    size_instruction,
)
from app.services.prompt_builder import (
    REFERENCE_IMAGE_INSTRUCTION,
    build_image_prompt,
    build_improve_prompt,
    clean_improved_text,
)
from tests.conftest import auth_headers


def png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, "PNG")
    return buf.getvalue()


# ---- 5. output size presets ---------------------------------------------

def test_every_preset_has_usable_metadata():
    for key, preset in IMAGE_PRESETS.items():
        assert preset["label"]
        assert (preset["width"] > 0) == (key != "auto")


def test_size_instruction_mentions_the_aspect():
    assert "16:9" in size_instruction("landscape")
    assert size_instruction("auto") == ""


def test_unknown_preset_is_rejected():
    assert is_valid("square") and not is_valid("gigantic")


def test_image_is_fitted_to_the_exact_preset_size():
    out = fit_to_preset(png_bytes(1000, 1000), "landscape")
    with Image.open(io.BytesIO(out)) as im:
        assert (im.width, im.height) == (1920, 1080)


def test_auto_preset_leaves_the_image_untouched():
    original = png_bytes(640, 480)
    assert fit_to_preset(original, "auto") == original


def test_broken_image_data_is_returned_unchanged():
    """A formatting step must never cost the user their generated image."""
    assert fit_to_preset(b"not-an-image", "square") == b"not-an-image"


def test_size_sentence_reaches_the_ai_prompt():
    sent = build_image_prompt("a cat", image_size="vertical")
    assert "9:16" in sent and "a cat" in sent


async def test_submitting_with_a_size_preset(client):
    headers = await auth_headers(client, "alice")
    res = await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "a logo", "wants_image": "true", "image_size": "square"})
    assert res.status_code == 201
    assert res.json()["image_size"] == "square"


async def test_unknown_size_preset_is_a_400(client):
    headers = await auth_headers(client, "alice")
    res = await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "a logo", "wants_image": "true", "image_size": "huge"})
    assert res.status_code == 400


async def test_presets_are_listed_for_the_web_app(client):
    headers = await auth_headers(client, "alice")
    res = await client.get("/api/v1/prompts/image-sizes", headers=headers)
    assert res.status_code == 200
    assert {p["key"] for p in res.json()["presets"]} == set(IMAGE_PRESETS)


# ---- 6. regenerate -------------------------------------------------------

async def test_regenerate_creates_a_new_job_and_keeps_the_old_one(client):
    headers = await auth_headers(client, "alice")
    first = (await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "draw a tree", "wants_image": "true",
              "image_size": "portrait"})).json()

    res = await client.post(f"/api/v1/prompts/{first['id']}/regenerate", headers=headers)
    assert res.status_code == 201
    again = res.json()
    assert again["id"] != first["id"]
    assert again["prompt_text"] == "draw a tree"
    assert again["image_size"] == "portrait"     # settings carried over
    assert again["parent_id"] == first["id"]     # lineage recorded
    assert again["status"] == "waiting"

    # the original is untouched
    original = (await client.get(f"/api/v1/prompts/{first['id']}", headers=headers)).json()
    assert original["status"] == "waiting"


async def test_regenerate_carries_reference_uploads(client):
    headers = await auth_headers(client, "alice")
    first = (await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "like this", "wants_image": "true"},
        files={"files": ("ref.png", png_bytes(64, 64), "image/png")})).json()
    assert [f["kind"] for f in first["files"]] == ["upload"]

    again = (await client.post(
        f"/api/v1/prompts/{first['id']}/regenerate", headers=headers)).json()
    uploads = [f for f in again["files"] if f["kind"] == "upload"]
    assert len(uploads) == 1 and uploads[0]["filename"] == "ref.png"


async def test_regenerate_is_owner_only(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    mine = (await client.post("/api/v1/prompts", headers=alice,
                              data={"prompt_text": "mine"})).json()
    res = await client.post(f"/api/v1/prompts/{mine['id']}/regenerate", headers=bob)
    assert res.status_code == 404


# ---- 13. reference images ------------------------------------------------

def test_reference_sentence_only_when_images_are_attached():
    with_ref = build_image_prompt("a poster", has_reference_images=True)
    without = build_image_prompt("a poster", has_reference_images=False)
    assert REFERENCE_IMAGE_INSTRUCTION in with_ref
    assert REFERENCE_IMAGE_INSTRUCTION not in without


def test_instructions_are_not_duplicated_on_retry():
    once = build_image_prompt("a poster", image_size="square",
                              has_reference_images=True)
    assert build_image_prompt(once, image_size="square",
                              has_reference_images=True) == once


# ---- 16. prompt improver -------------------------------------------------

def test_improve_prompt_wraps_the_request():
    built = build_improve_prompt("કૂતરાનો ફોટો", wants_image=True)
    assert "કૂતરાનો ફોટો" in built
    assert "image generator" in built


@pytest.mark.parametrize("raw,expected", [
    ('"A golden retriever puppy"', "A golden retriever puppy"),
    ("Improved prompt: A sunset over hills", "A sunset over hills"),
    ("  plain text  ", "plain text"),
])
def test_improved_text_is_unwrapped(raw, expected):
    assert clean_improved_text(raw) == expected


async def test_improve_job_is_high_priority_and_hidden_from_history(client):
    headers = await auth_headers(client, "alice")
    res = await client.post("/api/v1/prompts/improve", headers=headers,
                            json={"prompt_text": "dog pic", "wants_image": True})
    assert res.status_code == 201
    job_id = res.json()["id"]

    detail = (await client.get(f"/api/v1/prompts/{job_id}", headers=headers)).json()
    assert detail["priority"] == 9          # jumps ahead of long image jobs
    assert "image generator" in detail["prompt_text"]

    listing = (await client.get("/api/v1/prompts", headers=headers)).json()
    assert job_id not in [p["id"] for p in listing["items"]]


async def test_improve_result_endpoint_reports_status(client):
    headers = await auth_headers(client, "alice")
    job = (await client.post("/api/v1/prompts/improve", headers=headers,
                             json={"prompt_text": "dog pic"})).json()
    res = await client.get(f"/api/v1/prompts/improve/{job['id']}", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "waiting"
    assert res.json()["improved_text"] is None


async def test_improve_endpoint_rejects_a_normal_prompt(client):
    headers = await auth_headers(client, "alice")
    normal = (await client.post("/api/v1/prompts", headers=headers,
                                data={"prompt_text": "hello"})).json()
    res = await client.get(f"/api/v1/prompts/improve/{normal['id']}", headers=headers)
    assert res.status_code == 404


# ---- 19. full-text search ------------------------------------------------

async def test_search_matches_prompt_and_answer(client, db):
    from sqlalchemy import select

    from app.models.prompt import Prompt

    headers = await auth_headers(client, "alice")
    await client.post("/api/v1/prompts", headers=headers,
                      data={"prompt_text": "quarterly budget summary"})
    other = (await client.post("/api/v1/prompts", headers=headers,
                               data={"prompt_text": "something else"})).json()

    # simulate the AI having answered the second one
    row = (await db.execute(select(Prompt).where(Prompt.id == other["id"]))).scalar_one()
    row.response_text = "The budget report is attached"
    await db.commit()

    found = (await client.get("/api/v1/prompts?search=budget", headers=headers)).json()
    assert found["total"] == 2  # matched in the request AND in the answer

    none = (await client.get("/api/v1/prompts?search=zzzznothing", headers=headers)).json()
    assert none["total"] == 0


async def test_search_never_crosses_users(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    await client.post("/api/v1/prompts", headers=alice,
                      data={"prompt_text": "alice secret plan"})
    found = (await client.get("/api/v1/prompts?search=secret", headers=bob)).json()
    assert found["total"] == 0


async def test_image_only_filter(client):
    headers = await auth_headers(client, "alice")
    tag = "filtertag7391"
    await client.post("/api/v1/prompts", headers=headers,
                      data={"prompt_text": f"{tag} text one"})
    await client.post("/api/v1/prompts", headers=headers,
                      data={"prompt_text": f"{tag} picture one", "wants_image": "true"})
    both = (await client.get(f"/api/v1/prompts?search={tag}", headers=headers)).json()
    assert both["total"] == 2
    only = (await client.get(
        f"/api/v1/prompts?search={tag}&only_images=true", headers=headers)).json()
    assert only["total"] == 1 and only["items"][0]["wants_image"] is True


# ---- 44. multi-account (one worker per browser, not per machine) ---------

async def test_heartbeat_records_the_browser_endpoint(client):
    from app.services.queue import QueueService

    queue = QueueService()
    await queue.register_heartbeat("pc1-a", chrome="connected", current_job=None,
                                   endpoint="http://localhost:9222")
    await queue.register_heartbeat("pc1-b", chrome="connected", current_job=None,
                                   endpoint="http://localhost:9223")
    workers = {w["id"]: w for w in await queue.live_workers()}
    assert workers["pc1-a"]["endpoint"] != workers["pc1-b"]["endpoint"]


def test_accounts_config_is_parsed(monkeypatch):
    """CHROME_ACCOUNTS gives each account its own port + profile."""
    import importlib
    import sys

    sys.path.insert(0, "/home/user/aiauto/scripts")
    start = importlib.import_module("start")
    start.CFG = {"cdp": "http://localhost:9222", "profile": "/tmp/p",
                 "accounts": "9222|/tmp/a,9223|/tmp/b"}
    accounts = start.load_accounts()
    assert [a["cdp"] for a in accounts] == ["http://localhost:9222",
                                            "http://localhost:9223"]
    assert [a["profile"] for a in accounts] == ["/tmp/a", "/tmp/b"]

    start.CFG = {"cdp": "http://localhost:9222", "profile": "/tmp/p", "accounts": ""}
    assert len(start.load_accounts()) == 1


# ---- 48. timing analytics ------------------------------------------------

async def test_timing_analytics_shape(client, db):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.prompt import Prompt, PromptStatus

    headers = await auth_headers(client, "alice")
    created = (await client.post("/api/v1/prompts", headers=headers,
                                 data={"prompt_text": "timed", "wants_image": "true"})).json()
    now = datetime.now(timezone.utc)
    row = (await db.execute(select(Prompt).where(Prompt.id == created["id"]))).scalar_one()
    row.status = PromptStatus.completed
    row.started_at = now - timedelta(seconds=120)
    row.completed_at = now - timedelta(seconds=30)
    await db.commit()

    admin = await auth_headers(client, "admin")
    data = (await client.get("/api/v1/admin/analytics?days=30", headers=admin)).json()
    timing = data["timing"]
    assert timing["images"]["count"] == 1
    assert timing["images"]["median"] == pytest.approx(90.0, abs=1)
    assert timing["success_rate"] == 100.0
    assert len(timing["by_hour"]) == 24


async def test_timing_analytics_is_admin_only(client):
    headers = await auth_headers(client, "alice")
    assert (await client.get("/api/v1/admin/analytics", headers=headers)).status_code == 403


# ---- 49. retention cleanup ----------------------------------------------

async def test_cleanup_removes_old_files_but_keeps_history(client, db):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.file import PromptFile
    from app.services.app_settings import AppSettingsService
    from app.schemas.settings import AdminSettingsUpdate
    from app.services.scheduler import SchedulerService
    from app.services.storage import StorageService

    headers = await auth_headers(client, "alice")
    prompt = (await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "old job"},
        files={"files": ("old.txt", b"old bytes", "text/plain")})).json()
    file_id = prompt["files"][0]["id"]
    row = (await db.execute(
        select(PromptFile).where(PromptFile.id == file_id))).scalar_one()
    path = StorageService().abs_path(row.rel_path)
    assert path.exists()

    # age the file beyond the retention window and enable cleanup
    row.created_at = datetime.now(timezone.utc) - timedelta(days=100)
    await db.commit()
    await AppSettingsService(db).update(AdminSettingsUpdate(file_retention_days=30))

    await SchedulerService()._cleanup_old_files(db)

    assert not path.exists()                       # file gone from disk
    assert (await db.execute(
        select(PromptFile).where(PromptFile.id == file_id))).scalar_one_or_none() is None
    kept = await client.get(f"/api/v1/prompts/{prompt['id']}", headers=headers)
    assert kept.status_code == 200                 # history row still readable
    assert kept.json()["prompt_text"] == "old job"


async def test_cleanup_does_nothing_when_retention_is_zero(client, db):
    from sqlalchemy import select

    from app.models.file import PromptFile
    from app.schemas.settings import AdminSettingsUpdate
    from app.services.app_settings import AppSettingsService
    from app.services.scheduler import SchedulerService

    # 0 = the shipped default: never delete anything
    await AppSettingsService(db).update(AdminSettingsUpdate(file_retention_days=0))
    headers = await auth_headers(client, "alice")
    prompt = (await client.post(
        "/api/v1/prompts", headers=headers, data={"prompt_text": "keep me"},
        files={"files": ("keep.txt", b"keep", "text/plain")})).json()
    file_id = prompt["files"][0]["id"]
    row = (await db.execute(
        select(PromptFile).where(PromptFile.id == file_id))).scalar_one()
    from datetime import datetime, timedelta, timezone

    row.created_at = datetime.now(timezone.utc) - timedelta(days=9999)
    await db.commit()

    await SchedulerService()._cleanup_old_files(db)  # retention 0 = never
    assert (await db.execute(
        select(PromptFile).where(PromptFile.id == file_id))).scalar_one_or_none() is not None
