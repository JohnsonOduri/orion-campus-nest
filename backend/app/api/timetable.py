"""Real timetable data — day/week/next-class views.

Reuses the exact RPCs the pre-existing TanStack Start API
(src/lib/timetable-api.ts, now dead code) already called
(orion_student_context / orion_day_timetable / orion_week_timetable /
orion_next_class, 608 live entries) — only the identity resolution changes.
That old path read an `Authorization: Bearer` header, which the browser
never sends anymore now that sessions are httpOnly cookies scoped to this
service's origin (D7); get_current_client() here reads the real session
cookie instead, so a logged-in student actually sees their own timetable
instead of silently falling back to demo data forever.

Returns each RPC's raw row shape rather than reshaping it — the frontend
does its own display mapping (day names, HH:MM slicing, live/upcoming
status) in one place, in TypeScript.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from .deps import get_current_client

router = APIRouter(prefix="/timetable", tags=["timetable"])


def _student_context(client) -> dict | None:
    return client.rpc("orion_student_context").execute().data


@router.get("/day")
def day_timetable(request: Request):
    client = get_current_client(request)
    ctx = _student_context(client)
    entries = client.rpc("orion_day_timetable", {"p_on_date": date.today().isoformat()}).execute().data
    return {"student": ctx, "entries": entries or []}


@router.get("/week")
def week_timetable(request: Request):
    client = get_current_client(request)
    ctx = _student_context(client)
    entries = client.rpc("orion_week_timetable", {"p_on_date": date.today().isoformat()}).execute().data
    return {"student": ctx, "entries": entries or []}


@router.get("/next")
def next_class(request: Request, include_activities: bool = False):
    client = get_current_client(request)
    ctx = _student_context(client)
    row = client.rpc("orion_next_class", {"p_include_activities": include_activities}).execute().data
    return {"student": ctx, "next_class": row, "include_activities": include_activities}
