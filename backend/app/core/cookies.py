"""Session transport: httpOnly cookies, not bearer tokens in browser JS
(design decision D7) — avoids exposing Supabase access/refresh tokens to
XSS-accessible localStorage. FastAPI reads the access-token cookie back on
every request and forwards it as the caller's JWT to Supabase.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request, Response

from . import config

ACCESS_TOKEN_COOKIE = "orion_access_token"
REFRESH_TOKEN_COOKIE = "orion_refresh_token"


# Supabase refresh tokens stay valid far longer than the hour an access token
# gets, so the cookies outlive the browser window rather than being session
# cookies: without this, closing the tab ended the session even though the
# refresh token was still perfectly good. The access-token cookie is given the
# same lifetime on purpose — it is allowed to hold an *expired* JWT, because
# POST /auth/refresh needs the pair to still be present in order to trade them
# in. Expiry is enforced by Supabase verifying the JWT, never by the cookie.
SESSION_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days


def set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    # samesite is config.COOKIE_SAMESITE ("lax" unless deliberately overridden
    # for a cross-site frontend/API deployment — see config.py's docstring).
    common = dict(
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
        max_age=SESSION_COOKIE_MAX_AGE,
    )
    response.set_cookie(ACCESS_TOKEN_COOKIE, access_token, **common)
    response.set_cookie(REFRESH_TOKEN_COOKIE, refresh_token, **common)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/")


def read_access_token(request: Request) -> Optional[str]:
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


def read_refresh_token(request: Request) -> Optional[str]:
    return request.cookies.get(REFRESH_TOKEN_COOKIE)
