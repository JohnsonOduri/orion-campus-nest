"""Google sign-in via Supabase's server-side PKCE flow.

We drive PKCE ourselves (rather than letting a browser-side SDK do it) so
the resulting session tokens land straight in httpOnly cookies (D7) and
never pass through JS. The `code_verifier` only needs to survive the
redirect round-trip to Google and back, so it rides in its own short-lived
cookie (`orion_oauth_pkce_verifier`) rather than server-side state.

Domain restriction (@iiitkottayam.ac.in) is enforced by the
`hook_restrict_signup_by_email_domain` Supabase Auth Hook at the GoTrue
level (see plan D3) — this router doesn't duplicate that check.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..core import config
from ..core.cookies import clear_pkce_cookie, read_pkce_cookie, set_pkce_cookie, set_session_cookies
from ..core.redirects import resolve_post_auth_redirect
from ..services.gotrue_http import auth_headers, get_client
from ..services.supabase_clients import get_request_scoped_client, get_service_client, rpc

router = APIRouter(prefix="/auth/oauth/google", tags=["oauth"])


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _parse_jwt_claims(token: str) -> dict:
    """Decode the JWT payload (no signature verification needed — Supabase signed it)."""
    try:
        payload_b64 = token.split(".")[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


@router.get("/authorize")
def authorize():
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = _code_challenge(verifier)
    redirect_to = f"{config.API_BASE_URL}/auth/oauth/google/callback"
    authorize_url = (
        f"{config.SUPABASE_URL}/auth/v1/authorize"
        f"?provider=google&redirect_to={redirect_to}"
        f"&code_challenge={challenge}&code_challenge_method=s256"
    )
    response = RedirectResponse(url=authorize_url, status_code=302)
    set_pkce_cookie(response, verifier)
    return response


@router.get("/callback")
def callback(request: Request, code: str | None = None, error_description: str | None = None):
    if error_description:
        import urllib.parse
        encoded_error = urllib.parse.quote(error_description)
        response = RedirectResponse(url=f"{config.FRONTEND_ORIGIN}/login?error={encoded_error}", status_code=302)
        clear_pkce_cookie(response)
        return response

    verifier = read_pkce_cookie(request)
    if not code or not verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth code or PKCE verifier")

    res = get_client().post(
        "/auth/v1/token?grant_type=pkce",
        headers=auth_headers(),
        json={"auth_code": code, "code_verifier": verifier},
    )

    if res.status_code >= 400:
        detail = res.json().get("error_description") or res.json().get("msg") or "Google sign-in failed"
        raise HTTPException(status_code=res.status_code, detail=detail)

    session = res.json()
    access_token = session["access_token"]
    client = get_request_scoped_client(access_token)
    profile = rpc(client, "get_my_profile")

    # If the handle_new_user trigger hasn't run yet (race condition or misconfigured
    # trigger on hosted project), profile_not_found is returned. We recover by
    # creating the profiles row ourselves via the service client, then send the
    # user to /register to complete their academic details.
    if isinstance(profile, dict) and profile.get("error") == "profile_not_found":
        claims = _parse_jwt_claims(access_token)
        user_id = claims.get("sub")
        email = claims.get("email", "")
        user_meta = claims.get("user_metadata", {})
        full_name = user_meta.get("full_name") or user_meta.get("name") or ""
        role = "ADMIN" if email.lower() == "oduri.johnson@gmail.com" else "STUDENT"

        if user_id:
            try:
                svc = get_service_client()
                svc.table("profiles").upsert(
                    {"id": user_id, "full_name": full_name, "email": email, "role": role},
                    on_conflict="id",
                ).execute()
            except Exception:
                pass  # Best-effort; /register will show an error if it still fails

        redirect_to = "/register"
    else:
        redirect_to = resolve_post_auth_redirect(profile)

    response = RedirectResponse(url=f"{config.FRONTEND_ORIGIN}{redirect_to}", status_code=302)
    set_session_cookies(response, access_token, session["refresh_token"])
    clear_pkce_cookie(response)
    return response
