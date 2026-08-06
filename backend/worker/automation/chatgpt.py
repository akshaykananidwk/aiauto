"""Playwright automation of the logged-in ChatGPT Pro web session.

Flow per prompt:
    new chat → (attach uploads) → type prompt → send → wait until
    generation finishes → capture text → download images/files →
    (optionally delete the conversation) → return AIResult.

Robustness: every UI element is located through prioritized selector
lists (see selectors.py); completion is detected by the stop-button
disappearing AND the response text being stable, so streaming UI
changes don't break it.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import Locator, Page, TimeoutError as PWTimeout

from app.core.config import get_settings
from app.core.logging import get_logger
from worker.automation import selectors as sel
from worker.automation.base import AIResult, GenerationTimeoutError, LoginExpiredError
from worker.automation.browser import BrowserManager

logger = get_logger("worker.chatgpt")


async def find_first(page: Page, candidates: list[str], timeout_ms: int = 5000) -> Locator | None:
    """Return the first visible locator among candidate selectors."""
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    while asyncio.get_event_loop().time() < deadline:
        for css in candidates:
            loc = page.locator(css).first
            try:
                if await loc.is_visible():
                    return loc
            except Exception:
                continue
        await asyncio.sleep(0.25)
    return None


class ChatGPTProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.browser = BrowserManager()

    async def start(self) -> None:
        await self.browser.start()

    async def stop(self) -> None:
        await self.browser.stop()

    async def healthy(self) -> bool:
        return await self.browser.is_connected()

    # ---------- internals ----------

    async def _ensure_ready(self) -> Page:
        page = await self.browser.get_page()
        if "chatgpt" not in page.url and "openai" not in page.url:
            await page.goto(self.settings.chatgpt_url, wait_until="domcontentloaded",
                            timeout=60000)
        login = await find_first(page, sel.LOGIN_MARKERS, timeout_ms=2000)
        if login is not None:
            raise LoginExpiredError(
                "ChatGPT session is logged out on the master computer — "
                "an administrator must log in again"
            )
        return page

    async def _new_chat(self, page: Page) -> None:
        try:
            await page.goto(self.settings.chatgpt_url, wait_until="domcontentloaded",
                            timeout=60000)
            await asyncio.sleep(1.0)
        except PWTimeout:
            logger.warning("navigation to new chat timed out; continuing on current page")

    async def _attach_files(self, page: Page, paths: list[Path]) -> None:
        if not paths:
            return
        file_input = None
        for css in sel.FILE_UPLOAD_INPUT:
            loc = page.locator(css).first
            if await loc.count() > 0:
                file_input = loc
                break
        if file_input is None:
            attach = await find_first(page, sel.ATTACH_BUTTON, timeout_ms=3000)
            if attach:
                await attach.click()
                await asyncio.sleep(0.5)
                for css in sel.FILE_UPLOAD_INPUT:
                    loc = page.locator(css).first
                    if await loc.count() > 0:
                        file_input = loc
                        break
        if file_input is None:
            raise RuntimeError("could not find the file upload input in the ChatGPT UI")
        await file_input.set_input_files([str(p) for p in paths])
        # give the UI time to finish uploading before allowing send
        await asyncio.sleep(2.0 + 1.0 * len(paths))

    async def _type_and_send(self, page: Page, text: str) -> None:
        box = await find_first(page, sel.PROMPT_INPUT, timeout_ms=15000)
        if box is None:
            raise RuntimeError("could not find the ChatGPT prompt input")
        await box.click()
        # use insert_text via keyboard to preserve newlines without submitting
        await page.keyboard.insert_text(text)
        await asyncio.sleep(0.3)
        send = await find_first(page, sel.SEND_BUTTON, timeout_ms=10000)
        if send is None:
            await page.keyboard.press("Enter")
        else:
            await send.click()

    async def _wait_for_completion(self, page: Page, timeout_seconds: int) -> None:
        """Done when the stop button is gone and the last message stops growing."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_seconds
        # allow generation to actually start
        await asyncio.sleep(2.0)
        last_len = -1
        stable_ticks = 0
        while loop.time() < deadline:
            stop_visible = False
            for css in sel.STOP_BUTTON:
                try:
                    if await page.locator(css).first.is_visible():
                        stop_visible = True
                        break
                except Exception:
                    continue
            current = await self._last_message_text(page)
            if not stop_visible:
                if current and len(current) == last_len:
                    stable_ticks += 1
                    if stable_ticks >= 3:  # ~3s of no change and no stop button
                        return
                else:
                    stable_ticks = 0
            else:
                stable_ticks = 0
            last_len = len(current) if current else last_len
            await asyncio.sleep(1.0)
        raise GenerationTimeoutError(f"generation did not finish within {timeout_seconds}s")

    async def _last_message(self, page: Page) -> Locator | None:
        for css in sel.ASSISTANT_MESSAGE:
            loc = page.locator(css)
            if await loc.count() > 0:
                return loc.last
        return None

    async def _last_message_text(self, page: Page) -> str:
        msg = await self._last_message(page)
        if msg is None:
            return ""
        try:
            return (await msg.inner_text()).strip()
        except Exception:
            return ""

    async def _collect_images(self, page: Page) -> list[tuple[str, bytes]]:
        images: list[tuple[str, bytes]] = []
        msg = await self._last_message(page)
        if msg is None:
            return images
        seen: set[str] = set()
        for css in sel.MESSAGE_IMAGE:
            for img in await msg.locator(css).all():
                try:
                    src = await img.get_attribute("src") or ""
                    if not src or src in seen:
                        continue
                    seen.add(src)
                    data: bytes | None = None
                    if src.startswith("http"):
                        resp = await page.context.request.get(src)
                        if resp.ok:
                            data = await resp.body()
                    if data is None:  # blob:/data: URLs — screenshot the element
                        data = await img.screenshot(type="png")
                    images.append((f"image_{len(images) + 1}.png", data))
                except Exception as exc:
                    logger.warning("image download failed: %s", exc)
        return images

    async def _collect_files(self, page: Page) -> list[tuple[str, bytes]]:
        files: list[tuple[str, bytes]] = []
        msg = await self._last_message(page)
        if msg is None:
            return files
        for css in sel.FILE_DOWNLOAD_LINK:
            for link in await msg.locator(css).all():
                try:
                    name = (await link.inner_text()).strip() or "download.bin"
                    async with page.expect_download(timeout=60000) as dl_info:
                        await link.click()
                    download = await dl_info.value
                    path = await download.path()
                    if path:
                        files.append(
                            (download.suggested_filename or name, Path(path).read_bytes())
                        )
                except Exception as exc:
                    logger.warning("file download failed: %s", exc)
        return files

    async def _delete_conversation(self, page: Page) -> None:
        try:
            options = await find_first(page, sel.CONVERSATION_OPTIONS, timeout_ms=3000)
            if options is None:
                return
            await options.click()
            item = await find_first(page, sel.DELETE_MENU_ITEM, timeout_ms=3000)
            if item is None:
                return
            await item.click()
            confirm = await find_first(page, sel.DELETE_CONFIRM, timeout_ms=3000)
            if confirm is not None:
                await confirm.click()
                await asyncio.sleep(1.0)
            logger.info("conversation deleted from ChatGPT history")
        except Exception as exc:
            logger.warning("could not delete conversation (non-fatal): %s", exc)

    # ---------- public ----------

    async def run_prompt(
        self,
        prompt_text: str,
        upload_paths: list[Path],
        wants_image: bool,
        timeout_seconds: int,
    ) -> AIResult:
        page = await self._ensure_ready()
        await self._new_chat(page)
        await self._attach_files(page, upload_paths)
        await self._type_and_send(page, prompt_text)
        await self._wait_for_completion(page, timeout_seconds)

        text = await self._last_message_text(page)
        images = await self._collect_images(page)
        files = await self._collect_files(page)

        if self.settings.delete_conversations_after_run:
            await self._delete_conversation(page)

        return AIResult(text=text, images=images, files=files)
