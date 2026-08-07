"""Chrome connection management for the master computer.

Strategy:
  1. Try to ATTACH to an already-running Chrome via CDP
     (started with --remote-debugging-port=9222). This reuses the exact
     browser where ChatGPT Pro is logged in — no second login ever.
  2. If Chrome is GONE (closed/crashed mid-job), RELAUNCH the real
     Chrome ourselves with the same profile + debug port — exactly like
     start.py does — and attach to it. This keeps ONE Chrome that both
     the worker and any later start.bat run can find.
  3. Only as a last resort, launch a Playwright-managed Chrome with the
     persistent profile (no debug port — other tools can't reuse it).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("worker.browser")


def find_chrome() -> str | None:
    """Locate the installed Google Chrome binary (mirrors scripts/start.py)."""
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
            / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LocalAppData", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for path in candidates:
            if path.is_file():
                return str(path)
        return None
    import shutil

    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


class BrowserManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.attached_over_cdp = False

    async def start(self) -> BrowserContext:
        # idempotent: called before every job — reuse a live connection
        # instead of leaking a Playwright driver per job
        if self._context is not None:
            if await self.is_connected():
                return self._context
            await self.stop()  # stale connection — clean up before reconnecting

        self.attached_over_cdp = False  # reset — may fall back to launching
        self._pw = await async_playwright().start()

        # 1) attach to the running, logged-in Chrome
        if self.settings.chrome_cdp_url:
            if await self._attach_cdp():
                return self._context

            # 2) Chrome is gone (closed/crashed) — relaunch the REAL Chrome
            # with the same profile + debug port, then attach. Never launch
            # a second, debug-less Chrome that start.bat can't find.
            if await self._relaunch_chrome() and await self._attach_cdp(
                attempts=12, delay=2.0
            ):
                return self._context
            logger.warning("could not reach or relaunch Chrome over CDP — "
                           "falling back to a Playwright-managed Chrome")

        # 3) last resort: Playwright-managed Chrome with the login profile
        if not self.settings.chrome_profile_dir:
            raise RuntimeError(
                "Cannot reach Chrome: start Chrome with --remote-debugging-port=9222 "
                "or set CHROME_PROFILE_DIR"
            )
        self._context = await self._pw.chromium.launch_persistent_context(
            self.settings.chrome_profile_dir,
            headless=self.settings.chrome_headless,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            accept_downloads=True,
        )
        logger.info("launched Chrome with persistent profile %s",
                    self.settings.chrome_profile_dir)
        return self._context

    async def _attach_cdp(self, attempts: int = 1, delay: float = 0.0) -> bool:
        """Try to attach to Chrome's debug port; True on success."""
        for attempt in range(1, attempts + 1):
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    self.settings.chrome_cdp_url, timeout=5000
                )
                self._context = (
                    self._browser.contexts[0]
                    if self._browser.contexts
                    else await self._browser.new_context()
                )
                self.attached_over_cdp = True
                logger.info("attached to running Chrome via CDP at %s",
                            self.settings.chrome_cdp_url)
                return True
            except Exception as exc:
                if attempt == attempts:
                    logger.warning("CDP attach failed (%s)", exc)
                elif delay:
                    await asyncio.sleep(delay)
        return False

    async def _relaunch_chrome(self) -> bool:
        """Start the real Chrome with profile + debug port (like start.py).
        Only for a local CDP endpoint; True if the process was spawned."""
        host = (urlparse(self.settings.chrome_cdp_url).hostname or "").lower()
        if host not in ("localhost", "127.0.0.1", "::1"):
            return False  # remote Chrome — nothing we can relaunch here
        chrome = find_chrome()
        if chrome is None:
            logger.warning("Chrome executable not found — cannot relaunch it")
            return False
        profile = self.settings.chrome_profile_dir or str(Path.home() / "aiauto-chrome")
        port = urlparse(self.settings.chrome_cdp_url).port or 9222
        logger.warning("Chrome is not running — relaunching it with profile %s "
                       "on debug port %s", profile, port)
        try:
            subprocess.Popen(
                [chrome,
                 f"--remote-debugging-port={port}",
                 f"--user-data-dir={profile}",
                 "--no-first-run",
                 "--no-default-browser-check",
                 self.settings.chatgpt_url],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as exc:
            logger.error("failed to relaunch Chrome: %s", exc)
            return False

    async def get_page(self) -> Page:
        # Chrome tabs/windows can be closed under us at any time (user closes
        # the window, Chrome restarts, CDP target dies). On a closed-target
        # error, drop the stale connection and reconnect once from scratch.
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                if self._context is None:
                    await self.start()
                assert self._context is not None
                chatgpt_url = self.settings.chatgpt_url
                for page in self._context.pages:
                    if page.is_closed():
                        continue
                    if chatgpt_url.split("//")[-1] in page.url:
                        return page
                page = await self._context.new_page()
                await page.goto(chatgpt_url, wait_until="domcontentloaded", timeout=60000)
                return page
            except Exception as exc:
                last_exc = exc
                if attempt == 1 and self._looks_closed(exc):
                    logger.warning("Chrome target closed (%s) — reconnecting", exc)
                    await self.stop()
                    continue
                raise
        raise last_exc  # unreachable, keeps type checkers happy

    @staticmethod
    def _looks_closed(exc: Exception) -> bool:
        msg = str(exc).lower()
        return ("has been closed" in msg or "target closed" in msg
                or "browser closed" in msg or "targetclosederror" in msg
                or type(exc).__name__ == "TargetClosedError")

    async def is_connected(self) -> bool:
        try:
            if self._context is None:
                return False
            if self._browser is not None and not self._browser.is_connected():
                return False
            return True
        except Exception:
            return False

    async def stop(self) -> None:
        try:
            if self._context is not None and not self.attached_over_cdp:
                await self._context.close()
            if self._browser is not None and not self.attached_over_cdp:
                await self._browser.close()
        finally:
            self._context = None
            self._browser = None
            self.attached_over_cdp = False
            if self._pw is not None:
                await self._pw.stop()
                self._pw = None
