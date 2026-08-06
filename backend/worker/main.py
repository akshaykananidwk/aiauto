"""AIAuto worker — runs on the master computer.

Consumes the Redis queue and processes every prompt through the ONE AI
backend this platform uses: the master computer's logged-in ChatGPT Pro
browser session (Playwright). Stores results and files and publishes
realtime status events. Run with:

    python -m worker.main

Correctness notes:
  * Terminal status writes use a guarded UPDATE (`WHERE status =
    'processing'`) so a cancellation committed by the API mid-job is
    never clobbered by the worker's completion/failure commit.
  * Realtime publishes happen only AFTER the durable commit and are
    best-effort — a Redis hiccup must never re-run a completed job.
"""
from __future__ import annotations

import asyncio
import os
import signal
import socket
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import update as sql_update

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import async_session_factory, init_db
from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.schemas.settings import AdminSettings
from app.services import events
from app.services.audit import audit
from app.services.notify import NotificationService
from app.services.queue import QueueService
from app.services.redis_client import close_redis
from worker.automation.base import (
    AIResult,
    GenerationTimeoutError,
    ImageDownloadError,
    LoginExpiredError,
)
from worker.automation.chatgpt import ChatGPTProvider

logger = get_logger("worker")


class Worker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.worker_id = (
            self.settings.worker_id
            or f"{socket.gethostname()}-{os.getpid()}"
        )
        self.queue = QueueService()
        self.provider = ChatGPTProvider()
        self.stopping = asyncio.Event()
        self.current_job: str | None = None

    # ---------- status ----------

    async def _heartbeat_loop(self) -> None:
        while not self.stopping.is_set():
            try:
                healthy = await self.provider.healthy()
                await self.queue.register_heartbeat(
                    self.worker_id,
                    chrome="connected" if healthy else "disconnected",
                    current_job=self.current_job,
                )
            except Exception as exc:
                logger.warning("heartbeat failed: %s", exc)
            await asyncio.sleep(5)

    # ---------- helpers ----------

    async def _admin_settings(self, db) -> AdminSettings:
        """Runtime settings from the admin panel (DB) merged over env."""
        try:
            from app.services.app_settings import AppSettingsService

            return await AppSettingsService(db).effective()
        except Exception:
            return AdminSettings(
                job_retry_count=self.settings.job_retry_count,
                job_timeout_seconds=self.settings.job_timeout_seconds,
                response_timeout_seconds=self.settings.response_timeout_seconds,
                delete_conversations_after_run=self.settings.delete_conversations_after_run,
            )

    async def _claim_terminal(self, db, prompt_id: str, values: dict) -> bool:
        """Atomically move a prompt out of `processing`. Returns False when
        someone else (a cancellation) changed the status first."""
        result = await db.execute(
            sql_update(Prompt)
            .where(Prompt.id == prompt_id, Prompt.status == PromptStatus.processing)
            .values(**values)
        )
        return result.rowcount == 1

    async def _publish_safe(self, event_type: str, data: dict, user_id: int | None) -> None:
        try:
            await events.publish(event_type, data, user_id=user_id)
        except Exception as exc:
            logger.warning("event publish failed (non-fatal): %s", exc)

    def _save_result_files(self, db, prompt: Prompt, result: AIResult) -> None:
        """Persist result artifacts. Every file is verified on disk before
        its DB row is added — a prompt is never 'completed' pointing at a
        file that does not actually exist."""
        from app.services.storage import StorageService, guess_mime, is_image

        storage = StorageService()

        def _save_verified(filename: str, data: bytes) -> tuple[str, int]:
            rel, size = storage.save_bytes("results", prompt.id, filename, data)
            written = storage.abs_path(rel)
            if not written.exists() or written.stat().st_size != len(data):
                raise ImageDownloadError(
                    f"result file {filename} failed disk verification after write")
            return rel, size

        for filename, data in result.images:
            rel, size = _save_verified(filename, data)
            thumb = storage.make_thumbnail(rel)  # thumbnail failure is non-fatal
            db.add(PromptFile(
                prompt_id=prompt.id, kind=FileKind.result_image, filename=filename,
                rel_path=rel, thumb_rel_path=thumb, mime_type=guess_mime(filename),
                size_bytes=size,
            ))
        for filename, data in result.files:
            rel, size = _save_verified(filename, data)
            kind = FileKind.result_image if is_image(filename) else FileKind.result_file
            thumb = storage.make_thumbnail(rel) if kind == FileKind.result_image else None
            db.add(PromptFile(
                prompt_id=prompt.id, kind=kind, filename=filename, rel_path=rel,
                thumb_rel_path=thumb, mime_type=guess_mime(filename), size_bytes=size,
            ))

    async def _restart_provider(self) -> None:
        try:
            await self.provider.stop()
        except Exception:
            pass
        try:
            await self.provider.start()
        except Exception as exc:
            logger.error("provider restart failed: %s", exc)

    # ---------- job processing ----------

    async def _process(self, prompt_id: str) -> None:
        self.current_job = prompt_id
        try:
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

                admin = await self._admin_settings(db)
                self.provider.delete_conversations = admin.delete_conversations_after_run

                # guarded waiting→processing transition: an API-side
                # cancellation committed in this window must win
                started = await db.execute(
                    sql_update(Prompt)
                    .where(Prompt.id == prompt_id, Prompt.status == PromptStatus.waiting)
                    .values(status=PromptStatus.processing,
                            started_at=datetime.now(timezone.utc))
                )
                if started.rowcount != 1:
                    await db.rollback()
                    await self.queue.clear_cancel_flag(prompt_id)
                    logger.info("prompt %s no longer waiting — skipping", prompt_id)
                    return
                await audit(db, "prompt.started", f"prompt {prompt.id} started",
                            user_id=prompt.user_id, meta={"prompt_id": prompt.id,
                                                          "worker": self.worker_id})
                await db.commit()
                await db.refresh(prompt)
                await self._publish_safe(events.PROMPT_PROCESSING,
                                         {"prompt_id": prompt.id}, prompt.user_id)
                if prompt.wants_image:
                    await self._publish_safe(events.PROMPT_GENERATING_IMAGE,
                                             {"prompt_id": prompt.id}, prompt.user_id)

                from app.services.storage import StorageService

                storage = StorageService()
                upload_paths: list[Path] = [
                    storage.abs_path(f.rel_path)
                    for f in prompt.files
                    if f.kind == FileKind.upload and storage.abs_path(f.rel_path).exists()
                ]

                try:
                    await self.provider.start()
                    result = await asyncio.wait_for(
                        self.provider.run_prompt(
                            prompt.prompt_text,
                            upload_paths,
                            prompt.wants_image,
                            admin.response_timeout_seconds,
                        ),
                        timeout=admin.job_timeout_seconds,
                    )
                    # belt-and-braces: an image prompt must never complete
                    # without at least one captured image
                    if prompt.wants_image and not result.images:
                        raise ImageDownloadError(
                            "an image was requested but the reply contained no "
                            "downloadable image")
                except Exception as exc:
                    await self._handle_failure(db, prompt, exc, admin)
                    return

                await self._publish_safe(events.PROMPT_DOWNLOADING,
                                         {"prompt_id": prompt.id}, prompt.user_id)

                claimed = await self._claim_terminal(db, prompt.id, {
                    "status": PromptStatus.completed,
                    "response_text": result.text,
                    "completed_at": datetime.now(timezone.utc),
                })
                if not claimed:
                    # the API cancelled this prompt mid-run — honour it.
                    # NB: snapshot ids BEFORE rollback (rollback expires ORM
                    # instances; expired access raises under asyncio)
                    prompt_id_, user_id_ = prompt.id, prompt.user_id
                    await db.rollback()
                    await self.queue.clear_cancel_flag(prompt_id_)
                    await audit(db, "prompt.cancel_honoured",
                                f"prompt {prompt_id_} was cancelled mid-run; result discarded",
                                user_id=user_id_, level="warning",
                                meta={"prompt_id": prompt_id_}, commit=True)
                    return

                try:
                    self._save_result_files(db, prompt, result)
                    await audit(db, "prompt.completed",
                                f"prompt {prompt.id} completed "
                                f"({len(result.images)} images, {len(result.files)} files)",
                                user_id=prompt.user_id, meta={"prompt_id": prompt.id})
                    if prompt.user:
                        await NotificationService(db).notify(
                            prompt.user, "success", "Prompt completed",
                            f"Your prompt \"{prompt.prompt_text[:80]}\" finished"
                            + (f" with {len(result.images)} image(s)" if result.images else ""),
                            meta={"prompt_id": prompt.id},
                        )
                    await db.commit()
                except Exception as exc:
                    # storage/DB failure while persisting results: undo the
                    # completion claim and route through retry/failure —
                    # never leave the job wedged in `processing`
                    await db.rollback()
                    await self._handle_failure(db, prompt, exc, admin)
                    return
                # post-commit: purely informational, must never fail the job
                await self._publish_safe(
                    events.PROMPT_COMPLETED,
                    {"prompt_id": prompt.id,
                     "images": len(result.images), "files": len(result.files)},
                    prompt.user_id,
                )
        finally:
            self.current_job = None

    async def _handle_failure(
        self, db, prompt: Prompt, exc: Exception, admin: AdminSettings
    ) -> None:
        retryable = not isinstance(exc, LoginExpiredError)
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("prompt %s failed: %s", prompt.id, error_msg)

        if isinstance(exc, (GenerationTimeoutError, asyncio.TimeoutError)):
            error_msg = "The AI did not finish in time. The job can be retried."
        if isinstance(exc, LoginExpiredError):
            await self._publish_safe(
                events.WORKER_STATUS,
                {"error": "login_expired", "message": str(exc)}, None)

        # snapshot BEFORE rollback — rollback expires ORM instances and
        # expired attribute access raises MissingGreenlet under asyncio
        prompt_id_ = prompt.id
        user_id_ = prompt.user_id
        retry_count = prompt.retry_count
        priority = prompt.priority
        text_snippet = prompt.prompt_text[:80]

        await db.rollback()  # discard any partial state from the failed run

        # reset the browser between failures — cheap insurance against a
        # wedged page/session
        await self._restart_provider()

        if retryable and retry_count < admin.job_retry_count:
            claimed = await self._claim_terminal(db, prompt_id_, {
                "status": PromptStatus.waiting,
                "retry_count": retry_count + 1,
                "error": error_msg,
            })
            if not claimed:  # cancelled mid-run — do not resurrect it
                await db.rollback()
                await self.queue.clear_cancel_flag(prompt_id_)
                return
            await audit(db, "prompt.retry",
                        f"prompt {prompt_id_} auto-retry {retry_count + 1}",
                        user_id=user_id_, level="warning",
                        meta={"prompt_id": prompt_id_, "error": error_msg})
            await db.commit()
            await self.queue.clear_cancel_flag(prompt_id_)
            await self.queue.enqueue(prompt_id_, priority)
            return

        claimed = await self._claim_terminal(db, prompt_id_, {
            "status": PromptStatus.failed,
            "error": error_msg,
            "completed_at": datetime.now(timezone.utc),
        })
        if not claimed:  # already cancelled — nothing more to record
            await db.rollback()
            await self.queue.clear_cancel_flag(prompt_id_)
            return
        await audit(db, "prompt.failed", f"prompt {prompt_id_} failed: {error_msg}",
                    user_id=user_id_, level="error",
                    meta={"prompt_id": prompt_id_})
        from app.models.user import User

        user = await db.get(User, user_id_)  # fresh, non-expired instance
        if user is not None:
            await NotificationService(db).notify(
                user, "error", "Prompt failed",
                f"Your prompt \"{text_snippet}\" failed: {error_msg[:200]}",
                meta={"prompt_id": prompt_id_},
            )
        await db.commit()
        await self._publish_safe(events.PROMPT_FAILED,
                                 {"prompt_id": prompt_id_, "error": error_msg},
                                 user_id_)

    # ---------- main loop ----------

    async def run(self) -> None:
        setup_logging()
        await init_db()
        logger.info("worker %s starting (ChatGPT browser automation)", self.worker_id)
        try:
            await self.provider.start()
        except Exception as exc:
            logger.error("browser start failed (will keep retrying): %s", exc)

        heartbeat = asyncio.create_task(self._heartbeat_loop())
        try:
            while not self.stopping.is_set():
                try:
                    prompt_id = await self.queue.pop_blocking(timeout=5)
                    if prompt_id is None:
                        continue
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
