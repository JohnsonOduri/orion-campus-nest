"""Logout / me.

Google is the only sign-in method (src/routes/login.tsx, backend/app/api/
oauth.py's POST /auth/oauth/google/set-session) — password signup/login
were removed. Session tokens never reach the browser as JS-readable values
for longer than the OAuth handshake itself (D7, narrowed — see
oauth.py/CLAUDE.md §13) — set as httpOnly cookies by set-session, read back
on every subsequent request here.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..core.cookies import clear_session_cookies, read_access_token
from ..services.gotrue_http import auth_headers, get_client
from ..services.supabase_clients import get_request_scoped_client, rpc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/logout")
def logout(request: Request, response: Response):
    token = read_access_token(request)
    if token:
        try:
            get_client().post(
                "/auth/v1/logout",
                headers={**auth_headers(), "Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError:
            pass  # best-effort server-side revoke; clearing cookies is what matters client-side
    clear_session_cookies(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    client = get_request_scoped_client(token)
    profile = rpc(client, "get_my_profile")
    if isinstance(profile, dict) and profile.get("error"):
        raise HTTPException(status_code=401, detail=profile["error"])
    return profile
