"""Faculty directory — read-only.

185 real rows, rebuilt from the full institute directory (see
scripts/rebuild_faculty.py — Data/iiit_kottayam_people.csv). Every row
carries a `category` (hod/administrative/faculty/professional_support).
Coverage is still partial for some enrichment fields (email/phone/
designation/office_location/office_hours/research_interests/profile_url)
— the frontend renders each conditionally rather than showing blank/null
text.
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
        .select(
            "id,full_name,initials,department_id,email,phone,designation,office_location,"
            "office_hours,research_interests,profile_url,category,status"
        )
        .eq("status", "active")
        .order("full_name")
        .execute()
        .data
    )
