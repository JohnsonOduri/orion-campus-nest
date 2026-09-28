"""All admin approval-queue actions in one place, both workflows.

Every route here role-checks ADMIN first via require_role (D8) — a clean,
fast 403 for anyone else — before the underlying RLS (`is_admin()`-gated
policies/RPCs) does the actual enforcement.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from cr_ingest import timetable_draft as td

from .deps import require_role
from ..schemas import ArchiveRequest, ReviewDecisionRequest
from ..services.supabase_clients import rpc

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/cr-requests")
def pending_cr_requests(request: Request):
    client, _ = require_role(request, {"ADMIN"})
    return (
        client.table("approval_requests")
        .select("id,submitted_by,submitter_note,created_at")
        .eq("submission_type", "cr_access_request")
        .eq("approval_status", "pending")
        .order("created_at")
        .execute()
        .data
    )


@router.post("/cr-requests/{request_id}/review")
def review_cr_request(request_id: int, body: ReviewDecisionRequest, request: Request):
    client, _ = require_role(request, {"ADMIN"})
    rpc(
        client,
        "review_cr_access_request",
        {
            "p_request_id": request_id,
            "p_approve": body.approve,
            "p_rejection_reason": body.rejection_reason,
        },
    )
    return {"ok": True}


@router.get("/announcements")
def pending_announcements(request: Request):
    client, _ = require_role(request, {"ADMIN"})
    return (
        client.table("announcements")
        .select("id,title,content,category,department,batch,target_role,submitted_by,created_at")
        .eq("status", "pending")
        .order("created_at")
        .execute()
        .data
    )


@router.post("/announcements/{announcement_id}/review")
def review_announcement(announcement_id: int, body: ReviewDecisionRequest, request: Request):
    client, _ = require_role(request, {"ADMIN"})
    return rpc(
        client,
        "review_announcement",
        {
            "p_id": announcement_id,
            "p_approve": body.approve,
            "p_rejection_reason": body.rejection_reason,
        },
    )


def _people(client, ids: set) -> dict:
    if not ids:
        return {}
    rows = client.table("profiles").select("id,full_name,email").in_("id", list(ids)).execute().data or []
    return {r["id"]: r for r in rows}


@router.get("/timetable-submissions")
def pending_timetable_submissions(request: Request):
    """Pending CR timetable proposals, each re-checked against the live
    directory and compared with the class's current timetable — the admin
    reviews what would actually change, with names resolved server-side
    (not whatever the submission claims)."""
    client, _ = require_role(request, {"ADMIN"})
    rows = (
        client.table("approval_requests")
        .select("id,submitted_by,submitter_note,created_at,payload,source_file_path")
        .eq("submission_type", "timetable_update")
        .eq("approval_status", "pending")
        .order("created_at")
        .execute()
        .data
    ) or []
    if not rows:
        return []
    directory = td.Directory.load(client)
    people = _people(client, {r["submitted_by"] for r in rows})
    out = []
    for r in rows:
        payload = r.get("payload") or {}
        cls = payload.get("class") or {}
        entries, issues = td.check(payload.get("entries") or [], directory)
        current = td.current_entries(client, cls) if cls else []
        out.append({
            "id": r["id"],
            "submitted_by": people.get(r["submitted_by"]) or {"id": r["submitted_by"]},
            "note": r.get("submitter_note"),
            "created_at": r["created_at"],
            "class": cls,
            "class_label": td.class_label(cls) if cls else "unknown class",
            "valid_from": payload.get("valid_from"),
            "valid_until": payload.get("valid_until"),
            "entries": entries,
            "issues": [i.to_dict() for i in issues],
            "diff": td.diff(current, entries),
            "current_count": len(current),
            "source_file_path": r.get("source_file_path"),
        })
    return out


@router.post("/timetable-submissions/{request_id}/review")
def review_timetable_submission(request_id: int, body: ReviewDecisionRequest, request: Request):
    client, _ = require_role(request, {"ADMIN"})
    return rpc(client, "review_cr_timetable", {
        "p_request_id": request_id,
        "p_approve": body.approve,
        "p_rejection_reason": body.rejection_reason,
    })


@router.get("/announcements/live")
def live_announcements(request: Request):
    """Everything students can see right now, newest first — including
    notices CRs published without review, which an admin can take down."""
    client, _ = require_role(request, {"ADMIN"})
    rows = (
        client.table("announcements")
        .select("id,title,content,category,semester,department,section,event_date,event_time,valid_until,"
                "auto_published,submitted_by,published_at,source_file_path")
        .eq("status", "active")
        .order("published_at", desc=True)
        .limit(50)
        .execute()
        .data
    ) or []
    people = _people(client, {r["submitted_by"] for r in rows if r.get("submitted_by")})
    for r in rows:
        r["submitted_by"] = people.get(r.get("submitted_by")) or {"id": r.get("submitted_by")}
    return rows


@router.post("/announcements/{announcement_id}/archive")
def archive_announcement(announcement_id: int, body: ArchiveRequest, request: Request):
    client, _ = require_role(request, {"ADMIN"})
    return rpc(client, "archive_announcement", {"p_id": announcement_id, "p_reason": body.reason})


@router.get("/logs")
def audit_logs(request: Request, limit: int = 100):
    """Audit trail for the admin Logs page: who did what, to which entity, when.

    `audit_logs.actor_id` has no FK to `profiles`, so PostgREST can't embed
    the actor — the names are resolved in a second query and merged here
    rather than leaving the UI to render bare UUIDs. Both queries run on the
    caller's own JWT, so the audit_logs_select_admin / profiles_select_admin_all
    policies are what actually authorize this, not the require_role check.
    """
    client, _ = require_role(request, {"ADMIN"})

    rows = (
        client.table("audit_logs")
        .select("id,actor_id,action,entity_type,entity_id,old_data,new_data,metadata,created_at")
        .order("created_at", desc=True)
        .limit(max(1, min(limit, 500)))
        .execute()
        .data
    ) or []

    actor_ids = {r["actor_id"] for r in rows if r.get("actor_id")}
    actors: dict[str, dict] = {}
    if actor_ids:
        for p in (
            client.table("profiles")
            .select("id,full_name,email,role")
            .in_("id", list(actor_ids))
            .execute()
            .data
            or []
        ):
            actors[p["id"]] = p

    for r in rows:
        r["actor"] = actors.get(r.get("actor_id"))
    return rows
