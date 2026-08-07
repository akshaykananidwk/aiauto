"""Text-to-speech for answers: listen to a result, or download it as audio.

Two engines, chosen by the administrator:

  * "offline" (default) — the computer's own voices (Windows SAPI5 via
    pyttsx3). Nothing leaves the network; quality depends on which voices
    Windows has installed. Produces WAV.
  * "online" — Google's public translate TTS (gTTS). Much better for
    Gujarati/Hindi and produces MP3, but the ANSWER TEXT IS SENT to
    Google, so it is opt-in and never the default.

Both are optional at runtime: if the engine's package is missing the API
says exactly what to install instead of failing obscurely.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("tts")

MAX_CHARS = 8000  # a very long answer would take minutes to synthesise


class TTSUnavailable(RuntimeError):
    """The selected engine is not installed/usable — message explains how
    to enable it."""


def clean_for_speech(text: str) -> str:
    """Strip markdown decoration so the voice doesn't read '###' aloud."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)      # code blocks
    text = re.sub(r"`([^`]*)`", r"\1", text)                       # inline code
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)              # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)           # links
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)      # headings
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)      # bold/italic
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)           # bullets
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.M)        # table rows
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CHARS]


def _audio_dir() -> Path:
    d = get_settings().storage_path / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_path(prompt_id: str, text: str, engine: str, language: str) -> Path:
    """Cache per (answer, engine, language) so re-downloads are instant and
    an edited/regenerated answer produces a new file."""
    digest = hashlib.sha256(
        f"{engine}|{language}|{text}".encode("utf-8")).hexdigest()[:16]
    ext = "mp3" if engine == "online" else "wav"
    return _audio_dir() / f"{prompt_id}_{digest}.{ext}"


def _synthesize_offline(text: str, out: Path) -> None:
    try:
        import pyttsx3
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise TTSUnavailable(
            "the offline voice engine is not installed — run "
            "`backend\\.venv\\Scripts\\pip install pyttsx3` on the server, "
            "or switch the audio engine to 'online' in Admin → Settings"
        ) from exc
    try:
        engine = pyttsx3.init()
        engine.save_to_file(text, str(out))
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - machine specific
        raise TTSUnavailable(
            f"the computer's voice engine could not produce audio ({exc}). "
            "On Windows check Settings → Time & Language → Speech for an "
            "installed voice, or switch to the 'online' engine."
        ) from exc
    if not out.exists() or out.stat().st_size < 1000:
        raise TTSUnavailable(
            "the computer's voice engine produced an empty file — install a "
            "speech voice in Windows, or switch to the 'online' engine")


def _synthesize_online(text: str, language: str, out: Path) -> None:
    try:
        from gtts import gTTS
    except Exception as exc:  # pragma: no cover - depends on the machine
        raise TTSUnavailable(
            "the online voice engine is not installed — run "
            "`backend\\.venv\\Scripts\\pip install gTTS` on the server"
        ) from exc
    try:
        gTTS(text=text, lang=(language or "en")).save(str(out))
    except Exception as exc:
        raise TTSUnavailable(
            f"the online voice service could not be reached ({exc}) — check "
            "the server's internet connection, or use the 'offline' engine"
        ) from exc
    if not out.exists() or out.stat().st_size < 500:
        raise TTSUnavailable("the online voice service returned an empty file")


async def synthesize(
    prompt_id: str, text: str, *, engine: str, language: str
) -> tuple[Path, str]:
    """Return (file path, mime type), generating and caching on first use.

    Runs the blocking engine off the event loop so a long answer never
    stalls the API.
    """
    spoken = clean_for_speech(text)
    if not spoken:
        raise TTSUnavailable("there is no text in this answer to read aloud")
    if engine not in ("offline", "online"):
        raise TTSUnavailable(
            "audio is switched off — an administrator can enable it in "
            "Admin → Settings")

    out = cache_path(prompt_id, spoken, engine, language)
    if out.exists() and out.stat().st_size > 500:
        return out, ("audio/mpeg" if out.suffix == ".mp3" else "audio/wav")

    if engine == "online":
        await asyncio.to_thread(_synthesize_online, spoken, language, out)
        return out, "audio/mpeg"
    await asyncio.to_thread(_synthesize_offline, spoken, out)
    return out, "audio/wav"
