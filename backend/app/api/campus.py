"""Read-only campus data for the portal pages that used to render mock data
(/calendar, /exams, /courses, /documents, /profile, /search).

Every endpoint uses the caller's own request-scoped client (RLS applies —
CLAUDE.md §13) and reuses backend/query/campus.py, the same lookups the AI
answers from, so a page and ORION can never disagree about a date or a room.
"""

from __future__ import annotations

import re
import threading
import time

from fastapi import APIRouter, Request

from query import campus as campus_data
from query import retrieval

from .deps import get_current_client, get_current_profile

router = APIRouter(tags=["campus"])


@router.get("/calendar")
def calendar(request: Request):
    client = get_current_client(request)
    return campus_data.calendar_events(client)


@router.get("/exams")
def exams(request: Request):
    client, profile = get_current_profile(request)
    rows = campus_data.my_exams(client, None if profile.get("role") == "ADMIN" else profile)
    for r in rows:
        r["courses"] = {"course_code": r.get("course_code"), "course_name": r.get("course_name")}
    windows = [e for e in campus_data.calendar_events(client) if e["event_type"] == "exam"]
    return {"exams": rows, "calendar": windows}


@router.get("/courses")
def courses(request: Request):
    client = get_current_client(request)
    return sorted(campus_data.all_courses(client), key=lambda c: (c.get("semester") or 0, c["course_code"]))


# Credits come from the curriculum text (courses.credits is mostly empty).
# The answer is the same for every student of a cohort + department, so it
# is cached briefly instead of re-parsed on every page view.
_credit_cache: dict[tuple, tuple[float, object]] = {}
_credit_lock = threading.Lock()


def _credits(client, code: str, family, department):
    key = (code, family, department)
    with _credit_lock:
        hit = _credit_cache.get(key)
        if hit and time.monotonic() - hit[0] < 3600:
            return hit[1]
    value = campus_data.credits_from_curriculum(client, code, family, department)
    with _credit_lock:
        _credit_cache[key] = (time.monotonic(), value)
    return value


@router.get("/courses/mine")
def my_courses(request: Request):
    client = get_current_client(request)
    profile = campus_data.student_context(client)
    family = campus_data.cohort_family(profile)
    department = (profile or {}).get("department")
    result = campus_data.my_courses(client)
    out = []
    for fact in result.facts:
        c = fact.data
        ltpc = _credits(client, c["course_code"], family, department)
        out.append({**c, "curriculum": ltpc})
    return out


@router.get("/documents")
def documents(request: Request):
    client = get_current_client(request)
    return (
        client.table("documents")
        .select("id,title,document_type,category,programme,specialisation,cohort,valid_from,valid_until,published_at,status")
        .eq("status", "active")
        .order("title")
        .execute()
        .data
        or []
    )


@router.get("/me/academic")
def my_academic(request: Request):
    """The caller's regulations and classroom — derived, never typed in."""
    client = get_current_client(request)
    profile = campus_data.student_context(client)
    family = campus_data.cohort_family(profile)
    room = None
    if profile:
        classroom = campus_data.classroom(client, profile)
        room = next((f.data for f in classroom.facts if f.data.get("_classroom")), None)
    return {
        "cohort_family": family,
        "regulations": campus_data.REGULATION_TITLES.get(family or ""),
        "classroom": {"room_no": room["room_no"], "room_type": room.get("room_type")} if room else None,
    }


@router.get("/timetable/courses/{course_code}/faculty")
def course_faculty(course_code: str, request: Request):
    client = get_current_client(request)
    code = re.sub(r"\s+", " ", course_code.strip().upper())
    return [f.data for f in retrieval.faculty_for_course(client, code).facts]
