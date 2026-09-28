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

from cr_ingest import pipeline, rules, timetable_draft as td
from query.tempo import today_ist

from ..core.cookies import read_access_token
from .deps import get_current_client, get_current_profile, require_role
from ..schemas import (AnnouncementPreviewRequest, ClassAnnouncementRequest, CrAccessRequest,
                       TimetableDraftRequest, TimetableSubmitRequest)
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

def _my_class(profile: dict) -> dict:
    cls = pipeline.class_of(profile)
    if not cls:
        raise HTTPException(status_code=400, detail="Complete your academic profile (semester, department, "
                                                    "section) first — it decides which class you represent.")
    return cls


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


# ------------------------------------------------------------------ uploads

@router.post("/uploads")
async def upload(request: Request):
    """Raw file body (PDF/JPEG/PNG/WebP, ≤4 MB) → an editable draft. The
    file is kept (private bucket, the CR's own folder) so an admin can see
    the original next to what was extracted."""
    client, profile = require_role(request, {"CR", "ADMIN"})
    data = await request.body()
    try:
        mime = pipeline.sniff(data)
        draft = pipeline.process(client, profile, data, today_ist())
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
def current_timetable(request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _my_class(profile)
    entries = td.current_entries(client, cls)
    return pipeline.timetable_payload(client, cls, entries, td.Directory.load(client))


@router.post("/timetable/check")
def check_timetable(body: TimetableDraftRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    cls = _my_class(profile)
    return pipeline.timetable_payload(client, cls, body.entries, td.Directory.load(client))


@router.post("/timetable/submit")
def submit_timetable(body: TimetableSubmitRequest, request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    _my_class(profile)
    entries, issues = td.check(body.entries, td.Directory.load(client))
    if td.blocking(issues):
        raise HTTPException(status_code=400, detail="Fix the highlighted periods before submitting: "
                            + "; ".join(i.message for i in issues if i.severity == "error")[:600])
    valid_from = _parse_date(body.valid_from, "valid_from")
    valid_until = _parse_date(body.valid_until, "valid_until")
    if valid_from and valid_from < today_ist():
        raise HTTPException(status_code=400, detail="The new timetable can't start in the past.")
    return rpc(client, "submit_cr_timetable", {
        "p_entries": td.storable(entries),
        "p_valid_from": valid_from.isoformat() if valid_from else None,
        "p_valid_until": valid_until.isoformat() if valid_until else None,
        "p_note": body.note,
        "p_source_path": _own_path(profile, body.upload_path),
    })


@router.get("/timetable/submissions")
def my_timetable_submissions(request: Request):
    client, profile = require_role(request, {"CR", "ADMIN"})
    rows = (
        client.table("approval_requests")
        .select("id,approval_status,rejection_reason,submitter_note,created_at,reviewed_at,payload,source_file_path")
        .eq("submission_type", "timetable_update")
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
    return rows


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
    return out


def _decision(profile: dict, category: str, sensitive: list[str]) -> dict:
    if profile.get("role") == "ADMIN":
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

    row = {
        "title": body.title.strip(), "content": body.content.strip(), "category": category,
        "event_date": event_date.isoformat() if event_date else None, "event_time": body.event_time or None,
        "submitted_by": profile["id"], "source_kind": "upload" if body.upload_path else "typed",
        "source_file_path": _own_path(profile, body.upload_path),
    }
    is_admin = profile.get("role") == "ADMIN"
    if decision["publish_now"] and not is_admin:
        cls = pipeline.class_of(profile) or {}
        valid_until = min(valid_until, today + timedelta(days=rules.MAX_AUTO_DAYS))
        row.update(status="active", auto_published=True, published_at=datetime.now(timezone.utc).isoformat(),
                   semester=cls.get("semester"), programme=cls.get("programme"), department=cls.get("department"),
                   batch=cls.get("batch"), section=cls.get("section"))
    elif is_admin:
        row.update(status="active", published_at=datetime.now(timezone.utc).isoformat(),
                   approved_by=profile["id"], approved_at=datetime.now(timezone.utc).isoformat())
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
                "valid_until,auto_published,source_kind")
        .eq("submitted_by", profile["id"])
        .order("created_at", desc=True)
        .execute()
        .data
    )
