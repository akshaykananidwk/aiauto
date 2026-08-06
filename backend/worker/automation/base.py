"""Provider interface: every AI backend returns the same result shape."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class AIResult:
    text: str = ""
    # local temp paths of downloaded artifacts (moved into storage by the worker)
    images: list[tuple[str, bytes]] = field(default_factory=list)  # (filename, data)
    files: list[tuple[str, bytes]] = field(default_factory=list)


class AIProvider(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def healthy(self) -> bool: ...
    async def run_prompt(
        self,
        prompt_text: str,
        upload_paths: list[Path],
        wants_image: bool,
        timeout_seconds: int,
    ) -> AIResult: ...


class LoginExpiredError(RuntimeError):
    """The ChatGPT session is no longer logged in — needs admin attention."""


class GenerationTimeoutError(RuntimeError):
    """The model did not finish within the configured timeout."""
