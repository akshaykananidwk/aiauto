"""Minimal plugin system.

Drop a ``*.py`` file into the ``plugins/`` directory at the repo root.
Each plugin module must define::

    def register(hooks):
        hooks.on("prompt.completed", my_handler)   # sync or async

Handlers receive the event payload dict. Events mirror the realtime bus:
prompt.submitted / prompt.completed / prompt.failed / update.progress /
notification.new / worker.status … Handlers run in the process that
publishes the event (API server or worker) and must never block for long.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from app.core.config import ROOT_DIR
from app.core.logging import get_logger

logger = get_logger("plugins")


class HookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable]] = defaultdict(list)
        self.loaded: list[str] = []

    def on(self, event: str, handler: Callable) -> None:
        self._hooks[event].append(handler)

    async def dispatch(self, event: str, payload: dict) -> None:
        for handler in self._hooks.get(event, []) + self._hooks.get("*", []):
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("plugin handler for %s failed: %s", event, exc)


hooks = HookRegistry()
_loaded = False


def load_plugins() -> HookRegistry:
    global _loaded
    if _loaded:
        return hooks
    _loaded = True
    plugin_dir = ROOT_DIR / "plugins"
    if not plugin_dir.is_dir():
        return hooks
    for path in sorted(plugin_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"aiauto_plugin_{path.stem}", path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            if hasattr(module, "register"):
                module.register(hooks)
                hooks.loaded.append(path.stem)
                logger.info("loaded plugin: %s", path.stem)
        except Exception as exc:
            logger.error("failed to load plugin %s: %s", path.name, exc)
    return hooks
