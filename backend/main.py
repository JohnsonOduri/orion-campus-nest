"""ORION auth/registration/CR-workflow API — FastAPI, local/dev only.

Every router forwards the caller's own Supabase JWT (D6); nothing here ever
uses the service-role key to serve a user request. CORS is locked to the
one known frontend origin with credentials enabled, matching the httpOnly
cookie session transport (D7).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.api import admin, announcements, auth, cr, faculty, mess, oauth, registration, timetable
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


@app.exception_handler(APIError)
def handle_postgrest_error(_request, exc: APIError):
    # RPC-level `raise exception ...` (role checks, validation, etc.) surface
    # here as PostgREST errors, not Python exceptions — turn them into a
    # clean 400 instead of an opaque 500.
    return JSONResponse(status_code=400, content={"detail": exc.message})


app.include_router(auth.router)
app.include_router(oauth.router)
app.include_router(registration.router)
app.include_router(cr.router)
app.include_router(admin.router)
app.include_router(timetable.router)
app.include_router(faculty.router)
app.include_router(mess.router)
app.include_router(announcements.router)


@app.get("/health")
def health():
    return {"status": "ok"}
