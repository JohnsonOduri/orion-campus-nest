"""Google sign-in — frontend-driven.

The browser drives the Google OAuth/PKCE handshake itself via supabase-js
(`src/lib/supabase-browser.ts`, `src/routes/login.tsx`,
`src/routes/auth.callback.tsx`) — no backend round trip is needed to even
*start* signing in, unlike the previous design where
`GET /auth/oauth/google/authorize` required this FastAPI service to be
running before the browser could reach Google at all.

This router's only remaining job is the one-shot handoff: the frontend
callback page exchanges the code for a Supabase session itself, then POSTs
the resulting tokens here exactly once. This endpoint turns them into the
same httpOnly cookies every other auth path already sets
(`core/cookies.py`) and resolves the same post-auth redirect
(`core/redirects.py`) that `/auth/login` uses.

Security note (narrows the previous "tokens never touch JS" guarantee,
decision D7, which still holds in full for password login/signup): Google
sign-in tokens do pass through frontend JS/`sessionStorage` for the
duration of the handshake — see `supabase-browser.ts`'s docstring for why
that's unavoidable for a redirect-based OAuth flow, and
`auth.callback.tsx`, which actively wipes that storage the moment this
endpoint's response comes back. This endpoint doesn't (and can't) verify
that on its own — it trusts nothing about the request body except what a
real PostgREST call using it as a bearer token proves.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from ..core.cookies import set_session_cookies
from ..core.profile_bootstrap import bootstrap_profile_if_missing
from ..core.redirects import resolve_post_auth_redirect
from ..schemas import SetSessionRequest
from ..services.supabase_clients import get_request_scoped_client, rpc

router = APIRouter(prefix="/auth/oauth/google", tags=["oauth"])


@router.post("/set-session")
def set_session(body: SetSessionRequest, response: Response):
    # Forwarding the token straight to PostgREST is what actually verifies
    # it (signature, expiry) — this call is the real trust boundary, not
    # anything about how the token arrived in this request body.
    client = get_request_scoped_client(body.access_token)
    profile = rpc(client, "get_my_profile")

    if isinstance(profile, dict) and profile.get("error") == "profile_not_found":
        redirect_to = bootstrap_profile_if_missing(body.access_token)
    else:
        redirect_to = resolve_post_auth_redirect(profile)

    set_session_cookies(response, body.access_token, body.refresh_token)
    return {"ok": True, "redirect_to": redirect_to}
