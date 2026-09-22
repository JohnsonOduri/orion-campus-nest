"""Text-to-speech endpoints (docs/tts.md).

GET  /tts/config  — which provider the frontend should use, plus the voice
                    allowlist and defaults. No secrets in here: the Kokoro
                    server's URL is deliberately NOT part of the response.
POST /tts/speech  — proxies one chunk of already-sanitised text to a Kokoro
                    OpenAI-compatible server (`POST /v1/audio/speech`) and
                    returns MP3. Works with any server implementing that
                    contract (kokoro-open-tts, Kokoro-FastAPI, ...).

Why proxy instead of letting the browser call Kokoro directly: Kokoro
servers have no auth of their own, so exposing one publicly would hand free
compute to anyone. Here only a signed-in ORION user can synthesise, and the
Kokoro host can stay on a private network.

The request text is never logged — it's the user's answer content.
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..core import config
from ..core.cookies import read_access_token
from ..core.ratelimit import TTS_LIMITER
from ..services import gotrue_http

router = APIRouter(prefix="/tts", tags=["tts"])

# Deliberately a short, curated list rather than all 54 Kokoro voices — these
# are the English voices worth auditioning for an assistant. Labels describe
# the voice; they make no claim about which one is best.
VOICES: list[dict[str, str]] = [
    {"id": "af_heart", "name": "Heart", "accent": "American", "gender": "female"},
    {"id": "af_bella", "name": "Bella", "accent": "American", "gender": "female"},
    {"id": "af_nicole", "name": "Nicole", "accent": "American", "gender": "female"},
    {"id": "af_sarah", "name": "Sarah", "accent": "American", "gender": "female"},
    {"id": "af_sky", "name": "Sky", "accent": "American", "gender": "female"},
    {"id": "am_adam", "name": "Adam", "accent": "American", "gender": "male"},
    {"id": "am_michael", "name": "Michael", "accent": "American", "gender": "male"},
    {"id": "bm_george", "name": "George", "accent": "British", "gender": "male"},
    {"id": "bf_emma", "name": "Emma", "accent": "British", "gender": "female"},
]
VOICE_IDS = {v["id"] for v in VOICES}

MIN_SPEED = 0.7
MAX_SPEED = 1.3
# The frontend sends one sentence-group at a time (~300 chars); this bound
# just stops the endpoint being used to synthesise whole documents.
MAX_TEXT_CHARS = 600

if config.KOKORO_VOICE not in VOICE_IDS:
    raise RuntimeError(f"KOKORO_VOICE={config.KOKORO_VOICE!r} is not one of {sorted(VOICE_IDS)}")

DEFAULT_SPEED = min(MAX_SPEED, max(MIN_SPEED, config.KOKORO_SPEED))


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=MIN_SPEED, le=MAX_SPEED)


# --- caller verification -----------------------------------------------------
# A response is ~3-6 chunks, each a separate POST. Verifying the session with
# Supabase on every chunk would add a round trip per sentence, so a verified
# token is remembered for a short time (keyed by its hash, never stored raw).
_VERIFY_TTL_SECONDS = 60
_verified_until: dict[str, float] = {}
_verified_lock = threading.Lock()


def _require_signed_in(request: Request) -> None:
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _verified_lock:
        if _verified_until.get(key, 0) > now:
            return

    try:
        resp = gotrue_http.get_client().get(
            "/auth/v1/user",
            headers={**gotrue_http.auth_headers(), "Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not verify your session") from exc
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with _verified_lock:
        if len(_verified_until) > 1000:
            _verified_until.clear()
        _verified_until[key] = now + _VERIFY_TTL_SECONDS


# --- Kokoro client -------------------------------------------------------------
_kokoro: httpx.Client | None = None
_kokoro_lock = threading.Lock()


def _kokoro_client() -> httpx.Client:
    global _kokoro
    with _kokoro_lock:
        if _kokoro is None:
            _kokoro = httpx.Client(
                base_url=config.KOKORO_BASE_URL,
                # Connect fails fast so the browser falls back quickly when
                # Kokoro isn't running; synthesis of one chunk on CPU can take
                # a few seconds.
                timeout=httpx.Timeout(20.0, connect=2.0),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return _kokoro


def close_client() -> None:
    global _kokoro
    with _kokoro_lock:
        if _kokoro is not None:
            _kokoro.close()
            _kokoro = None


@router.get("/config")
def tts_config():
    return {
        "provider": config.TTS_PROVIDER,
        "default_voice": config.KOKORO_VOICE,
        "default_speed": DEFAULT_SPEED,
        "speed_range": [MIN_SPEED, MAX_SPEED],
        "voices": VOICES,
    }


@router.post("/speech")
def speech(body: SpeechRequest, request: Request):
    _require_signed_in(request)
    TTS_LIMITER.check_request(request)

    if config.TTS_PROVIDER != "kokoro":
        raise HTTPException(status_code=503, detail="Neural voice is not enabled on this server")

    voice = body.voice or config.KOKORO_VOICE
    if voice not in VOICE_IDS:
        raise HTTPException(status_code=400, detail="Unknown voice")
    speed = body.speed if body.speed is not None else DEFAULT_SPEED

    try:
        resp = _kokoro_client().post(
            "/v1/audio/speech",
            json={
                "model": "kokoro",
                "input": body.text,
                "voice": voice,
                "speed": speed,
                "response_format": "mp3",
            },
        )
    except httpx.HTTPError as exc:
        print(f"[tts.speech] Kokoro unreachable ({exc.__class__.__name__})", file=sys.stderr)
        raise HTTPException(status_code=503, detail="Voice service unavailable") from exc

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not content_type.startswith("audio/"):
        print(f"[tts.speech] Kokoro returned {resp.status_code} ({content_type or 'no content-type'})", file=sys.stderr)
        raise HTTPException(status_code=502, detail="Voice service returned an error")

    return Response(content=resp.content, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
