"""Official OpenAI API provider — a drop-in alternative to browser
automation (AI_PROVIDER=api). More reliable and ToS-clean; use it when
API billing is acceptable."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from worker.automation.base import AIResult

logger = get_logger("worker.openai_api")


class OpenAIAPIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.openai_api_key:
            raise RuntimeError("AI_PROVIDER=api requires OPENAI_API_KEY")

    async def start(self) -> None:  # nothing to start
        pass

    async def stop(self) -> None:
        pass

    async def healthy(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _client(self, timeout: int) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            timeout=timeout,
        )

    async def run_prompt(
        self,
        prompt_text: str,
        upload_paths: list[Path],
        wants_image: bool,
        timeout_seconds: int,
    ) -> AIResult:
        result = AIResult(model=self.settings.openai_image_model if wants_image
                          else self.settings.openai_text_model)
        async with self._client(timeout_seconds) as client:
            if wants_image:
                r = await client.post(
                    "/images/generations",
                    json={"model": self.settings.openai_image_model,
                          "prompt": prompt_text, "n": 1},
                )
                r.raise_for_status()
                for i, item in enumerate(r.json().get("data", []), start=1):
                    if item.get("b64_json"):
                        result.images.append(
                            (f"image_{i}.png", base64.b64decode(item["b64_json"]))
                        )
                    elif item.get("url"):
                        img = await client.get(item["url"])
                        if img.status_code == 200:
                            result.images.append((f"image_{i}.png", img.content))
                result.text = "Image generated."
            else:
                content: list[dict] = [{"type": "text", "text": prompt_text}]
                for p in upload_paths:
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                        b64 = base64.b64encode(p.read_bytes()).decode()
                        content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        })
                r = await client.post(
                    "/chat/completions",
                    json={"model": self.settings.openai_text_model,
                          "messages": [{"role": "user", "content": content}]},
                )
                r.raise_for_status()
                data = r.json()
                result.text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                result.input_tokens = int(usage.get("prompt_tokens", 0))
                result.output_tokens = int(usage.get("completion_tokens", 0))
        return result
