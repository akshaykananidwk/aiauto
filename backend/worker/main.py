"""AIAuto worker — runs on the master computer.

Consumes the Redis queue, drives the AI provider (ChatGPT browser
session or OpenAI API), stores results and files, and publishes
realtime status events. Run with:

    python -m worker.main
"""
from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import async_session_factory, init_db
from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.services import events
from app.services.audit import audit
from app.services.queue import (
    CHROME_STATUS_KEY,
    CURRENT_JOB_KEY,
    HEARTBEAT_KEY,
    QueueService,
)
from app.services.redis_client import close_redis, get_redis
from app.services.storage import StorageService, guess_mime, is_image
from worker.automation.base import AIProvider, AIResult, GenerationTimeoutError, LoginExpiredError

logger = get_logger("worker")


def build_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "api":
        from worker.automation.openai_api import OpenAIAPIProvider

        return OpenAIAPIProvider()
    from worker.automation.chatgpt import ChatGPTProvider

    return ChatGPTProvider()


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.queue = QueueService()
        self.storage = StorageService()
        self.provider = build_provider()
        self.stopping = asyncio.Event()

    # ---------- status ----------

    async def _heartbeat_loop(self) -> None:
        redis = get_redis()
        while not self.stopping.is_set():
            try:
                await redis.set(HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=15)
                healthy = await self.provider.healthy()
                await redis.set(CHROME_STATUS_KEY, "connected" if healthy else "disconnected",
                                ex=15)
            except Exception as exc:
                logger.warning("heartbeat failed: %s", exc)
            await asyncio.sleep(5)

    # ---------- job processing ----------

    async def _save_result(self, db, prompt: Prompt, result: AIResult) -> None:
        for filename, data in result.images:
            rel, size = self.storage.save_bytes("results", prompt.id, filename, data)
            thumb = self.storage.make_thumbnail(rel)
            db.add(PromptFile(
                prompt_id=prompt.id, kind=FileKind.result_image, filename=filename,
                rel_path=rel, thumb_rel_path=thumb, mime_type=guess_mime(filename),
                size_bytes=size,
            ))
        for filename, data in result.files:
            rel, size = self.storage.save_bytes("results", prompt.id, filename, data)
            kind = FileKind.result_image if is_image(filename) else FileKind.result_file
            thumb = self.storage.make_thumbnail(rel) if kind == FileKind.result_image else None
            db.add(PromptFile(
                prompt_id=prompt.id, kind=kind, filename=filename, rel_path=rel,
                thumb_rel_path=thumb, mime_type=guess_mime(filename), size_bytes=size,
            ))

    async def _process(self, prompt_id: str) -> None:
        redis = get_redis()
        await redis.set(CURRENT_JOB_KEY, prompt_id, ex=self.settings.job_timeout_seconds + 60)
        async with async_session_factory() as db:
            prompt = await db.get(Prompt, prompt_id)
            if prompt is None:
                logger.warning("queued prompt %s not found in DB", prompt_id)
                return
            if prompt.status != PromptStatus.waiting:
                logger.info("skipping prompt %s in status %s", prompt_id, prompt.status)
                return
            if await self.queue.is_cancelled(prompt_id):
                prompt.status = PromptStatus.cancelled
                prompt.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            prompt.status = PromptStatus.processing
            prompt.started_at = datetime.now(timezone.utc)
            await audit(db, "prompt.started", f"prompt {prompt.id} started",
                        user_id=prompt.user_id, meta={"prompt_id": prompt.id})
            await db.commit()
            await events.publish(events.PROMPT_PROCESSING, {"prompt_id": prompt.id},
                                 user_id=prompt.user_id)
            if prompt.wants_image:
                await events.publish(events.PROMPT_GENERATING_IMAGE,
                                     {"prompt_id": prompt.id}, user_id=prompt.user_id)

            upload_paths: list[Path] = [
                self.storage.abs_path(f.rel_path)
                for f in prompt.files
                if f.kind == FileKind.upload and self.storage.abs_path(f.rel_path).exists()
            ]

            try:
                result = await asyncio.wait_for(
                    self.provider.run_prompt(
                        prompt.prompt_text,
                        upload_paths,
                        prompt.wants_image,
                        self.settings.response_timeout_seconds,
                    ),
                    timeout=self.settings.job_timeout_seconds,
                )
                await events.publish(events.PROMPT_DOWNLOADING, {"prompt_id": prompt.id},
                                     user_id=prompt.user_id)
                await self._save_result(db, prompt, result)
                prompt.response_text = result.text
                prompt.status = PromptStatus.completed
                prompt.completed_at = datetime.now(timezone.utc)
                await audit(db, "prompt.completed",
                            f"prompt {prompt.id} completed "
                            f"({len(result.images)} images, {len(result.files)} files)",
                            user_id=prompt.user_id, meta={"prompt_id": prompt.id})
                await db.commit()
                await events.publish(
                    events.PROMPT_COMPLETED,
                    {"prompt_id": prompt.id,
                     "images": len(result.images), "files": len(result.files)},
                    user_id=prompt.user_id,
                )
            except Exception as exc:
                await self._handle_failure(db, prompt, exc)
        await redis.delete(CURRENT_JOB_KEY)

    async def _handle_failure(self, db, prompt: Prompt, exc: Exception) -> None:
        retryable = not isinstance(exc, LoginExpiredError)
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("prompt %s failed: %s", prompt.id, error_msg)

        if isinstance(exc, (GenerationTimeoutError, asyncio.TimeoutError)):
            error_msg = "The AI did not finish in time. The job can be retried."

        if retryable and prompt.retry_count < self.settings.job_retry_count:
            prompt.retry_count += 1
            prompt.status = PromptStatus.waiting
            prompt.error = error_msg
            await audit(db, "prompt.retry",
                        f"prompt {prompt.id} auto-retry {prompt.retry_count}",
                        user_id=prompt.user_id, level="warning",
                        meta={"prompt_id": prompt.id, "error": error_msg})
            await db.commit()
            await self.queue.enqueue(prompt.id, prompt.priority)
            # reset the browser between retries — cheap insurance
            await self._restart_provider()
            return

        prompt.status = PromptStatus.failed
        prompt.error = error_msg
        prompt.completed_at = datetime.now(timezone.utc)
        await audit(db, "prompt.failed", f"prompt {prompt.id} failed: {error_msg}",
                    user_id=prompt.user_id, level="error",
                    meta={"prompt_id": prompt.id})
        await db.commit()
        await events.publish(events.PROMPT_FAILED,
                             {"prompt_id": prompt.id, "error": error_msg},
                             user_id=prompt.user_id)
        if isinstance(exc, LoginExpiredError):
            await events.publish(events.WORKER_STATUS,
                                 {"error": "login_expired", "message": str(exc)},
                                 admin_only=True)

    async def _restart_provider(self) -> None:
        try:
            await self.provider.stop()
        except Exception:
            pass
        try:
            await self.provider.start()
        except Exception as exc:
            logger.error("provider restart failed: %s", exc)

    # ---------- main loop ----------

    async def run(self) -> None:
        setup_logging()
        await init_db()
        logger.info("worker starting (provider=%s)", self.settings.ai_provider)
        try:
            await self.provider.start()
        except Exception as exc:
            logger.error("provider start failed (will keep retrying): %s", exc)

        heartbeat = asyncio.create_task(self._heartbeat_loop())
        try:
            while not self.stopping.is_set():
                try:
                    prompt_id = await self.queue.pop_blocking(timeout=5)
                    if prompt_id is None:
                        continue
                    if not await self.provider.healthy():
                        await self._restart_provider()
                    await self._process(prompt_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("worker loop error: %s", exc)
                    await asyncio.sleep(3)
        finally:
            self.stopping.set()
            heartbeat.cancel()
            await self.provider.stop()
            await close_redis()
            logger.info("worker stopped")

    def request_stop(self) -> None:
        self.stopping.set()


def main() -> None:
    worker = Worker()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:
            pass  # Windows
    try:
        loop.run_until_complete(worker.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
