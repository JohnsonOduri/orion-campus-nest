"""Reusable FastAPI dependencies: resolve the caller's client + profile, and
proactively check role before touching Supabase (design decision D8) — the
underlying RLS/is_admin() checks are the REAL boundary, this is just a
clean, fast 401/403 instead of a confusing empty result or a generic RLS
error surfacing all the way up.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from supabase import Client

from ..core.cookies import read_access_token
from ..services.supabase_clients import get_request_scoped_client, rpc


def get_current_client(request: Request) -> Client:
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return get_request_scoped_client(token)


def get_current_profile(request: Request) -> tuple[Client, dict[str, Any]]:
    client = get_current_client(request)
    profile = rpc(client, "get_my_profile")
    if isinstance(profile, dict) and profile.get("error"):
        raise HTTPException(status_code=401, detail=profile["error"])
    return client, profile


def require_role(request: Request, allowed_roles: set[str]) -> tuple[Client, dict[str, Any]]:
    client, profile = get_current_profile(request)
    if profile.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient role for this action")
    return client, profile
