"""Signup / login / logout / me.

Proxies Supabase Auth's REST endpoints directly (httpx) rather than the
supabase-py SDK for the auth calls themselves — mirrors the exact pattern
already used in scripts/create_test_students.py and
scripts/verify_query_router.py. Session tokens never reach the browser as
JS-readable values (D7) — set as httpOnly cookies here, read back on every
subsequent request.

Uses the shared, connection-pooled client from gotrue_http.py instead of
opening a fresh httpx.Client (and redoing the TLS handshake to Supabase) on
every single call.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..core.cookies import clear_session_cookies, read_access_token, set_session_cookies
from ..core.redirects import resolve_post_auth_redirect
from ..schemas import LoginRequest, SignupRequest
from ..services.gotrue_http import auth_headers, get_client
from ..services.supabase_clients import get_request_scoped_client, rpc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
def signup(body: SignupRequest, response: Response):
    payload: dict = {"email": body.email, "password": body.password}
    if body.full_name:
        payload["data"] = {"full_name": body.full_name}

    res = get_client().post("/auth/v1/signup", headers=auth_headers(), json=payload)

    if res.status_code >= 400:
        detail = res.json().get("msg") or res.json().get("error_description") or "Signup failed"
        raise HTTPException(status_code=res.status_code, detail=detail)

    data = res.json()
    session = data.get("session")  # None if email confirmation is required
    if session:
        set_session_cookies(response, session["access_token"], session["refresh_token"])
        client = get_request_scoped_client(session["access_token"])
        profile = rpc(client, "get_my_profile")
        return {"ok": True, "redirect_to": resolve_post_auth_redirect(profile)}

    return {"ok": True, "redirect_to": "/login", "message": "Check your email to confirm your account."}


@router.post("/login")
def login(body: LoginRequest, response: Response):
    res = get_client().post(
        "/auth/v1/token?grant_type=password",
        headers=auth_headers(),
        json={"email": body.email, "password": body.password},
    )

    if res.status_code >= 400:
        detail = res.json().get("error_description") or res.json().get("msg") or "Invalid credentials"
        raise HTTPException(status_code=401, detail=detail)

    session = res.json()
    set_session_cookies(response, session["access_token"], session["refresh_token"])

    client = get_request_scoped_client(session["access_token"])
    profile = rpc(client, "get_my_profile")
    return {"ok": True, "redirect_to": resolve_post_auth_redirect(profile)}


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
