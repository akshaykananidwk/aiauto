"""v1.6.0: follow-up conversations, answer audio, onboarding flag."""
import pytest

from app.services.prompt_builder import build_follow_up_prompt
from app.services.tts import TTSUnavailable, cache_path, clean_for_speech, synthesize
from tests.conftest import auth_headers


async def completed_prompt(client, db, headers, text="explain solar panels",
                           answer="Solar panels convert light into electricity.",
                           conversation_url=None):
    from sqlalchemy import select

    from app.models.prompt import Prompt, PromptStatus

    created = (await client.post("/api/v1/prompts", headers=headers,
                                 data={"prompt_text": text})).json()
    row = (await db.execute(
        select(Prompt).where(Prompt.id == created["id"]))).scalar_one()
    row.status = PromptStatus.completed
    row.response_text = answer
    row.conversation_url = conversation_url
    await db.commit()
    return created["id"]


# ---- 68. follow-up -------------------------------------------------------

async def test_follow_up_creates_a_linked_job(client, db):
    headers = await auth_headers(client, "alice")
    first = await completed_prompt(client, db, headers)

    res = await client.post(f"/api/v1/prompts/{first}/follow-up", headers=headers,
                            json={"prompt_text": "make it shorter"})
    assert res.status_code == 201
    child = res.json()
    assert child["follow_up_to"] == first
    assert child["prompt_text"] == "make it shorter"
    assert child["status"] == "waiting"


async def test_follow_up_can_request_an_image(client, db):
    headers = await auth_headers(client, "alice")
    first = await completed_prompt(client, db, headers)
    child = (await client.post(
        f"/api/v1/prompts/{first}/follow-up", headers=headers,
        json={"prompt_text": "draw that", "wants_image": True,
              "image_size": "square"})).json()
    assert child["wants_image"] is True and child["image_size"] == "square"


async def test_follow_up_needs_a_finished_job(client):
    headers = await auth_headers(client, "alice")
    waiting = (await client.post("/api/v1/prompts", headers=headers,
                                 data={"prompt_text": "still running"})).json()
    res = await client.post(f"/api/v1/prompts/{waiting['id']}/follow-up",
                            headers=headers, json={"prompt_text": "more"})
    assert res.status_code == 400


async def test_follow_up_is_owner_only(client, db):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    mine = await completed_prompt(client, db, alice)
    res = await client.post(f"/api/v1/prompts/{mine}/follow-up", headers=bob,
                            json={"prompt_text": "sneaky"})
    assert res.status_code == 404


async def test_thread_lists_follow_ups_in_order(client, db):
    headers = await auth_headers(client, "alice")
    root = await completed_prompt(client, db, headers)
    for question in ("shorter please", "now in Gujarati"):
        await client.post(f"/api/v1/prompts/{root}/follow-up", headers=headers,
                          json={"prompt_text": question})
    thread = (await client.get(f"/api/v1/prompts/{root}/thread", headers=headers)).json()
    assert [t["prompt_text"] for t in thread] == ["shorter please", "now in Gujarati"]


def test_context_fallback_carries_the_previous_exchange():
    """When the original chat is gone, the AI still gets the context."""
    built = build_follow_up_prompt("make it shorter", "explain solar panels",
                                   "Solar panels convert light into electricity.")
    assert "explain solar panels" in built
    assert "convert light into electricity" in built
    assert built.rstrip().endswith("make it shorter")


def test_context_fallback_handles_an_image_only_answer():
    built = build_follow_up_prompt("same but at sunset", "draw a house", "")
    assert "(an image was generated)" in built
    assert "draw a house" in built


# ---- 66. answer audio ----------------------------------------------------

@pytest.mark.parametrize("raw,expected_absent", [
    ("## Heading\ntext", "##"),
    ("**bold** words", "**"),
    ("- bullet one", "- "),
    ("`code`", "`"),
    ("[link](https://example.com)", "https://"),
    ("```\nprint(1)\n```", "print(1)"),
])
def test_markdown_is_stripped_before_speaking(raw, expected_absent):
    assert expected_absent not in clean_for_speech(raw)


def test_speech_text_keeps_the_actual_words():
    spoken = clean_for_speech("## Report\n\n**Solar** panels are `great`.")
    assert "Report" in spoken and "Solar" in spoken and "great" in spoken


def test_audio_cache_path_varies_with_engine_and_language():
    a = cache_path("p1", "hello", "offline", "en")
    b = cache_path("p1", "hello", "online", "en")
    c = cache_path("p1", "hello", "online", "gu")
    d = cache_path("p1", "different answer", "online", "gu")
    assert len({a, b, c, d}) == 4          # no cache collisions
    assert a.suffix == ".wav" and b.suffix == ".mp3"


async def test_audio_refuses_when_the_engine_is_off():
    with pytest.raises(TTSUnavailable, match="switched off"):
        await synthesize("p1", "some answer", engine="off", language="en")


async def test_audio_refuses_empty_text():
    with pytest.raises(TTSUnavailable, match="no text"):
        await synthesize("p1", "   ", engine="offline", language="en")


async def test_audio_endpoint_needs_an_answer(client):
    headers = await auth_headers(client, "alice")
    waiting = (await client.post("/api/v1/prompts", headers=headers,
                                 data={"prompt_text": "no answer yet"})).json()
    res = await client.get(f"/api/v1/prompts/{waiting['id']}/audio", headers=headers)
    assert res.status_code == 400


async def test_audio_endpoint_reports_a_missing_engine_clearly(client, db, monkeypatch):
    """A missing voice engine must explain how to fix it, not 500."""
    import app.services.tts as tts

    headers = await auth_headers(client, "alice")
    prompt_id = await completed_prompt(client, db, headers)

    def explode(*_args, **_kwargs):
        raise TTSUnavailable("the offline voice engine is not installed — run pip install pyttsx3")

    monkeypatch.setattr(tts, "_synthesize_offline", explode)
    res = await client.get(f"/api/v1/prompts/{prompt_id}/audio", headers=headers)
    assert res.status_code == 503
    assert "pyttsx3" in res.json()["detail"]


async def test_audio_endpoint_serves_and_caches_the_file(client, db, monkeypatch):
    import app.services.tts as tts

    headers = await auth_headers(client, "alice")
    prompt_id = await completed_prompt(client, db, headers)
    calls = []

    def fake_engine(text, out):
        calls.append(text)
        out.write_bytes(b"RIFF" + b"\0" * 2000)   # a plausible WAV

    monkeypatch.setattr(tts, "_synthesize_offline", fake_engine)

    first = await client.get(f"/api/v1/prompts/{prompt_id}/audio", headers=headers)
    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert len(first.content) > 1000

    second = await client.get(f"/api/v1/prompts/{prompt_id}/audio", headers=headers)
    assert second.status_code == 200
    assert len(calls) == 1          # served from cache the second time


async def test_audio_is_owner_only(client, db):
    alice = await auth_headers(client, "alice")
    bob = await auth_headers(client, "bob")
    prompt_id = await completed_prompt(client, db, alice)
    assert (await client.get(f"/api/v1/prompts/{prompt_id}/audio",
                             headers=bob)).status_code == 404


# ---- 94. onboarding ------------------------------------------------------

async def test_new_user_starts_not_onboarded_and_can_finish(client):
    headers = await auth_headers(client, "alice")
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["onboarded"] is False

    done = await client.post("/api/v1/auth/onboarded", headers=headers,
                             json={"done": True})
    assert done.status_code == 200 and done.json()["onboarded"] is True

    again = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert again["onboarded"] is True        # survives a reload/other computer


async def test_tour_can_be_replayed(client):
    headers = await auth_headers(client, "bob")
    await client.post("/api/v1/auth/onboarded", headers=headers, json={"done": True})
    res = await client.post("/api/v1/auth/onboarded", headers=headers,
                            json={"done": False})
    assert res.json()["onboarded"] is False


async def test_onboarding_requires_login(client):
    assert (await client.post("/api/v1/auth/onboarded",
                              json={"done": True})).status_code == 401
