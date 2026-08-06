"""Notification center + external channels (email / Telegram / webhook).

In-app notifications are stored in the DB and pushed live over the
WebSocket event bus. External channels are best-effort and never fail
the calling operation. Works from both the API server and the worker.
"""
from __future__ import annotations

import asyncio
import smtplib
from email.mime.text import MIMEText

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services import events

logger = get_logger("notify")

NOTIFICATION_EVENT = "notification.new"


def _send_email_sync(to_addr: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not to_addr:
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_addr
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def _send_telegram(chat_id: str, text: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not chat_id:
        return
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )


async def _send_webhook(payload: dict) -> None:
    """Generic outbound webhook — point it at Slack, a WhatsApp gateway
    (e.g. Twilio), or any internal system."""
    settings = get_settings()
    url = settings.notify_webhook_url
    if not url or not url.lower().startswith(("http://", "https://")):
        return
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(url, json=payload)


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(
        self,
        user: User,
        type_: str,
        title: str,
        body: str = "",
        meta: dict | None = None,
        *,
        external: bool = True,
        commit: bool = False,
    ) -> Notification:
        """Store an in-app notification, push it over WS, and fan out to
        the user's external channels."""
        notif = Notification(user_id=user.id, type=type_, title=title, body=body, meta=meta)
        self.db.add(notif)
        if commit:
            await self.db.commit()
        try:
            await events.publish(
                NOTIFICATION_EVENT,
                {"type": type_, "title": title, "body": body, "meta": meta or {}},
                user_id=user.id,
            )
        except Exception:
            pass
        if external:
            await dispatch_external(user, title, body, meta)
        return notif

    async def notify_admins(
        self, type_: str, title: str, body: str = "", meta: dict | None = None
    ) -> None:
        res = await self.db.execute(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True))
        )
        for admin in res.scalars().all():
            await self.notify(admin, type_, title, body, meta)

    async def unread_count(self, user_id: int) -> int:
        stmt = select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        return (await self.db.execute(stmt)).scalar_one()


async def dispatch_external(user: User, title: str, body: str, meta: dict | None) -> None:
    """Fire-and-forget external delivery; never raises."""
    text = f"[AIAuto] {title}" + (f"\n{body}" if body else "")

    async def _run() -> None:
        try:
            if user.email:
                await asyncio.to_thread(_send_email_sync, user.email, f"[AIAuto] {title}", body or title)
        except Exception as exc:
            logger.warning("email notification failed: %s", exc)
        try:
            if user.telegram_chat_id:
                await _send_telegram(user.telegram_chat_id, text)
        except Exception as exc:
            logger.warning("telegram notification failed: %s", exc)
        try:
            await _send_webhook({"user": user.username, "title": title, "body": body,
                                 "meta": meta or {}})
        except Exception as exc:
            logger.warning("webhook notification failed: %s", exc)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        await _run()
