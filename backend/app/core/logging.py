"""Central logging configuration: console + rotating file handler."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from app.core.config import ROOT_DIR, get_settings

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    # one log file PER PROCESS: on Windows two processes sharing a rotating
    # file deadlock on rollover (the other process holds the file open)
    logname = "worker.log" if "worker" in (sys.argv[0] or "") else "aiauto.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / logname, maxBytes=10 * 1024 * 1024, backupCount=10, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
