"""Worker resilience: network-outage detection, heartbeat deregistration,
and closed-Chrome-target recognition (v1.3.3 fixes)."""
import pytest

from app.services.queue import QueueService
from worker.automation.browser import BrowserManager
from worker.main import NETWORK_ERROR_MARKERS


# ---- network-outage detection (jobs must NOT burn retries on these) ----

@pytest.mark.parametrize("message", [
    "Page.goto: net::ERR_ADDRESS_UNREACHABLE at https://chatgpt.com/",
    "Page.goto: net::ERR_INTERNET_DISCONNECTED at https://chatgpt.com/",
    "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://chatgpt.com/",
    "net::ERR_CONNECTION_RESET",
    "net::ERR_TIMED_OUT",
])
def test_network_errors_are_recognised(message):
    assert any(m in message.lower() for m in NETWORK_ERROR_MARKERS)


@pytest.mark.parametrize("message", [
    "ImageDownloadError: an image was requested but none arrived",
    "LoginExpiredError: ChatGPT session is logged out",
    "GenerationTimeoutError: no reply",
])
def test_normal_failures_are_not_network_errors(message):
    assert not any(m in message.lower() for m in NETWORK_ERROR_MARKERS)


# ---- closed-target detection (BrowserManager reconnects instead of dying) ----

@pytest.mark.parametrize("message", [
    "Locator.count: Target page, context or browser has been closed",
    "TargetClosedError: target closed",
    "Browser closed unexpectedly",
])
def test_closed_target_errors_are_recognised(message):
    assert BrowserManager._looks_closed(Exception(message))


def test_ordinary_errors_do_not_trigger_reconnect():
    assert not BrowserManager._looks_closed(Exception("Timeout 60000ms exceeded"))


# ---- heartbeat deregistration (clean shutdown must unblock restart) ----

async def test_deregister_removes_heartbeat(client):
    queue = QueueService()
    await queue.register_heartbeat("pc1-111", chrome="connected", current_job=None)
    assert any(w["id"] == "pc1-111" for w in await queue.live_workers())
    await queue.deregister_worker("pc1-111")
    assert not any(w["id"] == "pc1-111" for w in await queue.live_workers())
