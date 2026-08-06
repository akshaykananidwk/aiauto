"""Anthropic Claude API provider (AI_PROVIDER=anthropic)."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.core.config import get_settings
from worker.automation.base import AIResult

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.anthropic_api_key:
            raise RuntimeError("anthropic provider requires ANTHROPIC_API_KEY")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def healthy(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    async def run_prompt(
        self,
        prompt_text: str,
        upload_paths: list[Path],
        wants_image: bool,
        timeout_seconds: int,
    ) -> AIResult:
        content: list[dict] = []
        for p in upload_paths:
            suffix = p.suffix.lower()
            if suffix in IMAGE_SUFFIXES:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": MEDIA_TYPES[suffix],
                        "data": base64.b64encode(p.read_bytes()).decode(),
                    },
                })
            elif suffix == ".pdf":
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(p.read_bytes()).decode(),
                    },
                })
        if wants_image:
            prompt_text += ("\n\n(Note: this provider cannot generate images; "
                            "describe the image in detail instead.)")
        content.append({"type": "text", "text": prompt_text})

        model = self.settings.anthropic_model
        async with httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            timeout=timeout_seconds,
        ) as client:
            r = await client.post("/v1/messages", json={
                "model": model,
                "max_tokens": 8192,
                "messages": [{"role": "user", "content": content}],
            })
            r.raise_for_status()
            data = r.json()

        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
        usage = data.get("usage", {})
        return AIResult(
            text=text,
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )
