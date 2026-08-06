# AIAuto Plugins

Drop Python files in this directory to extend the platform without
touching core code. Each plugin defines a `register(hooks)` function:

```python
# plugins/my_plugin.py
def register(hooks):
    hooks.on("prompt.completed", on_completed)   # sync or async handlers

async def on_completed(payload):
    data = payload["data"]
    print(f"prompt {data['prompt_id']} finished!")
```

Available events (same names as the WebSocket bus):

- `prompt.submitted`, `prompt.processing`, `prompt.generating_image`,
  `prompt.downloading`, `prompt.completed`, `prompt.failed`, `prompt.cancelled`
- `queue.updated`, `worker.status`, `update.progress`, `notification.new`
- `*` — receive every event

Notes:

- Handlers run inside the process that publishes the event (API server or
  worker) — keep them fast and never raise (exceptions are logged and
  swallowed).
- Plugins load at startup; restart the service after adding one.
- Files starting with `_` are ignored. This directory is preserved by the
  auto-updater when listed in the protected paths.
