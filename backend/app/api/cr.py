"""CR-side actions: request CR access, upload files, propose timetable
changes, post class announcements.

Every CR route role-checks CR/ADMIN first (D8) — a plain STUDENT must not
reach them even via a direct API call. The database re-checks the same
things regardless (RLS on announcements/approval_requests/storage, and the
submit_cr_timetable RPC), so these checks are for clean errors, not the
boundary.

Workflow (2026-09-28, supabase/migrations/20260928150000_cr_upload_workflow.sql):

  POST /cr/uploads            file → editable draft (backend/cr_ingest/)
  POST /cr/timetable/check    re-check an edited draft
  GET  /cr/timetable/current  the class's live timetable, as a draft to edit
  POST /cr/timetable/submit   → approval_requests (pending admin review)
  POST /cr/announcements/preview  typed/OCR text → category, dates, checks
  POST /cr/announcements      academic + own class → live now; else pending
                              (with `changes`: one-off class changes, live now)
  POST /cr/exams/check|submit exam schedule → approval_requests (admin review)
  POST /cr/class-changes/preview   notice text → one-off changes / "permanent"
  GET  /cr/classes            classes that have a timetable (admin's picker)

An ADMIN uses the same endpoints with an explicit `target` class, and what
they submit is approved at once (same RPCs, audited). A CR's `target` is
ignored: their class always comes from their profile.

The CR's class always comes from their profile, never from the request.

The "own" GET endpoints filter by submitted_by explicitly rather than
leaning on RLS alone: `announcements` also has a permissive
`public_announcements_select` policy, and Postgres OR's permissive
policies together.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from postgrest.exceptions import APIError

from cr_ingest import class_changes as ccx, exam_draft as ed, pipeline, rules, timetable_draft as td
from query.tempo import today_ist

from ..core.cookies import read_access_token
from .deps import get_current_client, get_current_profile, require_role
from ..schemas import (AnnouncementPreviewRequest, ClassAnnouncementRequest, ClassChangePreviewRequest,
                       CrAccessRequest, ExamDraftRequest, ExamSubmitRequest, TargetClass, TimetableDraftRequest,
                       TimetableSubmitRequest)
from ..services import storage
from ..services.supabase_clients import rpc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cr", tags=["cr"])


@router.post("/access-request")
def submit_access_request(body: CrAccessRequest, request: Request):
    client = get_current_client(request)
    return rpc(client, "submit_cr_access_request", {"p_reason": body.reason})


@router.get("/access-request/status")
def access_request_status(request: Request):
    client, profile = get_current_profile(request)
    rows = (
        client.table("approval_requests")
        .select("id,approval_status,rejection_reason,submitter_note,created_at,reviewed_at")
        .eq("submission_type", "cr_access_request")
        .eq("submitted_by", profile["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


# ------------------------------------------------------------------ helpers

def _is_admin(profile: dict) -> bool:
    return profile.get("role") == "ADMIN"


def _target_dict(target: TargetClass | dict | None) -> dict | None:
    if target is None:
        return None
    t = target.model_dump() if isinstance(target, TargetClass) else dict(target)
    return {k: v for k, v in t.items() if v not in (None, "")}


def _class_for(profile: dict, target: TargetClass | dict | None = None, need_section: bool = True) -> dict:
    """The class being acted for: an admin's explicit target, else the
    caller's own class (a CR's target is ignored)."""
    t = _target_dict(target) if _is_admin(profile) else None
    if t:
        if need_section and not (t.get("department") and t.get("section")):
            raise HTTPException(status_code=400, detail="Pick the semester, department and section this is for.")
        return pipeline.class_of(t) or {}
    cls = pipeline.class_of(profile)
    if not cls:
        raise HTTPException(status_code=400, detail=("Pick the class this is for." if _is_admin(profile) else
                                                     "Complete your academic profile (semester, department, section) "
                                                     "first — it decides which class you represent."))
    return cls


def _query_target(semester: int | None, department: str | None, section: str | None) -> dict | None:
    return {"semester": semester, "department": department, "section": section} if semester else None


def _parse_date(value: str | None, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} must be a date (YYYY-MM-DD)") from exc


def _own_path(profile: dict, path: str | None) -> str | None:
    if path and not path.startswith(f"{profile['id']}/"):
        raise HTTPException(status_code=400, detail="That file isn't one of your uploads.")
    return path


def _rpc_target(profile: dict, cls: dict) -> dict | None:
    return {k: cls.get(k) for k in ("semester", "programme", "department", "batch", "section")} if _is_admin(profile) else None


@router.get("/classes")
def classes(request: Request):
    """Every class that has a timetable — the admin's target picker."""
    client, _ = require_role(request, {"CR", "ADMIN"})
    return rpc(client, "orion_class_options")


# ------------------------------------------------------------------ uploads

@router.post("/uploads")
async def upload(request: Request, semester: int | None = None, department: str | None = None,
                 section: str | None = None):
    """Raw file body (PDF/JPEG/PNG/WebP, ≤4 MB) → an editable draft. The
    file is kept (private bucket, the uploader's own folder) so an admin can
    see the original next to what was extracted. Admins pass the target
    class as query parameters."""
    client, profile = require_role(request, {"CR", "ADMIN"})
    data = await request.body()
    target = _query_target(semester, department, section) if _is_admin(profile) else None
    try:
        mime = pipeline.sniff(data)
        draft = pipeline.process(client, profile, data, today_ist(), target=target)
    except pipeline.UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = draft.to_dict()
    try:
        path = storage.new_path(profile["id"], pipeline.EXTENSIONS[mime])
        result["upload_path"] = storage.upload(read_access_token(request) or "", path, data, mime)
    except storage.StorageError as exc:
        logger.warning("CR upload could not be stored: %s", exc)
        result["upload_path"] = None
        result["warnings"].append("The original file couldn't be saved; the admin will only see what you submit.")
    return result


@router.get("/uploads/url")
def upload_url(path: str, request: Request):
    """Short-lived link to an uploaded original. Storage policies decide:
    the uploader, or any admin."""
    require_role(request, {"CR", "ADMIN"})
    try:
        return {"url": storage.signed_url(read_access_token(request) or "", path)}
    except storage.StorageError as exc:
        raise HTTPException(status_code=404, detail="File not found or not yours to view.") from exc


# ---------------------------------------------------------------- timetable

@router.get("/timetable/current")
def current_timetable(request: Request, semester: int | None = None, department: str | None = None,
                      section: str | None = None):
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _class_for(profile, _query_target(semester, department, section))
    entries = td.current_entries(client, cls)
    return pipeline.timetable_payload(client, cls, entries, td.Directory.load(client))


@router.post("/timetable/check")
def check_timetable(body: TimetableDraftRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _class_for(profile, body.target)
    return pipeline.timetable_payload(client, cls, body.entries, td.Directory.load(client))


@router.post("/timetable/submit")
def submit_timetable(body: TimetableSubmitRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _class_for(profile, body.target)
    entries, issues = td.check(body.entries, td.Directory.load(client))
    if td.blocking(issues):
        raise HTTPException(status_code=400, detail="Fix the highlighted periods before submitting: "
                            + "; ".join(i.message for i in issues if i.severity == "error")[:600])
    valid_from = _parse_date(body.valid_from, "valid_from")
    valid_until = _parse_date(body.valid_until, "valid_until")
    if valid_from and valid_from < today_ist():
        raise HTTPException(status_code=400, detail="The new timetable can't start in the past.")
    submitted = rpc(client, "submit_cr_timetable", {
        "p_entries": td.storable(entries),
        "p_valid_from": valid_from.isoformat() if valid_from else None,
        "p_valid_until": valid_until.isoformat() if valid_until else None,
        "p_note": body.note,
        "p_source_path": _own_path(profile, body.upload_path),
        "p_target": _rpc_target(profile, cls),
    })
    if _is_admin(profile):
        # An admin's change is the approval: publish it now (audited by the RPC).
        return {**rpc(client, "review_cr_timetable", {"p_request_id": submitted["id"], "p_approve": True,
                                                      "p_rejection_reason": None}), "published": True}
    return submitted


def _my_submissions(client, profile: dict, kind: str) -> list[dict]:
    rows = (
        client.table("approval_requests")
        .select("id,approval_status,rejection_reason,submitter_note,created_at,reviewed_at,payload,source_file_path")
        .eq("submission_type", kind)
        .eq("submitted_by", profile["id"])
        .order("created_at", desc=True)
        .limit(20)
        .execute()
        .data
    ) or []
    for r in rows:
        payload = r.pop("payload") or {}
        r["periods"] = len(payload.get("entries") or [])
        r["valid_from"] = payload.get("valid_from")
        r["exam_type"] = payload.get("exam_type")
        cls = payload.get("class") or {}
        r["class_label"] = td.class_label(cls) if cls.get("section") else (
            f"Semester {cls.get('semester')} · {cls.get('department') or 'all departments'}" if cls else None)
    return rows


@router.get("/timetable/submissions")
def my_timetable_submissions(request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    return _my_submissions(client, profile, "timetable_update")


# -------------------------------------------------------------------- exams

def _exam_scope(profile: dict, target: TargetClass | None) -> dict:
    if _is_admin(profile):
        t = _target_dict(target) or {}
        if not t.get("semester"):
            raise HTTPException(status_code=400, detail="Pick the semester this exam schedule is for.")
        return {"semester": int(t["semester"]), "department": t.get("department"), "programme": t.get("programme")}
    cls = _class_for(profile)
    return {"semester": cls["semester"], "department": cls["department"], "programme": cls.get("programme")}


def _exam_type(value: str) -> str:
    if value not in ed.EXAM_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown exam type {value!r}")
    return value


@router.get("/exams/current")
def current_exams(request: Request, exam_type: str = "end_sem", semester: int | None = None,
                  department: str | None = None):
    client, profile = require_role(request, {"CR", "ADMIN"})
    scope = _exam_scope(profile, TargetClass(semester=semester, department=department) if semester else None)
    rows = ed.current_exams(client, scope["semester"], _exam_type(exam_type), scope.get("department"))
    for r in rows:
        r["start_time"], r["end_time"] = (r.get("start_time") or "")[:5], (r.get("end_time") or "")[:5]
    return pipeline.exam_payload(client, scope, rows, exam_type, today_ist())


@router.post("/exams/check")
def check_exams(body: ExamDraftRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    scope = _exam_scope(profile, body.target)
    entries = body.entries
    if scope.get("department"):
        entries = [dict(e, department=scope["department"]) for e in entries]
    return pipeline.exam_payload(client, scope, entries, _exam_type(body.exam_type), today_ist())


@router.post("/exams/submit")
def submit_exams(body: ExamSubmitRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    scope = _exam_scope(profile, body.target)
    entries = body.entries
    if scope.get("department"):
        entries = [dict(e, department=scope["department"]) for e in entries]
    checked, issues = ed.check(entries, td.Directory.load(client), today_ist())
    if td.blocking(issues):
        raise HTTPException(status_code=400, detail="Fix the highlighted exams before submitting: "
                            + "; ".join(i.message for i in issues if i.severity == "error")[:600])
    target = None
    if _is_admin(profile):
        target = {"semester": scope["semester"], "programme": scope.get("programme") or "B.Tech"}
        if scope.get("department"):
            target["department"] = scope["department"]
    submitted = rpc(client, "submit_exam_schedule", {
        "p_entries": ed.storable(checked), "p_exam_type": _exam_type(body.exam_type), "p_note": body.note,
        "p_source_path": _own_path(profile, body.upload_path), "p_target": target,
    })
    if _is_admin(profile):
        return {**rpc(client, "review_exam_schedule", {"p_request_id": submitted["id"], "p_approve": True,
                                                       "p_rejection_reason": None}), "published": True}
    return submitted


@router.get("/exams/submissions")
def my_exam_submissions(request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    return _my_submissions(client, profile, "exam_schedule")


# ------------------------------------------------------------ class changes

def _class_week(client, cls: dict) -> tuple[list[dict], list[dict]]:
    week = td.current_entries(client, cls)
    courses = {}
    for e in week:
        if e.get("course_code"):
            courses[e["course_code"]] = {"course_code": e["course_code"], "course_name": e.get("course_name")}
    return week, sorted(courses.values(), key=lambda c: c["course_code"])


@router.post("/class-changes/preview")
def preview_class_changes(body: ClassChangePreviewRequest, request: Request):
    """Notice text → the one-off changes it announces (or "this is a
    permanent change: use the timetable editor"). With `changes`, just
    re-checks the CR's edited list."""
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _class_for(profile, body.target)
    week, courses = _class_week(client, cls)
    today = today_ist()
    if body.changes is not None:
        found = {"permanent": False, "changes": body.changes, "notes": []}
    else:
        found = ccx.extract(body.text, today, week, courses)
    issues = ccx.check(found["changes"], week, today) if found["changes"] else []
    return {**found, "issues": [i.to_dict() for i in issues], "can_post": bool(found["changes"]) and not td.blocking(issues),
            "courses": courses, "class_label": td.class_label(cls)}


# ------------------------------------------------------------ announcements

@router.post("/announcements/preview")
def preview_announcement(body: AnnouncementPreviewRequest, request: Request):
    """What posting this text would do: suggested category, dates, and
    whether it goes live now or to an admin (and why)."""
    _, profile = require_role(request, {"CR", "ADMIN"})
    text = f"{body.title}\n{body.content}".strip()
    draft = rules.draft_announcement(body.content, today_ist(), title=body.title or None, category=body.category)
    draft.sensitive = rules.sensitive_findings(text)
    out = draft.to_dict()
    out["decision"] = _decision(profile, draft.category, draft.sensitive)
    out["permanent_change"] = ccx.is_permanent(text) and draft.category == "CLASS_UPDATE"
    out["class_changes"] = draft.category == "CLASS_UPDATE" and not out["permanent_change"]
    return out


def _decision(profile: dict, category: str, sensitive: list[str]) -> dict:
    if _is_admin(profile):
        return {"publish_now": True, "reason": "You're an admin, so this is published straight away."}
    if sensitive:
        return {"publish_now": False, "reason": "It seems to contain " + ", ".join(sensitive)
                + " — an admin will check it first."}
    if not rules.is_academic(category):
        return {"publish_now": False, "reason": "Only academic notices (quiz, exam, assignment, class update, "
                                                "deadline) go live straight away. An admin will review this one."}
    if not pipeline.class_of(profile):
        return {"publish_now": False, "reason": "Your academic profile is incomplete, so an admin will review it."}
    return {"publish_now": True, "reason": "Academic notice for your class — it will be shared right away."}


def _end_of_day_ist(d: date) -> str:
    return datetime.combine(d, time(23, 59, 59)).isoformat() + "+05:30"


@router.post("/announcements")
def submit_announcement(body: ClassAnnouncementRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    today = today_ist()
    is_admin = _is_admin(profile)
    category = (body.category or rules.classify_category(f"{body.title}\n{body.content}")).upper()
    if category not in rules.CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Unknown category {category}")
    sensitive = rules.sensitive_findings(f"{body.title}\n{body.content}")
    decision = _decision(profile, category, sensitive)
    event_date = _parse_date(body.event_date, "event_date")
    if body.event_time:
        try:
            time.fromisoformat(body.event_time)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="event_time must be HH:MM") from exc
    valid_until = _parse_date(body.valid_until, "valid_until") or rules.default_valid_until(event_date, today)
    if valid_until < today:
        raise HTTPException(status_code=400, detail="The announcement would already be expired.")

    # Who it's for. A CR: always their own class (pending or live). An admin:
    # everyone, or the class they picked.
    if is_admin and body.everyone and not body.changes:
        scope = {}
    else:
        cls = _class_for(profile, body.target)
        scope = {k: cls.get(k) for k in ("semester", "programme", "department", "batch", "section")}

    source_path = _own_path(profile, body.upload_path)
    if body.changes:
        if category != "CLASS_UPDATE":
            raise HTTPException(status_code=400, detail="Class changes can only be posted as a class update.")
        if not decision["publish_now"]:
            raise HTTPException(status_code=400, detail=decision["reason"])
        week, _ = _class_week(client, scope)
        issues = ccx.check(body.changes, week, today)
        if td.blocking(issues):
            raise HTTPException(status_code=400, detail="Fix the class changes first: "
                                + "; ".join(i.message for i in issues if i.severity == "error")[:600])
        last = max([date.fromisoformat(str(c.get("new_date") or c["change_date"])) for c in body.changes])
        until = min(max(valid_until, last + timedelta(days=1)), today + timedelta(days=rules.MAX_AUTO_DAYS))
        announcement = {"title": body.title.strip(), "content": body.content.strip(), **scope,
                        "event_date": event_date.isoformat() if event_date else None, "event_time": body.event_time or None,
                        "auto_published": not is_admin, "valid_until": _end_of_day_ist(until),
                        "source_kind": "upload" if body.upload_path else "typed", "source_file_path": source_path}
        try:
            out = rpc(client, "post_class_update", {"p_announcement": announcement,
                                                    "p_changes": ccx.storable(body.changes)})
        except APIError as exc:
            logger.warning("class update refused: %s", getattr(exc, "message", exc))
            raise HTTPException(status_code=400, detail="These class changes couldn't be posted with your permissions.") from exc
        return {"id": out.get("id"), "status": "active", "auto_published": not is_admin, "changes": out.get("changes"),
                "reason": "Posted — your class's schedule now shows these changes."}

    row = {
        "title": body.title.strip(), "content": body.content.strip(), "category": category,
        "event_date": event_date.isoformat() if event_date else None, "event_time": body.event_time or None,
        "submitted_by": profile["id"], "source_kind": "upload" if body.upload_path else "typed",
        "source_file_path": source_path, **scope,
    }
    now = datetime.now(timezone.utc).isoformat()
    if is_admin:
        row.update(status="active", published_at=now, approved_by=profile["id"], approved_at=now)
    elif decision["publish_now"]:
        valid_until = min(valid_until, today + timedelta(days=rules.MAX_AUTO_DAYS))
        row.update(status="active", auto_published=True, published_at=now)
    else:
        row.update(status="pending")
    row["valid_until"] = _end_of_day_ist(valid_until)

    try:
        created = client.table("announcements").insert(row).execute().data or []
    except APIError as exc:
        logger.warning("announcement insert refused: %s", getattr(exc, "message", exc))
        raise HTTPException(status_code=400, detail="This announcement couldn't be posted with your permissions.") from exc
    return {"id": created[0]["id"] if created else None, "status": row["status"],
            "auto_published": bool(row.get("auto_published")), "reason": decision["reason"]}


@router.get("/announcements")
def my_announcements(request: Request):
    client, profile = get_current_profile(request)
    return (
        client.table("announcements")
        .select("id,title,status,category,rejection_reason,created_at,published_at,event_date,event_time,"
                "valid_until,auto_published,source_kind,semester,department,section")
        .eq("submitted_by", profile["id"])
        .order("created_at", desc=True)
        .execute()
        .data
    )
