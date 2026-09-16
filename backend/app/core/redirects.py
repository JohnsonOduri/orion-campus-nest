"""Where to send the browser after a successful sign-in — one place, used
by both POST /auth/login and the OAuth callback, so the two paths can never
disagree about routing logic.

Only STUDENT/CR/ADMIN are real, in-use roles for this app today — FACULTY
exists as a valid `profiles.role` value (README's product scope), but there
is no faculty-facing experience built yet, so it's deliberately not mapped
here; it falls through to the generic default like any other unhandled
value rather than being silently pointed at the student dashboard as if
that were a real faculty flow.
"""

from __future__ import annotations

from typing import Any

_ROLE_ROUTES = {
    "ADMIN": "/admin",
    "CR": "/cr",
    "STUDENT": "/dashboard",
}

# "onboarded" means "has a student_profiles row" (see get_my_profile() /
# design decision D1) — that's only ever true, or even applicable, for
# STUDENT/CR accounts. ADMIN (and FACULTY) never get a student_profiles row,
# so gating them on it too would bounce them into /register forever.
_ONBOARDING_REQUIRED_ROLES = {"STUDENT", "CR"}


def resolve_post_auth_redirect(profile: dict[str, Any]) -> str:
    if profile.get("error"):
        import urllib.parse
        encoded = urllib.parse.quote(str(profile.get("error")))
        return f"/login?error={encoded}"
    role = profile.get("role", "")
    if role in _ONBOARDING_REQUIRED_ROLES and not profile.get("onboarded"):
        return "/register"
    return _ROLE_ROUTES.get(role, "/dashboard")
