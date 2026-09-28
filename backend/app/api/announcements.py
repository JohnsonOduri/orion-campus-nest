"""Student-facing announcement reads.

CR authoring (submit_announcement) and admin review already exist in
cr.py/admin.py — this is the missing piece: a plain student reading active,
unexpired announcements. Relies on the same `public_announcements_select`
RLS policy those routers' docstrings already reference (any authenticated
user, active + unexpired rows) — this endpoint just gives the frontend
something to call instead of reading mock-data.ts.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from query import campus

from .deps import get_current_profile

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements(request: Request):
    """Live, unexpired announcements relevant to the caller: campus-wide
    ones plus notices for their own class (campus.announcement_visible_to)."""
    client, profile = get_current_profile(request)
    return campus.current_announcements(client, profile)
