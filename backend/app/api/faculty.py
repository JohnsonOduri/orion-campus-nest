"""Faculty directory — read-only.

61 real rows exist (extracted from timetable PDFs during ingestion), small
enough to return in full and let the frontend keep its existing client-side
search/department-filter UI. email/office_location/office_hours/
research_interests are still null for every row (enrichment not done yet,
see CLAUDE.md §24) — the frontend renders those fields conditionally rather
than showing blank/null text.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from .deps import get_current_client

router = APIRouter(prefix="/faculty", tags=["faculty"])


@router.get("")
def list_faculty(request: Request):
    client = get_current_client(request)
    return (
        client.table("faculty")
        .select("id,full_name,initials,department_id,email,office_location,office_hours,research_interests,status")
        .eq("status", "active")
        .order("full_name")
        .execute()
        .data
    )
