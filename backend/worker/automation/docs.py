"""Document text extraction (PDF reader / OCR / Document AI helper).

API providers that can't ingest arbitrary files get the extracted text
appended to the prompt instead. All extractors are optional and degrade
gracefully when their library is missing.
"""
from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger

logger = get_logger("worker.docs")

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
MAX_CHARS = 30000


def extract_text(path: Path) -> str:
    """Best-effort text extraction; empty string when unsupported."""
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES:
            return path.read_text(encoding="utf-8", errors="replace")[:MAX_CHARS]
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            return _ocr_image(path)
    except Exception as exc:
        logger.warning("text extraction failed for %s: %s", path.name, exc)
    return ""


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.info("pypdf not installed — skipping PDF extraction")
        return ""
    reader = PdfReader(str(path))
    chunks = []
    total = 0
    for page in reader.pages[:50]:
        text = page.extract_text() or ""
        chunks.append(text)
        total += len(text)
        if total > MAX_CHARS:
            break
    return "\n".join(chunks)[:MAX_CHARS]


def _ocr_image(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""  # OCR is optional (requires pytesseract + tesseract binary)
    with Image.open(path) as im:
        return pytesseract.image_to_string(im)[:MAX_CHARS]


def build_context_block(paths: list[Path]) -> str:
    """Combine extracted document texts into a prompt context block."""
    parts = []
    for path in paths:
        text = extract_text(path)
        if text.strip():
            parts.append(f"--- Content of attached file '{path.name}' ---\n{text.strip()}")
    return ("\n\n".join(parts) + "\n\n") if parts else ""
