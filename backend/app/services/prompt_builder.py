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


def build_image_prompt(prompt_text: str, instruction: str | None = None) -> str:
    """Return the prompt to send for an image job.

    Appends the English image instruction unless the staff member already
    wrote one themselves (detected by the instruction's opening words) —
    duplicating it would only confuse the model.
    """
    text = (prompt_text or "").strip()
    suffix = (instruction if instruction is not None else DEFAULT_IMAGE_INSTRUCTION).strip()
    if not suffix:
        return text
    if suffix.lower() in text.lower():
        return text  # already present (e.g. a retried job or a manual paste)
    if not text:
        return suffix
    return f"{text}{SEPARATOR}{suffix}"
