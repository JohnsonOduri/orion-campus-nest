"""Student-facing announcement reads.

CR authoring (submit_announcement) and admin review already exist in
cr.py/admin.py — this is the missing piece: a plain student reading active,
unexpired announcements. Relies on the same `public_announcements_select`
RLS policy those routers' docstrings already reference (any authenticated
user, active + unexpired rows) — this endpoint just gives the frontend
something to call instead of reading mock-data.ts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from .deps import get_current_client

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements(request: Request):
    client = get_current_client(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    return (
        client.table("announcements")
        .select("id,title,content,category,department,batch,target_role,created_at,published_at")
        .eq("status", "active")
        .or_(f"valid_until.is.null,valid_until.gte.{now_iso}")
        .order("created_at", desc=True)
        .execute()
        .data
    )
