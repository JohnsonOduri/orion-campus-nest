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

from ..core.cookies import (
    clear_session_cookies,
    read_access_token,
    read_refresh_token,
    set_session_cookies,
)
from ..services.gotrue_http import auth_headers, get_client
from ..services.supabase_clients import get_request_scoped_client, rpc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh")
def refresh(request: Request, response: Response):
    """Trade the refresh-token cookie for a fresh access token.

    Supabase access tokens last an hour, and until this existed nothing ever
    read `orion_refresh_token` back — so an hour into a session every request
    started failing with PostgREST's "JWT expired" and the only way out was to
    sign in again. The browser can't do this itself: the cookies are httpOnly
    and `auth.callback.tsx` deliberately drops the client-side Supabase
    session right after the handshake (CLAUDE.md §13), so the refresh token
    only exists here.

    Supabase rotates refresh tokens, so the new pair must both be written
    back; a client that fires two refreshes concurrently would spend the
    rotated token on one of them and get logged out, which is why
    src/lib/api-client.ts funnels all callers through a single in-flight
    refresh.
    """
    token = read_refresh_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        res = get_client().post(
            "/auth/v1/token?grant_type=refresh_token",
            headers=auth_headers(),
            json={"refresh_token": token},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach the auth service") from exc

    if res.status_code >= 400:
        # The refresh token is spent, revoked or expired — this session is
        # genuinely over, so clear the cookies rather than leaving the browser
        # to retry a pair that will never work again.
        clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired")

    session = res.json()
    access_token, refresh_token = session.get("access_token"), session.get("refresh_token")
    if not access_token or not refresh_token:
        clear_session_cookies(response)
        raise HTTPException(status_code=401, detail="Session expired")

    set_session_cookies(response, access_token, refresh_token)
    return {"ok": True}


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
