"""All admin approval-queue actions in one place, both workflows.

Every route here role-checks ADMIN first via require_role (D8) — a clean,
fast 403 for anyone else — before the underlying RLS (`is_admin()`-gated
policies/RPCs) does the actual enforcement.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from .deps import require_role
from ..schemas import ReviewDecisionRequest
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
