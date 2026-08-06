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
from worker.automation.base import (
    AIResult,
    GenerationTimeoutError,
    ImageDownloadError,
    LoginExpiredError,
)
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
    name = "browser"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.browser = BrowserManager()
        # runtime-overridable from admin settings (worker sets this per job)
        self.delete_conversations = self.settings.delete_conversations_after_run

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

    async def _assistant_count(self, page: Page) -> int:
        for css in sel.ASSISTANT_MESSAGE:
            count = await page.locator(css).count()
            if count > 0:
                return count
        return 0

    async def _stop_visible(self, page: Page) -> bool:
        for css in sel.STOP_BUTTON:
            try:
                if await page.locator(css).first.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _image_generating(self, page: Page) -> bool:
        """True while ChatGPT shows a 'Creating image…' style indicator —
        the image is still rendering and must not be captured yet."""
        for css in sel.IMAGE_GENERATING:
            try:
                if await page.locator(css).first.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _image_state(self, page: Page, page_wide: bool = False) -> list[dict]:
        """Snapshot of candidate generated images: src + natural size +
        load state. Used both for completion detection (the snapshot must
        stop changing) and for collection."""
        msg = await self._last_message(page)
        scope = page if (page_wide or msg is None) else msg
        min_px = 256 if (page_wide or msg is None) else 64
        out: list[dict] = []
        seen: set[str] = set()
        for css in sel.MESSAGE_IMAGE:
            try:
                imgs = await scope.locator(css).all()
            except Exception:
                continue
            for img in imgs:
                try:
                    info = await img.evaluate(
                        "el => ({src: el.currentSrc || el.src || '', "
                        "w: el.naturalWidth, h: el.naturalHeight, done: el.complete})"
                    )
                except Exception:
                    continue
                src = info.get("src") or ""
                if not src or src in seen:
                    continue
                if info.get("w", 0) < min_px or info.get("h", 0) < min_px:
                    continue  # avatars, icons, placeholders
                seen.add(src)
                out.append(info)
        return out

    def _signature(self, text: str, images: list[dict]) -> tuple:
        return (len(text), tuple(sorted((i["src"], i["w"], i["h"]) for i in images)))

    async def _wait_for_completion(
        self, page: Page, timeout_seconds: int, baseline_count: int, wants_image: bool
    ) -> None:
        """Done when ALL of the following hold for ~3 consecutive seconds:
          * a NEW assistant message exists (count above the pre-send
            baseline — prevents capturing a stale answer),
          * the stop/streaming button is gone,
          * no 'Creating image…' indicator is visible,
          * the message state (text length + every image's src and natural
            size) has stopped changing, and
          * there is actually SOMETHING to capture (non-empty text or at
            least one fully-loaded image).

        Watching the images — not just the text — is essential: ChatGPT
        keeps rendering a generated image long after the caption text has
        stabilised, and image-only replies may contain no text at all."""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_seconds
        # allow generation to actually start
        await asyncio.sleep(2.0)
        last_sig: tuple | None = None
        stable_ticks = 0
        while loop.time() < deadline:
            if await self._assistant_count(page) <= baseline_count:
                await asyncio.sleep(1.0)
                continue  # our reply has not appeared yet

            text = await self._last_message_text(page)
            images = await self._image_state(page)
            sig = self._signature(text, images)

            busy = await self._stop_visible(page) or await self._image_generating(page)
            images_loaded = all(i.get("done") and i.get("src", "").strip() for i in images)
            has_content = bool(text) or bool(images)

            # image replies settle longer: ChatGPT's progressive render can
            # keep src and natural size constant while pixels still fill in
            needed = 5 if (wants_image or images) else 3
            if not busy and images_loaded and has_content and sig == last_sig:
                stable_ticks += 1
                if stable_ticks >= needed:
                    return
            else:
                stable_ticks = 0
            last_sig = sig
            await asyncio.sleep(1.0)
        raise GenerationTimeoutError(
            f"generation did not finish within {timeout_seconds}s"
            + (" (image was still rendering)" if wants_image else "")
        )

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

    async def _download_one_image(self, page: Page, src: str) -> bytes | None:
        """Download an image by src, validating it is REAL image data.

        Three strategies, most reliable first:
          1. fetch INSIDE the page (same session, same cookies — also the
             only way to read blob: URLs),
          2. Playwright's request context (browser cookies),
          3. screenshot of the rendered element.
        """
        # 1) in-page fetch → base64 (works for http(s), blob: and data:)
        try:
            data_url = await page.evaluate(
                """async (src) => {
                    try {
                        const resp = await fetch(src, {credentials: 'include'});
                        if (!resp.ok) return null;
                        const blob = await resp.blob();
                        return await new Promise((resolve) => {
                            const fr = new FileReader();
                            fr.onload = () => resolve(fr.result);
                            fr.onerror = () => resolve(null);
                            fr.readAsDataURL(blob);
                        });
                    } catch (e) { return null; }
                }""",
                src,
            )
            if data_url and data_url.startswith("data:"):
                import base64

                header, _, payload = data_url.partition(",")
                data = base64.b64decode(payload)
                if len(data) > 1000 and "image" in header:
                    return data
        except Exception as exc:
            logger.warning("in-page image fetch failed for %s: %s", src[:80], exc)

        # 2) request-context fetch with the browser's cookies
        if src.startswith("http"):
            try:
                resp = await page.context.request.get(src, timeout=60000)
                content_type = resp.headers.get("content-type", "")
                body = await resp.body()
                if resp.ok and content_type.startswith("image/") and len(body) > 1000:
                    return body
                logger.warning("image fetch rejected (%s, %s bytes, %s)",
                               resp.status, len(body), content_type)
            except Exception as exc:
                logger.warning("image fetch failed for %s: %s", src[:80], exc)

        # 3) screenshot the rendered element
        try:
            img = page.locator(f"img[src='{src}']").first
            if await img.count() > 0:
                data = await img.screenshot(type="png", timeout=15000)
                if len(data) > 1000:
                    return data
        except Exception as exc:
            logger.warning("image screenshot fallback failed: %s", exc)
        return None

    async def _collect_images(self, page: Page, wants_image: bool) -> list[tuple[str, bytes]]:
        """Download every generated image in the reply. When an image was
        requested, retries (message scope first, then page-wide) before
        giving up — the caller treats zero images as a hard failure."""
        attempts = 4 if wants_image else 1
        for attempt in range(1, attempts + 1):
            candidates = await self._image_state(page)
            if not candidates and wants_image:
                # some UI variants render the image outside the message div
                candidates = await self._image_state(page, page_wide=True)
            images: list[tuple[str, bytes]] = []
            for info in candidates:
                data = await self._download_one_image(page, info["src"])
                if data is not None:
                    images.append((f"image_{len(images) + 1}.png", data))
            if images or not wants_image:
                if wants_image:
                    logger.info("captured %s image(s) on attempt %s", len(images), attempt)
                return images
            if attempt < attempts:
                logger.info("no image captured yet (attempt %s/%s) — waiting…",
                            attempt, attempts)
                await asyncio.sleep(3.0)
        return []

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

    async def _dump_debug(self, page: Page, reason: str) -> None:
        """Save a screenshot + page HTML to logs/ so capture failures on the
        master computer can be diagnosed precisely. Never raises."""
        try:
            from datetime import datetime, timezone

            from app.core.config import ROOT_DIR

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            debug_dir = ROOT_DIR / "logs"
            debug_dir.mkdir(exist_ok=True)
            base = debug_dir / f"debug_{reason}_{stamp}"
            await page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
            html = await page.content()
            base.with_suffix(".html").write_text(html, encoding="utf-8")
            logger.warning("debug dump saved: %s.png / .html", base)
        except Exception as exc:
            logger.warning("debug dump failed: %s", exc)

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
        baseline = await self._assistant_count(page)
        await self._type_and_send(page, prompt_text)
        await self._wait_for_completion(page, timeout_seconds, baseline, wants_image)

        text = await self._last_message_text(page)
        images = await self._collect_images(page, wants_image)
        files = await self._collect_files(page)

        if wants_image and not images:
            # capture failed: dump diagnostics so the exact cause is visible,
            # and keep the conversation in ChatGPT as evidence
            await self._dump_debug(page, "image-capture-failed")
            raise ImageDownloadError(
                "an image was requested but none could be captured from the "
                "reply — a debug screenshot was saved to logs/ and the "
                "conversation was kept in ChatGPT for inspection"
                + (f"; reply text: {text[:200]}" if text else "")
            )

        if self.delete_conversations:
            await self._delete_conversation(page)

        return AIResult(text=text, images=images, files=files)
