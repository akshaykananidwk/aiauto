"""Builds the text that is actually typed into the AI chat.

Staff write prompts in their own words (often Gujarati or Hindi) and just
tick "Generate image". The AI produces far more reliable results when the
request ends with an explicit, well-formed English image instruction — so
the platform appends one automatically at send time.

The user's own prompt is never modified in the database or in the UI: the
instruction is added only to the copy that goes to the AI, and it is
shown to staff as a preview before they submit.
"""
from __future__ import annotations

DEFAULT_IMAGE_INSTRUCTION = (
    "Create a single, high-quality image of the description above. "
    "The description may be in Gujarati or Hindi — understand it and "
    "generate the image accordingly. Generate the image directly in this "
    "reply: do not ask any follow-up questions and do not answer with "
    "text only."
)

SEPARATOR = "\n\n---\n"

# added when the job carries uploaded images: the AI should treat them as
# a visual reference ("make one like this") rather than as a document
REFERENCE_IMAGE_INSTRUCTION = (
    "Use the attached image(s) as the visual reference for style, "
    "composition and subject."
)

# sent as its own job when a user asks for their prompt to be improved
IMPROVE_IMAGE_PROMPT = (
    "Rewrite the request below into ONE clear, detailed English prompt for "
    "an AI image generator. Keep the original meaning and every specific "
    "detail; add helpful specifics about subject, setting, composition, "
    "lighting, colours and style. Do not invent facts that change the "
    "meaning. Reply with the improved prompt ONLY — no quotes, no "
    "explanation, no options, no preamble.\n\nRequest:\n"
)

IMPROVE_TEXT_PROMPT = (
    "Rewrite the request below into ONE clear, well-structured English "
    "prompt for an AI assistant. Keep the original meaning and every "
    "specific detail; make the task, the expected output and any format "
    "requirements explicit. Reply with the improved prompt ONLY — no "
    "quotes, no explanation, no preamble.\n\nRequest:\n"
)


def build_image_prompt(
    prompt_text: str,
    instruction: str | None = None,
    *,
    image_size: str | None = None,
    has_reference_images: bool = False,
) -> str:
    """Return the prompt to send for an image job.

    Appends the English image instruction (plus the size and reference
    sentences when they apply) unless it is already present — a retried
    job must not accumulate duplicate instructions.
    """
    from app.services.image_presets import size_instruction

    text = (prompt_text or "").strip()
    base = (instruction if instruction is not None else DEFAULT_IMAGE_INSTRUCTION).strip()

    parts = [base] if base else []
    if has_reference_images:
        parts.append(REFERENCE_IMAGE_INSTRUCTION)
    size_sentence = size_instruction(image_size)
    if size_sentence:
        parts.append(size_sentence)
    suffix = " ".join(parts).strip()

    if not suffix:
        return text
    if suffix.lower() in text.lower():
        return text  # already present (e.g. a retried job or a manual paste)
    if not text:
        return suffix
    return f"{text}{SEPARATOR}{suffix}"


def build_improve_prompt(prompt_text: str, wants_image: bool) -> str:
    """The helper job that turns a rough request into a better prompt."""
    head = IMPROVE_IMAGE_PROMPT if wants_image else IMPROVE_TEXT_PROMPT
    return head + (prompt_text or "").strip()


def clean_improved_text(raw: str) -> str:
    """Strip the wrapping the AI sometimes adds around its answer."""
    text = (raw or "").strip()
    for prefix in ("improved prompt:", "here is the improved prompt:",
                   "here's the improved prompt:", "prompt:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
    if len(text) >= 2 and text[0] in "\"“'" and text[-1] in "\"”'":
        text = text[1:-1].strip()
    return text
