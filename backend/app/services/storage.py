"""Secure file storage: uploads, results, thumbnails."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("storage")

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip", ".csv": "text/csv", ".txt": "text/plain",
    ".json": "application/json", ".md": "text/markdown",
}


def safe_filename(name: str) -> str:
    name = Path(name).name  # strip any directory components
    name = SAFE_NAME_RE.sub("_", name).strip("._") or "file"
    return name[:200]


def guess_mime(filename: str) -> str:
    return MIME_BY_EXT.get(Path(filename).suffix.lower(), "application/octet-stream")


def is_image(filename: str) -> bool:
    return guess_mime(filename).startswith("image/")


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.settings.ensure_dirs()

    @property
    def root(self) -> Path:
        return self.settings.storage_path

    def abs_path(self, rel_path: str) -> Path:
        """Resolve a stored relative path, refusing traversal outside storage."""
        p = (self.root / rel_path).resolve()
        if not p.is_relative_to(self.root.resolve()):
            raise ValueError("path traversal detected")
        return p

    def _dest_dir(self, kind_dir: str, prompt_id: str) -> Path:
        d = self.root / kind_dir / prompt_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_bytes(self, kind_dir: str, prompt_id: str, filename: str, data: bytes) -> tuple[str, int]:
        """Save bytes; returns (rel_path, size)."""
        filename = safe_filename(filename)
        dest = self._dest_dir(kind_dir, prompt_id) / f"{uuid.uuid4().hex[:8]}_{filename}"
        dest.write_bytes(data)
        return str(dest.relative_to(self.root)), len(data)

    def make_thumbnail(self, rel_path: str, max_size: int = 320) -> str | None:
        """Create a JPEG/PNG thumbnail next to the image; returns rel path or None."""
        try:
            from PIL import Image

            src = self.abs_path(rel_path)
            thumb_path = src.with_name(f"thumb_{src.stem}.png")
            with Image.open(src) as im:
                im.thumbnail((max_size, max_size))
                im.save(thumb_path, "PNG")
            return str(thumb_path.relative_to(self.root))
        except Exception as exc:  # thumbnail failure must never fail the job
            logger.warning("thumbnail failed for %s: %s", rel_path, exc)
            return None

    def used_bytes(self) -> int:
        total = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def check_storage_limit(self) -> None:
        limit = self.settings.storage_limit_gb * 1024**3
        if self.used_bytes() >= limit:
            raise RuntimeError("storage limit reached — ask the administrator to free space")

    def delete_prompt_files(self, prompt_id: str) -> None:
        for kind_dir in ("uploads", "results"):
            d = self.root / kind_dir / prompt_id
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
