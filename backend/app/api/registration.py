from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.cookies import read_access_token
from ..schemas import RegisterRequest
from ..services.supabase_clients import get_request_scoped_client, get_service_client, rpc

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
    # uid for a privileged action: the cookie's *value* is attacker-settable
    # on a raw HTTP request (httpOnly only blocks browser JS from reading
    # it, not a forged request), so an unverified decode would let anyone
    # hijack an arbitrary account's password via the service-role admin API
    # below just by guessing/knowing its UUID.
    profile = rpc(client, "get_my_profile")
    if isinstance(profile, dict) and profile.get("error"):
        raise HTTPException(status_code=401, detail=profile["error"])
    uid = profile["id"]

    # Set password via the Admin API (auth.admin.update_user_by_id) which only
    # needs the user's ID — not a live GoTrue session in the client object.
    # Using client.auth.update_user() would raise AuthSessionMissingError
    # because the request-scoped client has no session, only a forwarded JWT.
    if body.password:
        try:
            svc = get_service_client()
            svc.auth.admin.update_user_by_id(uid, {"password": body.password})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to set password: {exc}") from exc

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
