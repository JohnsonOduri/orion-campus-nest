"""Create test auth users + student profiles on the LIVE Supabase (admin API).

Server-side administrative tooling (service role + SUPABASE_ACCESS_TOKEN).
Creates two students in DIFFERENT sections so cross-student isolation can be
proven against real JWTs. Profiles match the imported Semester 3 data.

Usage: .venv/bin/python scripts/create_test_students.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.supabase_sql import load_env, project_ref, run_sql  # noqa: E402

STUDENTS = [
    {
        "email": "orion-test-student-a@iiitkottayam.ac.in",
        "password": "OrionTest#2026a",
        "display_name": "Test Student A (CSE-I)",
        "department": "COMPUTER SCIENCE AND ENGINEERING",
        "batch": "I",
        "section": "I",
    },
    {
        "email": "orion-test-student-b@iiitkottayam.ac.in",
        "password": "OrionTest#2026b",
        "display_name": "Test Student B (CSE-II)",
        "department": "COMPUTER SCIENCE AND ENGINEERING",
        "batch": "II",
        "section": "II",
    },
]


def service_headers() -> dict:
    """GoTrue admin headers: the service-role key IS the admin credential."""
    return {
        "apikey": os.environ["SUPABASE_SECRET_KEY"],
        "Authorization": f"Bearer {os.environ['SUPABASE_SECRET_KEY']}",
        "Content-Type": "application/json",
    }


def admin_url(path: str) -> str:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    return f"{base}/auth/v1/{path}"


def main() -> int:
    load_env()
    base = os.environ["SUPABASE_URL"].rstrip("/")

    for s in STUDENTS:
        # 1. create (or reuse) the auth user
        res = requests.post(
            admin_url("admin/users"),
            headers=service_headers(),
            json={"email": s["email"], "password": s["password"],
                  "email_confirm": True, "confirm_email": True},
            timeout=30,
        )
        user = res.json() if res.status_code < 400 else {}
        uid = user.get("user", {}).get("id") or user.get("id")
        if not uid and res.status_code == 422:
            # already exists: look up by email via SQL
            rows = run_sql(
                "select id from auth.users where email = "
                f"'{s['email']}' limit 1"
            )
            uid = rows[0]["id"] if rows else None
        if not uid:
            print(f"ERROR creating {s['email']}: {res.status_code} {res.text[:300]}")
            return 1
        s["user_id"] = uid
        print(f"user: {s['email']} -> {uid}")

        # 2. upsert the student profile (service-role SQL; table is RLS-protected)
        run_sql(
            f"""insert into public.student_profiles
                  (user_id, display_name, semester, programme, department, batch, section)
                values ('{uid}', '{s['display_name']}', 3, 'B.Tech',
                        '{s['department']}', '{s['batch']}', '{s['section']}')
                on conflict (user_id) do update set
                  display_name = excluded.display_name,
                  semester = excluded.semester,
                  department = excluded.department,
                  batch = excluded.batch,
                  section = excluded.section"""
        )
        print(f"profile upserted for {uid}")

        # 3. verify sign-in works (GoTrue) and we can obtain a JWT
        login = requests.post(
            f"{base}/auth/v1/token?grant_type=password",
            headers={"apikey": os.environ["SUPABASE_PUBLIC_ANON_KEY"],
                     "Content-Type": "application/json"},
            json={"email": s["email"], "password": s["password"]},
            timeout=30,
        )
        if login.status_code != 200:
            print(f"ERROR signing in {s['email']}: {login.status_code} {login.text[:300]}")
            return 1
        s["access_token"] = login.json()["access_token"]
        print(f"  signed in OK (jwt len={len(s['access_token'])})")

    Path("/tmp/orion_test_students.json").write_text(json.dumps(STUDENTS))
    print("\nsaved -> /tmp/orion_test_students.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
