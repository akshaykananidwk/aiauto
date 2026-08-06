"""Regression tests for the final-audit findings."""
from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers


async def test_api_key_cap_ignores_revoked_keys(client):
    headers = await auth_headers(client, "bob")
    created = []
    for i in range(10):
        res = await client.post("/api/v1/api-keys", headers=headers,
                                json={"name": f"cap-test-{i}"})
        assert res.status_code == 201
        created.append(res.json())
    # cap reached with 10 active keys
    res = await client.post("/api/v1/api-keys", headers=headers, json={"name": "over-cap"})
    assert res.status_code == 400
    # revoking one frees a slot — revoked keys must not count forever
    res = await client.delete(f"/api/v1/api-keys/{created[0]['id']}", headers=headers)
    assert res.status_code == 200
    res = await client.post("/api/v1/api-keys", headers=headers, json={"name": "after-revoke"})
    assert res.status_code == 201


async def test_pausing_and_resuming_once_schedule_keeps_run_time(client):
    headers = await auth_headers(client, "alice")
    run_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    created = await client.post("/api/v1/schedules", headers=headers, json={
        "title": "one shot", "prompt_text": "run me later",
        "schedule_type": "once", "run_once_at": run_at,
    })
    assert created.status_code == 201, created.text
    sched = created.json()
    assert sched["next_run_at"] is not None

    paused = await client.patch(f"/api/v1/schedules/{sched['id']}", headers=headers,
                                json={"is_active": False})
    assert paused.json()["is_active"] is False
    resumed = await client.patch(f"/api/v1/schedules/{sched['id']}", headers=headers,
                                 json={"is_active": True})
    body = resumed.json()
    assert body["is_active"] is True
    # the one-time run must survive the pause/resume cycle
    assert body["next_run_at"] is not None


async def test_orphan_sweep_waits_two_ticks(client, db, fake_redis):
    """A waiting prompt missing from the queue is only re-enqueued after
    being missing on two consecutive sweeps."""
    from app.services.queue import QueueService
    from app.services.scheduler import SchedulerService

    headers = await auth_headers(client, "alice")
    res = await client.post("/api/v1/prompts", headers=headers,
                            data={"prompt_text": "orphan test", "wants_image": "false"})
    prompt_id = res.json()["id"]

    queue = QueueService()
    # simulate the worker popping the job (gone from the queue, DB still waiting)
    await queue.pop_blocking(timeout=1)
    assert await queue.in_queue(prompt_id) is False

    scheduler = SchedulerService()
    await scheduler._requeue_orphans(db)
    assert await queue.in_queue(prompt_id) is False  # first sighting: marker only
    await scheduler._requeue_orphans(db)
    assert await queue.in_queue(prompt_id) is True   # second sighting: re-queued
