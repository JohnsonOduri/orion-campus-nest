"""ORION auth/registration/CR-workflow API — FastAPI, local/dev only.

Every router forwards the caller's own Supabase JWT (D6); nothing here ever
uses the service-role key to serve a user request. CORS is locked to the
one known frontend origin with credentials enabled, matching the httpOnly
cookie session transport (D7).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.api import admin, ai, announcements, auth, campus, cr, faculty, mess, oauth, registration, timetable
from app.core import config
from app.services import gotrue_http

config.require_configured()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    gotrue_http.open_client()
    try:
        yield
    finally:
        gotrue_http.close_client()


app = FastAPI(title="ORION API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# PostgREST's codes for "this JWT is no good any more". These have to come
# back as 401, not 400: the frontend decides whether to refresh the session
# purely from the status, and while these were lumped in with validation
# errors an expired token was indistinguishable from a bad request — so
# nothing refreshed, nothing redirected to /login, and the raw string "JWT
# expired" was rendered straight into the AI chat transcript.
# PGRST300/301/302 = JWT secret missing / expired-or-invalid / anonymous
# access disabled. Deliberately NOT 42501: that is an RLS privilege denial,
# where the token is fine and refreshing it would change nothing.
_AUTH_ERROR_CODES = {"PGRST300", "PGRST301", "PGRST302"}


@app.exception_handler(APIError)
def handle_postgrest_error(_request, exc: APIError):
    # RPC-level `raise exception ...` (role checks, validation, etc.) surface
    # here as PostgREST errors, not Python exceptions — turn them into a
    # clean 400 instead of an opaque 500.
    code = getattr(exc, "code", None)
    message = exc.message or ""
    if code in _AUTH_ERROR_CODES or "JWT" in message.upper():
        return JSONResponse(status_code=401, content={"detail": message or "Session expired"})
    return JSONResponse(status_code=400, content={"detail": message})


app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(registration.router)
app.include_router(cr.router)
app.include_router(admin.router)
app.include_router(timetable.router)
app.include_router(faculty.router)
app.include_router(mess.router)
app.include_router(announcements.router)
app.include_router(ai.router)
app.include_router(campus.router)


@app.get("/health")
def health():
    # RENDER_GIT_COMMIT is set by Render for every deploy; locally it is
    # absent. Lets a deploy be verified ("is my fix actually live?") without
    # guessing from behaviour.
    commit = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "dev"
    return {"status": "ok", "commit": commit[:7]}
