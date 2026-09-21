"""CR-side actions: request CR access, author announcements.

`/cr/announcements` proactively role-checks CR/ADMIN (D8) — a plain
STUDENT must not reach this even via a direct API call, not just a hidden
button. The underlying submit_announcement() RPC re-checks the same thing
server-side regardless (defense in depth).

The "own" GET endpoints below filter by submitted_by explicitly rather than
leaning on RLS alone: `announcements` also has a separate, permissive
`public_announcements_select` policy (any authenticated user, any active
row) — without an explicit filter, "my announcements" would silently
include everyone else's active announcements too, since Postgres OR's
permissive policies together.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from .deps import get_current_client, get_current_profile, require_role
from ..schemas import AnnouncementSubmitRequest, CrAccessRequest
from ..services.supabase_clients import rpc

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


@router.post("/announcements")
def submit_announcement(body: AnnouncementSubmitRequest, request: Request):
    client, _ = require_role(request, {"CR", "ADMIN"})
    return rpc(
        client,
        "submit_announcement",
        {
            "p_title": body.title,
            "p_content": body.content,
            "p_category": body.category,
            "p_department": body.department,
            "p_batch": body.batch,
            "p_target_role": body.target_role,
            "p_valid_from": body.valid_from,
            "p_valid_until": body.valid_until,
        },
    )


@router.get("/announcements")
def my_announcements(request: Request):
    client, profile = get_current_profile(request)
    return (
        client.table("announcements")
        .select("id,title,status,category,rejection_reason,created_at,published_at")
        .eq("submitted_by", profile["id"])
        .order("created_at", desc=True)
        .execute()
        .data
    )
