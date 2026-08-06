"""Chrome connection management for the master computer.

Strategy:
  1. Try to ATTACH to an already-running Chrome via CDP
     (started with --remote-debugging-port=9222). This reuses the exact
     browser where ChatGPT Pro is logged in — no second login ever.
  2. Fall back to LAUNCHING a Chrome with the configured persistent
     profile directory, which also carries the login cookies.
"""
from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("worker.browser")


class BrowserManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.attached_over_cdp = False

    async def start(self) -> BrowserContext:
        self._pw = await async_playwright().start()

        # 1) attach to the running, logged-in Chrome
        if self.settings.chrome_cdp_url:
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
                return self._context
            except Exception as exc:
                logger.warning("CDP attach failed (%s) — falling back to persistent profile", exc)

        # 2) launch with the persistent logged-in profile
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

    async def get_page(self) -> Page:
        if self._context is None:
            await self.start()
        assert self._context is not None
        chatgpt_url = self.settings.chatgpt_url
        for page in self._context.pages:
            if chatgpt_url.split("//")[-1] in page.url:
                return page
        page = await self._context.new_page()
        await page.goto(chatgpt_url, wait_until="domcontentloaded", timeout=60000)
        return page

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
            if self._pw is not None:
                await self._pw.stop()
                self._pw = None
