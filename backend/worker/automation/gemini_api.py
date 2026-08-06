"""Google Gemini API provider (AI_PROVIDER=gemini)."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.core.config import get_settings
from worker.automation.base import AIResult

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf"}


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.gemini_api_key:
            raise RuntimeError("gemini provider requires GEMINI_API_KEY")

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def healthy(self) -> bool:
        return bool(self.settings.gemini_api_key)

    async def run_prompt(
        self,
        prompt_text: str,
        upload_paths: list[Path],
        wants_image: bool,
        timeout_seconds: int,
    ) -> AIResult:
        parts: list[dict] = []
        for p in upload_paths:
            media = MEDIA_TYPES.get(p.suffix.lower())
            if media:
                parts.append({"inline_data": {
                    "mime_type": media,
                    "data": base64.b64encode(p.read_bytes()).decode(),
                }})
        if wants_image:
            prompt_text += ("\n\n(Note: this provider is configured for text; "
                            "describe the requested image in detail instead.)")
        parts.append({"text": prompt_text})

        model = self.settings.gemini_model
        async with httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com",
            timeout=timeout_seconds,
        ) as client:
            r = await client.post(
                f"/v1beta/models/{model}:generateContent",
                params={"key": self.settings.gemini_api_key},
                json={"contents": [{"parts": parts}]},
            )
            r.raise_for_status()
            data = r.json()

        candidates = data.get("candidates", [])
        text = ""
        if candidates:
            text = "".join(p.get("text", "")
                           for p in candidates[0].get("content", {}).get("parts", []))
        usage = data.get("usageMetadata", {})
        return AIResult(
            text=text,
            model=model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
        )
