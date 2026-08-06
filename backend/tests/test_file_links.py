"""Signed one-file download links (native browser/mobile saving)."""
from app.core.security import create_file_token
from tests.conftest import auth_headers


async def make_prompt_with_upload(client, headers):
    res = await client.post(
        "/api/v1/prompts", headers=headers,
        data={"prompt_text": "file link test", "wants_image": "false"},
        files={"files": ("note.txt", b"hello file link", "text/plain")},
    )
    assert res.status_code == 201, res.text
    prompt = res.json()
    return next(f for f in prompt["files"] if f["kind"] == "upload")


async def test_signed_link_allows_headerless_download(client):
    headers = await auth_headers(client, "alice")
    file = await make_prompt_with_upload(client, headers)

    link = await client.get(f"/api/v1/files/{file['id']}/link", headers=headers)
    assert link.status_code == 200
    url = link.json()["url"]
    assert "st=" in url

    # NO Authorization header — the signed link alone authorizes it
    res = await client.get(url)
    assert res.status_code == 200
    assert res.content == b"hello file link"


async def test_token_bound_to_single_file(client):
    headers = await auth_headers(client, "alice")
    file_a = await make_prompt_with_upload(client, headers)
    file_b = await make_prompt_with_upload(client, headers)

    token_for_a = create_file_token(file_a["id"])
    res = await client.get(f"/api/v1/files/{file_b['id']}/download?st={token_for_a}")
    assert res.status_code == 403  # a link never opens a different file

    res = await client.get(f"/api/v1/files/{file_a['id']}/download?st=garbage")
    assert res.status_code == 401


async def test_link_requires_ownership(client):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    file = await make_prompt_with_upload(client, alice)
    res = await client.get(f"/api/v1/files/{file['id']}/link", headers=bob)
    assert res.status_code == 404  # bob cannot mint links for alice's files


async def test_download_still_works_with_jwt(client):
    headers = await auth_headers(client, "alice")
    file = await make_prompt_with_upload(client, headers)
    res = await client.get(f"/api/v1/files/{file['id']}/download", headers=headers)
    assert res.status_code == 200
    assert res.content == b"hello file link"


async def test_inline_vs_attachment_disposition(client):
    """`url` must force a download; `view_url` must display inline so the
    browser's native Save/Copy image gestures work."""
    headers = await auth_headers(client, "alice")
    file = await make_prompt_with_upload(client, headers)
    link = (await client.get(f"/api/v1/files/{file['id']}/link", headers=headers)).json()
    assert "inline=1" in link["view_url"]

    download = await client.get(link["url"])
    assert download.headers["content-disposition"].startswith("attachment")

    view = await client.get(link["view_url"])
    assert view.status_code == 200
    assert view.headers["content-disposition"].startswith("inline")
    assert view.content == b"hello file link"
