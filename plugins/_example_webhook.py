"""Example plugin (disabled — rename without the leading underscore to enable).

Posts a message to an internal endpoint whenever a prompt fails.
"""
import httpx


def register(hooks):
    hooks.on("prompt.failed", on_failed)


async def on_failed(payload):
    data = payload.get("data", {})
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post("http://intranet.local/alerts", json={
            "text": f"AIAuto prompt {data.get('prompt_id')} failed: {data.get('error')}",
        })
