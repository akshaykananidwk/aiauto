"""Central registry of ChatGPT UI selectors.

The ChatGPT web UI changes frequently. Every lookup tries a list of
selectors in order, so when OpenAI renames a data-testid the fix is a
one-line addition here — nothing else in the automation changes.
"""
from __future__ import annotations

PROMPT_INPUT = [
    "#prompt-textarea",
    "div[contenteditable='true'][data-testid*='prompt']",
    "div.ProseMirror[contenteditable='true']",
    "textarea[data-testid='prompt-textarea']",
    "textarea[placeholder*='Message']",
]

SEND_BUTTON = [
    "button[data-testid='send-button']",
    "button[data-testid='composer-send-button']",
    "#composer-submit-button",
    "button[aria-label*='Send']",
]

STOP_BUTTON = [
    "button[data-testid='stop-button']",
    "button[data-testid='composer-stop-button']",
    "button[aria-label*='Stop']",
]

ASSISTANT_MESSAGE = [
    "div[data-message-author-role='assistant']",
    "article[data-testid*='conversation-turn'] div[data-message-author-role='assistant']",
]

MESSAGE_IMAGE = [
    "img[alt='Generated image']",
    "img[alt*='Generated']",
    "img[src*='oaiusercontent']",
    "img[src*='files.oaiusercontent.com']",
    "img[src*='sdmntpr']",
    "img[src^='blob:']",
]

# UI markers shown WHILE an image is still being generated/rendered —
# completion must wait until none of these are visible
IMAGE_GENERATING = [
    "[data-testid*='image-gen']",
    "div:has-text('Creating image')",
    "div:has-text('Generating image')",
    "div:has-text('Getting started')",
    "progress",
    "[aria-label*='Creating']",
]

FILE_DOWNLOAD_LINK = [
    "a[href*='sandbox:']",
    "a[download]",
    "a[href*='oaiusercontent'][href*='download']",
]

FILE_UPLOAD_INPUT = [
    "input[type='file']",
]

ATTACH_BUTTON = [
    "button[data-testid='composer-plus-btn']",
    "button[aria-label*='Attach']",
    "button[aria-label*='Add photos']",
]

LOGIN_MARKERS = [
    "button[data-testid='login-button']",
    "a[href*='auth/login']",
    "button:has-text('Log in')",
]

NEW_CHAT = [
    "a[data-testid='create-new-chat-button']",
    "a[href='/']",
    "button[aria-label*='New chat']",
]

CONVERSATION_OPTIONS = [
    "button[data-testid='conversation-options-button']",
    "button[aria-label*='Open conversation options']",
]

DELETE_MENU_ITEM = [
    "div[role='menuitem']:has-text('Delete')",
    "[data-testid='delete-chat-menu-item']",
]

DELETE_CONFIRM = [
    "button[data-testid='delete-conversation-confirm-button']",
    "button:has-text('Delete')",
]
