from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from postgrest.exceptions import APIError

from ..core.cookies import read_access_token
from query.tempo import today_ist

from ..schemas import RegisterRequest
from ..services.supabase_clients import get_request_scoped_client, rpc

router = APIRouter(prefix="/auth", tags=["registration"])


@router.post("/register")
def register(body: RegisterRequest, request: Request):
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    client = get_request_scoped_client(token)

    # Resolve identity through a real PostgREST round trip — get_my_profile()
    # runs under auth.uid(), which only resolves if PostgREST actually
    # verifies the JWT's signature. Never decode `token` locally to get a
    # uid for a privileged action.
    profile = rpc(client, "get_my_profile")
    if isinstance(profile, dict) and profile.get("error"):
        raise HTTPException(status_code=401, detail=profile["error"])

    try:
        result = _register(client, body)
    except APIError as exc:
        # Students can't see each other's profiles, so a clash only shows up
        # as the unique index firing: say what it means.
        if "roll_number" in str(getattr(exc, "message", "")) or "roll_number" in str(exc):
            raise HTTPException(status_code=400, detail="That roll number is already registered to another account. "
                                                        "Check it, or contact the admin if it's yours.") from exc
        raise
    return result


def _register(client, body: RegisterRequest):
    return rpc(
        client,
        "complete_registration",
        {
            "p_full_name": body.full_name,
            "p_semester": body.semester,
            "p_department": body.department,
            "p_batch": body.batch or body.section,
            "p_section": body.section,
            "p_admission_year": body.admission_year,
            "p_programme": body.programme,
            "p_roll_number": body.roll_number,
        },
    )


@router.get("/register/options")
def register_options(request: Request):
    """The dropdowns: classes that actually have a timetable (programme →
    semester → department → section) and admission years up to this one."""
    token = read_access_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    client = get_request_scoped_client(token)
    year = today_ist().year
    return {"classes": rpc(client, "orion_class_options") or [], "admission_years": list(range(year, year - 8, -1))}
