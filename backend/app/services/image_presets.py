"""Output size presets for generated images.

Generic, purpose-neutral formats that suit any kind of work: posts,
stories, video thumbnails, presentations, banners and print. The chosen
aspect ratio is requested from the AI in the prompt, and the captured
image is fitted to the exact pixel size afterwards so what staff pick is
what they get.
"""
from __future__ import annotations

# key -> label / pixels / aspect. "auto" means "whatever the AI produces".
IMAGE_PRESETS: dict[str, dict] = {
    "auto": {"label": "Auto (let the AI decide)", "width": 0, "height": 0, "aspect": ""},
    "square": {"label": "Square 1:1 — 1024×1024", "width": 1024, "height": 1024,
               "aspect": "1:1 square"},
    "portrait": {"label": "Portrait 4:5 — 1080×1350", "width": 1080, "height": 1350,
                 "aspect": "4:5 portrait"},
    "vertical": {"label": "Vertical / Story 9:16 — 1080×1920", "width": 1080,
                 "height": 1920, "aspect": "9:16 vertical"},
    "landscape": {"label": "Landscape 16:9 — 1920×1080", "width": 1920, "height": 1080,
                  "aspect": "16:9 landscape"},
    "thumbnail": {"label": "Thumbnail 16:9 — 1280×720", "width": 1280, "height": 720,
                  "aspect": "16:9 landscape"},
    "wide": {"label": "Wide banner 3:1 — 1500×500", "width": 1500, "height": 500,
             "aspect": "3:1 wide banner"},
    "a4_portrait": {"label": "A4 print (portrait) — 2480×3508", "width": 2480,
                    "height": 3508, "aspect": "A4 portrait (1:1.414)"},
    "a4_landscape": {"label": "A4 print (landscape) — 3508×2480", "width": 3508,
                     "height": 2480, "aspect": "A4 landscape (1.414:1)"},
}

DEFAULT_PRESET = "auto"


def is_valid(key: str | None) -> bool:
    return (key or DEFAULT_PRESET) in IMAGE_PRESETS


def get_preset(key: str | None) -> dict:
    return IMAGE_PRESETS.get(key or DEFAULT_PRESET, IMAGE_PRESETS[DEFAULT_PRESET])


def presets_list() -> list[dict]:
    return [{"key": k, **v} for k, v in IMAGE_PRESETS.items()]


def size_instruction(key: str | None) -> str:
    """Sentence appended to the prompt so the AI aims for the right shape."""
    preset = get_preset(key)
    if not preset["aspect"]:
        return ""
    return (f"Compose the image in {preset['aspect']} format "
            f"(about {preset['width']}x{preset['height']} pixels).")


def fit_to_preset(data: bytes, key: str | None) -> bytes:
    """Scale + centre-crop the captured image to the preset's exact size.

    The AI usually returns a close-but-not-exact ratio, so the crop is
    normally a few pixels. Returns the original bytes unchanged for the
    "auto" preset, when it already matches, or if anything goes wrong —
    a resize must never cost the user their image.
    """
    preset = get_preset(key)
    target_w, target_h = preset["width"], preset["height"]
    if not target_w or not target_h:
        return data
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.width == target_w and im.height == target_h:
                return data
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            # cover fit: scale so both sides reach the target, crop the rest
            scale = max(target_w / im.width, target_h / im.height)
            new_w, new_h = max(1, round(im.width * scale)), max(1, round(im.height * scale))
            resized = im.resize((new_w, new_h), Image.LANCZOS)
            left, top = (new_w - target_w) // 2, (new_h - target_h) // 2
            cropped = resized.crop((left, top, left + target_w, top + target_h))
            out = io.BytesIO()
            cropped.save(out, "PNG")
            return out.getvalue()
    except Exception:
        return data  # never lose the image over a formatting step
