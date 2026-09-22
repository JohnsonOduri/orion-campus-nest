"""Offline tests for backend/app/api/tts.py — the Kokoro proxy.

Calls the route functions directly (same style as tests/test_ai_router.py);
Supabase session verification and the Kokoro HTTP client are faked, so no
network is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api import tts  # noqa: E402
from app.core import config  # noqa: E402


def _request(token: str | None = "tok"):
    cookies = {"orion_access_token": token} if token else {}
    return SimpleNamespace(cookies=cookies)


class _FakeResponse:
    def __init__(self, status_code=200, content=b"ID3fake-mp3", content_type="audio/mpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type} if content_type else {}


class _FakeKokoro:
    def __init__(self, response=None, exc=None):
        self.response = response or _FakeResponse()
        self.exc = exc
        self.calls: list[dict] = []

    def post(self, path, json):
        self.calls.append({"path": path, "json": json})
        if self.exc:
            raise self.exc
        return self.response


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(tts, "_require_signed_in", lambda request: None)


@pytest.fixture
def kokoro_enabled(monkeypatch):
    monkeypatch.setattr(config, "TTS_PROVIDER", "kokoro")


def _use_kokoro(monkeypatch, fake):
    monkeypatch.setattr(tts, "_kokoro_client", lambda: fake)
    return fake


def test_config_never_exposes_the_kokoro_url(monkeypatch):
    monkeypatch.setattr(config, "KOKORO_BASE_URL", "http://10.0.0.5:8880")
    body = tts.tts_config()
    assert "10.0.0.5" not in repr(body)
    assert body["default_voice"] in {v["id"] for v in body["voices"]}
    assert body["provider"] in {"browser", "kokoro"}


def test_requires_a_session_cookie():
    with pytest.raises(HTTPException) as exc:
        tts._require_signed_in(_request(token=None))
    assert exc.value.status_code == 401


def test_rejects_a_token_supabase_does_not_recognise(monkeypatch):
    tts._verified_until.clear()
    fake_gotrue = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(status_code=401))
    monkeypatch.setattr(tts.gotrue_http, "get_client", lambda: fake_gotrue)
    with pytest.raises(HTTPException) as exc:
        tts._require_signed_in(_request("forged"))
    assert exc.value.status_code == 401


def test_verified_token_is_cached_briefly(monkeypatch):
    tts._verified_until.clear()
    calls = []

    def get(*a, **k):
        calls.append(1)
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(tts.gotrue_http, "get_client", lambda: SimpleNamespace(get=get))
    tts._require_signed_in(_request("good"))
    tts._require_signed_in(_request("good"))
    assert len(calls) == 1


def test_browser_mode_refuses_synthesis(monkeypatch, signed_in):
    monkeypatch.setattr(config, "TTS_PROVIDER", "browser")
    fake = _use_kokoro(monkeypatch, _FakeKokoro())
    with pytest.raises(HTTPException) as exc:
        tts.speech(tts.SpeechRequest(text="Hello."), _request())
    assert exc.value.status_code == 503
    assert fake.calls == []


def test_proxies_to_openai_compatible_endpoint(monkeypatch, signed_in, kokoro_enabled):
    fake = _use_kokoro(monkeypatch, _FakeKokoro())
    resp = tts.speech(tts.SpeechRequest(text="Your next class is at 10 AM.", voice="bf_emma", speed=0.9), _request())
    assert resp.media_type == "audio/mpeg"
    assert resp.body == b"ID3fake-mp3"
    sent = fake.calls[0]
    assert sent["path"] == "/v1/audio/speech"
    assert sent["json"]["input"] == "Your next class is at 10 AM."
    assert sent["json"]["voice"] == "bf_emma"
    assert sent["json"]["speed"] == 0.9
    assert sent["json"]["response_format"] == "mp3"


def test_defaults_come_from_config(monkeypatch, signed_in, kokoro_enabled):
    fake = _use_kokoro(monkeypatch, _FakeKokoro())
    tts.speech(tts.SpeechRequest(text="Hi."), _request())
    assert fake.calls[0]["json"]["voice"] == config.KOKORO_VOICE
    assert fake.calls[0]["json"]["speed"] == tts.DEFAULT_SPEED


def test_unknown_voice_is_rejected_before_calling_kokoro(monkeypatch, signed_in, kokoro_enabled):
    fake = _use_kokoro(monkeypatch, _FakeKokoro())
    with pytest.raises(HTTPException) as exc:
        tts.speech(tts.SpeechRequest(text="Hi.", voice="../../etc/passwd"), _request())
    assert exc.value.status_code == 400
    assert fake.calls == []


@pytest.mark.parametrize("speed", [0.1, 5.0])
def test_speed_out_of_range_is_rejected(speed):
    with pytest.raises(ValidationError):
        tts.SpeechRequest(text="Hi.", speed=speed)


def test_overlong_text_is_rejected():
    with pytest.raises(ValidationError):
        tts.SpeechRequest(text="a" * (tts.MAX_TEXT_CHARS + 1))


def test_kokoro_down_maps_to_503(monkeypatch, signed_in, kokoro_enabled):
    _use_kokoro(monkeypatch, _FakeKokoro(exc=httpx.ConnectError("refused")))
    with pytest.raises(HTTPException) as exc:
        tts.speech(tts.SpeechRequest(text="Hi."), _request())
    assert exc.value.status_code == 503


@pytest.mark.parametrize(
    "response",
    [_FakeResponse(status_code=500, content_type="application/json"), _FakeResponse(content_type="application/json")],
)
def test_kokoro_error_or_non_audio_maps_to_502(monkeypatch, signed_in, kokoro_enabled, response):
    _use_kokoro(monkeypatch, _FakeKokoro(response=response))
    with pytest.raises(HTTPException) as exc:
        tts.speech(tts.SpeechRequest(text="Hi."), _request())
    assert exc.value.status_code == 502


# --------------------------------------------------------------- rate limiting

def test_rate_limiter_blocks_after_the_limit_and_recovers(monkeypatch):
    from app.core import ratelimit

    clock = [1000.0]
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock[0])
    limiter = ratelimit.RateLimiter(limit=3, window_seconds=60)
    for _ in range(3):
        limiter.check("user-a")
    with pytest.raises(HTTPException) as exc:
        limiter.check("user-a")
    assert exc.value.status_code == 429 and "Retry-After" in exc.value.headers
    limiter.check("user-b")  # other users are unaffected
    clock[0] += 61
    limiter.check("user-a")  # window slid past


def test_ask_rejects_an_overlong_question():
    from app.schemas import AskRequest

    with pytest.raises(ValidationError):
        AskRequest(query="x" * 1001)
