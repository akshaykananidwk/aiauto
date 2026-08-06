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

        # HTTP 200 does not mean success — safety blocks and abnormal stops
        # must raise so the failover chain can try the next provider
        feedback = data.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise RuntimeError(f"gemini blocked the prompt: {feedback['blockReason']}")
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("gemini returned no candidates")
        candidate = candidates[0]
        finish = candidate.get("finishReason", "STOP")
        text = "".join(p.get("text", "")
                       for p in candidate.get("content", {}).get("parts", []))
        if finish not in ("STOP", "MAX_TOKENS"):
            raise RuntimeError(f"gemini generation stopped abnormally: {finish}")
        if not text.strip():
            raise RuntimeError(f"gemini returned an empty response (finishReason={finish})")
        if finish == "MAX_TOKENS":
            text += "\n\n[Response truncated: model output limit reached]"
        usage = data.get("usageMetadata", {})
        return AIResult(
            text=text,
            model=model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
        )
