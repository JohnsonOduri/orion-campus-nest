"""Supabase client construction — mirrors src/lib/supabase-server.ts exactly.

Two shapes only:
  - a request-scoped client (anon key + the caller's own JWT forwarded
    verbatim) for every user-facing route. RLS applies; auth.uid() resolves
    to the real caller. This is the only client any router in this service
    should use.
  - a service-role client, defined here for completeness/tests only — no
    router imports it. Never use it to serve a user request (bypasses RLS).

Never regress to trusting a client-supplied user id (CLAUDE.md §13).
"""

from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from ..core import config


def get_request_scoped_client(access_token: str) -> Client:
    client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client


def get_service_client() -> Client:
    """Trusted server-side only (scripts/tests). Never used by a route."""
    if not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SECRET_KEY/SUPABASE_SERVICE_ROLE_KEY not configured")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def rpc(client: Client, name: str, params: dict[str, Any] | None = None) -> Any:
    """Thin helper: call an RPC and raise on a Postgres-level error message
    embedded in the response, since Supabase's RPC error surface for
    plpgsql `raise exception` comes back as an HTTP error, not a jsonb
    payload — supabase-py already raises for that; this just gives routers
    one place to catch it."""
    return client.rpc(name, params or {}).execute().data
