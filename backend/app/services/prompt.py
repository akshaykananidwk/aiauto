from __future__ import annotations

from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.file import FileKind, PromptFile
from app.models.prompt import Prompt, PromptStatus
from app.models.user import User
from app.repositories.prompt import PromptRepository
from app.schemas.prompt import PromptCreate
from app.services import events
from app.services.audit import audit
from app.services.queue import QueueService
from app.services.quota import QuotaService
from app.services.storage import StorageService, guess_mime, safe_filename


class _StoredUpload:
    """Adapter that lets an already-stored file go through submit()'s
    normal upload path (same size checks, same ordering guarantees)."""

    def __init__(self, filename: str, content: bytes, content_type: str):
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._done = False

    async def read(self, _size: int = -1) -> bytes:
        if self._done:
            return b""
        self._done = True
        return self._content


class PromptService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PromptRepository(db)
        self.queue = QueueService()
        self.storage = StorageService()
        self.settings = get_settings()

    async def submit(
        self, user: User, data: PromptCreate, uploads: list[UploadFile]
    ) -> Prompt:
        from app.services.app_settings import AppSettingsService

        admin_settings = await AppSettingsService(self.db).effective()
        if await self.queue.size() >= admin_settings.max_queue_size:
            raise ValueError("queue is full — try again in a few minutes")
        await self.storage.check_storage_limit_async(admin_settings.storage_limit_gb)
        await QuotaService(self.db).check(user)  # raises QuotaExceededError

        from app.services.image_presets import DEFAULT_PRESET, is_valid

        if not is_valid(data.image_size):
            raise ValueError(f"unknown image size preset: {data.image_size}")

        prompt = Prompt(
            user_id=user.id,
            prompt_text=data.prompt_text,
            wants_image=data.wants_image,
            image_size=data.image_size or DEFAULT_PRESET,
            parent_id=data.parent_id,
            follow_up_to=data.follow_up_to,
            is_utility=data.is_utility,
            # staff cannot raise their own priority; admins can. Utility
            # jobs (prompt improvement) are short and interactive, so they
            # jump the queue instead of blocking a person for minutes.
            priority=(9 if data.is_utility
                      else data.priority if user.role.value == "admin" else 0),
            computer_name=data.computer_name,
            department=user.department,
        )
        self.repo.add(prompt)
        await self.db.flush()

        max_bytes = self.settings.max_upload_mb * 1024 * 1024
        for up in uploads:
            # stream in chunks so an oversized upload is rejected at the
            # cap instead of being read fully into memory first
            chunks: list[bytes] = []
            total = 0
            while chunk := await up.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(
                        f"file {up.filename} exceeds {self.settings.max_upload_mb} MB"
                    )
                chunks.append(chunk)
            content = b"".join(chunks)
            rel, size = self.storage.save_bytes(
                "uploads", prompt.id, up.filename or "upload.bin", content
            )
            self.db.add(
                PromptFile(
                    prompt_id=prompt.id,
                    kind=FileKind.upload,
                    filename=safe_filename(up.filename or "upload.bin"),
                    rel_path=rel,
                    mime_type=up.content_type or guess_mime(up.filename or ""),
                    size_bytes=size,
                )
            )

        await audit(
            self.db, "prompt.submitted", f"prompt {prompt.id} submitted",
            user_id=user.id, meta={"prompt_id": prompt.id, "wants_image": data.wants_image},
        )
        await self.db.commit()
        await self.db.refresh(prompt)

        position = await self.queue.enqueue(prompt.id, prompt.priority)
        await events.publish(
            events.PROMPT_SUBMITTED,
            {"prompt_id": prompt.id, "status": prompt.status.value, "position": position},
            user_id=user.id,
        )
        await events.publish(events.QUEUE_UPDATED, {"size": position}, admin_only=True)
        from app.services import webhooks

        await webhooks.dispatch(user.id, "job.submitted", {
            "job_id": prompt.id,
            "type": "image" if prompt.wants_image else "text",
            "queue_position": position,
        })
        return prompt

    async def regenerate(self, prompt: Prompt, by_user: User) -> Prompt:
        """Run the same request again as a NEW job, keeping the old result.

        Uploaded reference files are carried over — and they are attached
        through the normal submit path, so they are on disk BEFORE the job
        is queued (a worker must never start on a half-built job).
        """
        uploads: list[_StoredUpload] = []
        for f in prompt.files:
            if f.kind != FileKind.upload:
                continue
            try:
                content = self.storage.abs_path(f.rel_path).read_bytes()
            except OSError:
                continue  # the original upload is gone — skip it
            uploads.append(_StoredUpload(f.filename, content, f.mime_type))

        data = PromptCreate(
            prompt_text=prompt.prompt_text,
            wants_image=prompt.wants_image,
            image_size=prompt.image_size,
            computer_name=prompt.computer_name,
            parent_id=prompt.id,
        )
        return await self.submit(by_user, data, uploads)

    async def cancel(self, prompt: Prompt, by_user: User) -> Prompt:
        if prompt.status not in (PromptStatus.waiting, PromptStatus.processing):
            raise ValueError("only waiting or processing prompts can be cancelled")
        await self.queue.remove(prompt.id)
        prompt.status = PromptStatus.cancelled
        prompt.completed_at = datetime.now(timezone.utc)
        await audit(
            self.db, "prompt.cancelled", f"prompt {prompt.id} cancelled",
            user_id=by_user.id, meta={"prompt_id": prompt.id},
        )
        await self.db.commit()
        await events.publish(
            events.PROMPT_CANCELLED, {"prompt_id": prompt.id}, user_id=prompt.user_id
        )
        return prompt

    async def retry(self, prompt: Prompt, by_user: User) -> Prompt:
        if prompt.status not in (PromptStatus.failed, PromptStatus.cancelled):
            raise ValueError("only failed or cancelled prompts can be retried")
        prompt.status = PromptStatus.waiting
        prompt.error = None
        prompt.started_at = None
        prompt.completed_at = None
        await audit(
            self.db, "prompt.retried", f"prompt {prompt.id} re-queued",
            user_id=by_user.id, meta={"prompt_id": prompt.id},
        )
        await self.db.commit()
        # a leftover cancel flag from a mid-job cancellation would kill the
        # retried run the moment the worker picks it up
        await self.queue.clear_cancel_flag(prompt.id)
        position = await self.queue.enqueue(prompt.id, prompt.priority)
        await events.publish(
            events.PROMPT_SUBMITTED,
            {"prompt_id": prompt.id, "status": "waiting", "position": position},
            user_id=prompt.user_id,
        )
        return prompt
