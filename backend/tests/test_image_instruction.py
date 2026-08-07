"""Automatic English image instruction appended to 'Generate image' prompts."""
from app.services.prompt_builder import (
    DEFAULT_IMAGE_INSTRUCTION,
    build_image_prompt,
)
from tests.conftest import auth_headers


def test_instruction_is_appended_after_the_users_text():
    out = build_image_prompt("દ્વારકાધીશનો ફોટો બનાવો")
    assert out.startswith("દ્વારકાધીશનો ફોટો બનાવો")
    assert out.endswith(DEFAULT_IMAGE_INSTRUCTION)


def test_user_text_is_never_modified():
    text = "A minimalist mountain logo"
    assert build_image_prompt(text).split("\n\n---\n")[0] == text


def test_not_duplicated_when_already_present():
    once = build_image_prompt("logo please")
    assert build_image_prompt(once) == once  # a retried job stays clean


def test_custom_instruction_from_admin_settings():
    out = build_image_prompt("a cat", "Draw it now.")
    assert out.endswith("Draw it now.")
    assert DEFAULT_IMAGE_INSTRUCTION not in out


def test_empty_instruction_disables_the_feature():
    assert build_image_prompt("a cat", "") == "a cat"


def test_empty_prompt_falls_back_to_the_instruction_alone():
    assert build_image_prompt("  ") == DEFAULT_IMAGE_INSTRUCTION


async def test_staff_can_read_the_instruction(client):
    headers = await auth_headers(client, "alice")
    res = await client.get("/api/v1/prompts/image-instruction", headers=headers)
    assert res.status_code == 200
    assert res.json()["instruction"] == DEFAULT_IMAGE_INSTRUCTION


async def test_admin_can_change_it_and_staff_sees_the_new_text(client):
    admin = await auth_headers(client, "admin")
    res = await client.put("/api/v1/admin/settings", headers=admin,
                           json={"image_prompt_instruction": "Render one photo."})
    assert res.status_code == 200
    assert res.json()["image_prompt_instruction"] == "Render one photo."

    staff = await auth_headers(client, "alice")
    res = await client.get("/api/v1/prompts/image-instruction", headers=staff)
    assert res.json()["instruction"] == "Render one photo."
