"""Result types and errors for the browser automation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIResult:
    text: str = ""
    # downloaded artifacts, moved into storage by the worker
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (filename, data)
    files: list[tuple[str, bytes]] = field(default_factory=list)
    # the chat this ran in — a follow-up can carry on in the same thread
    conversation_url: str = ""


class LoginExpiredError(RuntimeError):
    """The ChatGPT session is no longer logged in — needs admin attention."""


class GenerationTimeoutError(RuntimeError):
    """The generation did not finish within the configured timeout."""


class ImageDownloadError(RuntimeError):
    """An image was requested but could not be captured/downloaded —
    the job must NOT be marked completed."""
