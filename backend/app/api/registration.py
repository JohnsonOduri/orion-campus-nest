from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.cookies import read_access_token
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

    result = rpc(
        client,
        "complete_registration",
        {
            "p_full_name": body.full_name,
            "p_semester": body.semester,
            "p_department": body.department,
            "p_batch": body.batch,
            "p_section": body.section,
            "p_admission_year": body.admission_year,
            "p_programme": body.programme,
        },
    )
    return result
