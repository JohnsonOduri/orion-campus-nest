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


def set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    # samesite is config.COOKIE_SAMESITE ("lax" unless deliberately overridden
    # for a cross-site frontend/API deployment — see config.py's docstring).
    common = dict(httponly=True, secure=config.COOKIE_SECURE, samesite=config.COOKIE_SAMESITE, path="/")
    response.set_cookie(ACCESS_TOKEN_COOKIE, access_token, **common)
    response.set_cookie(REFRESH_TOKEN_COOKIE, refresh_token, **common)


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/")


def read_access_token(request: Request) -> Optional[str]:
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


def read_refresh_token(request: Request) -> Optional[str]:
    return request.cookies.get(REFRESH_TOKEN_COOKIE)
