"""Environment configuration for the ORION auth/CR-workflow API.

Loads the repo-root .env (same file src/lib/supabase-server.ts and every
scripts/*.py script already read) — one source of truth for credentials
across the JS and Python sides of this project. Never uses the service-role
key for a request-scoped operation; it's exposed here only for the rare
trusted server-side case (none in the current routers — see D6 in
docs/decisions/orion-auth-plan.md).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")


def _first(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


SUPABASE_URL: str = _first("SUPABASE_URL", "VITE_SUPABASE_URL", "PUBLIC_SUPABASE_URL") or ""
SUPABASE_ANON_KEY: str = (
    _first(
        "SUPABASE_ANON_KEY",
        "SUPABASE_PUBLIC_ANON_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "VITE_SUPABASE_ANON_KEY",
        "PUBLIC_SUPABASE_ANON_KEY",
    )
    or ""
)
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = _first("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")

GOOGLE_CLIENT_ID: Optional[str] = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: Optional[str] = os.environ.get("GOOGLE_CLIENT_SECRET")

# Where THIS API is reachable (used to build the OAuth redirect_to URL) and
# where the frontend lives (used for CORS + post-auth redirects).
API_BASE_URL: str = os.environ.get("API_BASE_URL", "http://localhost:8000")
FRONTEND_ORIGIN: str = os.environ.get("FRONTEND_ORIGIN", "http://localhost:8080")

# Cookie security — allow disabling `secure` for plain-http local dev; real
# deployments must run behind https and leave this true.
COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "false").lower() == "true"

# SameSite for the session cookies (core/cookies.py). Default "lax" is
# unchanged from the original design and is correct whenever the frontend
# and this API share one registrable domain. Set to "none" ONLY when they
# are genuinely on different sites (e.g. a Vercel frontend calling a Render
# API) — that combination requires COOKIE_SECURE=true (browsers reject
# SameSite=None without Secure) and only stays safe if CORS keeps rejecting
# every origin except FRONTEND_ORIGIN, since SameSite=None alone provides no
# CSRF protection on its own; the strict single-origin CORS in main.py is
# what's actually standing in for it. This is a deliberate deployment
# decision, not a default — see docs/backend-requirements.md §7. Never pair
# "none" with a wildcard CORS origin.
_COOKIE_SAMESITE_VALUES = {"lax", "strict", "none"}
COOKIE_SAMESITE: str = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in _COOKIE_SAMESITE_VALUES:
    raise RuntimeError(
        f"COOKIE_SAMESITE={COOKIE_SAMESITE!r} is not valid — must be one of {sorted(_COOKIE_SAMESITE_VALUES)}"
    )
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true (browsers reject SameSite=None without Secure)")


# --- Text-to-speech (docs/tts.md) -------------------------------------------
# "browser": the frontend speaks with the device's own SpeechSynthesis — zero
# infrastructure, the current prototype default. "kokoro": the frontend asks
# THIS service for audio (POST /tts/speech), which proxies to a Kokoro
# OpenAI-compatible server at KOKORO_BASE_URL. The Kokoro URL never reaches
# the browser. Browser TTS stays the fallback either way.
_TTS_PROVIDERS = {"browser", "kokoro"}
TTS_PROVIDER: str = os.environ.get("TTS_PROVIDER", "browser").strip().lower()
if TTS_PROVIDER not in _TTS_PROVIDERS:
    raise RuntimeError(f"TTS_PROVIDER={TTS_PROVIDER!r} is not valid — must be one of {sorted(_TTS_PROVIDERS)}")

# Default is :8880, not Kokoro's own default :8000 — that is this API's port.
KOKORO_BASE_URL: str = os.environ.get("KOKORO_BASE_URL", "http://localhost:8880").rstrip("/")
KOKORO_VOICE: str = os.environ.get("KOKORO_VOICE", "af_heart").strip()
try:
    KOKORO_SPEED: float = float(os.environ.get("KOKORO_SPEED", "1.0"))
except ValueError as exc:
    raise RuntimeError("KOKORO_SPEED must be a number, e.g. 1.0") from exc


def require_configured() -> None:
    """Fail fast and loudly at startup rather than on the first request."""
    missing = [
        name
        for name, value in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY))
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Check .env at the repo root."
        )
