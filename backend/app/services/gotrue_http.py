"""Shared httpx client for direct calls to Supabase's /auth/v1/* REST API.

A fresh httpx.Client() per request re-does the TLS handshake to Supabase on
every single call — auth.py and oauth.py each create one with `with
httpx.Client(...) as http:` per handler. Reusing one pooled, keep-alive
client across requests avoids that handshake cost on every login/signup/
token exchange. Opened once at app startup and closed at shutdown (see
main.py's lifespan), not a bare module-level singleton, so connections are
released cleanly on shutdown instead of leaking.
"""

from __future__ import annotations

import httpx

from ..core import config

_client: httpx.Client | None = None


def open_client() -> None:
    global _client
    _client = httpx.Client(
        base_url=config.SUPABASE_URL,
        timeout=15,
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    )


def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_client() -> httpx.Client:
    if _client is None:
        raise RuntimeError("gotrue_http client not initialized — is the app lifespan running?")
    return _client


def auth_headers() -> dict[str, str]:
    return {"apikey": config.SUPABASE_ANON_KEY, "Content-Type": "application/json"}
