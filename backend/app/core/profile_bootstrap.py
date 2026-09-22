"""Recovery path for when `get_my_profile` returns `profile_not_found` —
a race between a fresh Supabase Auth signup and the `handle_new_user`
trigger that's supposed to create the matching `profiles` row (or a
misconfigured trigger on the hosted project). Extracted from
`oauth.py::callback()`'s original inline logic so both the Google
sign-in path and (in principle) any other auth path can reach it
identically rather than duplicating it.
"""

from __future__ import annotations

import base64
import json

from ..services.supabase_clients import get_service_client


def parse_jwt_claims(token: str) -> dict:
    """Decode the JWT payload (no signature verification needed — Supabase signed it)."""
    try:
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def bootstrap_profile_if_missing(access_token: str) -> str:
    """Best-effort creates the missing `profiles` row from the JWT's own
    claims via the service-role client, then returns the redirect target
    ("/register", so the user completes their academic details). Failures
    are swallowed — /register itself will surface an error if the profile
    genuinely still doesn't exist by then."""
    claims = parse_jwt_claims(access_token)
    user_id = claims.get("sub")
    email = claims.get("email", "")
    user_meta = claims.get("user_metadata", {})
    full_name = user_meta.get("full_name") or user_meta.get("name") or ""
    role = "ADMIN" if email.lower() == "oduri.johnson@gmail.com" else "STUDENT"

    if user_id:
        try:
            svc = get_service_client()
            svc.table("profiles").upsert(
                {"id": user_id, "full_name": full_name, "email": email, "role": role},
                on_conflict="id",
            ).execute()
        except Exception:
            pass

    return "/register"
