"""Live end-to-end verification of the query router / retrieval / context
layer (backend/query/) against the real hosted Supabase project.

This is NOT a pytest test (like scripts/verify_import.py, it needs live
network + credentials, so it stays out of the offline `pytest tests/` run).
It proves the three required cases work against real data with a real,
request-scoped, RLS-respecting client — never service-role — exactly
matching src/lib/supabase-server.ts's security model:

  1. "What is my next class?"                              -> STRUCTURED
  2. "What are the attendance requirements?"                -> SEMANTIC
  3. "Which faculty work in NLP and when can I meet them?"  -> HYBRID

Usage:
    .venv/bin/python scripts/verify_query_router.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query.service import answer_query  # noqa: E402

TEST_STUDENT_EMAIL = "orion-test-student-a@iiitkottayam.ac.in"
TEST_STUDENT_PASSWORD = "OrionTest#2026a"

CASES = [
    "What is my next class?",
    "What are the attendance requirements?",
    "Which faculty work in NLP and when can I meet them?",
]


def load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_request_scoped_client():
    """Exactly the pattern src/lib/supabase-server.ts uses for user
    requests: anon key + the caller's own JWT via password sign-in against
    the already-provisioned test student (scripts/create_test_students.py).
    Never service-role."""
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    anon = os.environ.get("SUPABASE_PUBLIC_ANON_KEY") or os.environ.get("SUPABASE_PUBLISHABLE_KEY")

    res = requests.post(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": anon, "Content-Type": "application/json"},
        json={"email": TEST_STUDENT_EMAIL, "password": TEST_STUDENT_PASSWORD},
        timeout=30,
    )
    res.raise_for_status()
    jwt = res.json()["access_token"]

    client = create_client(url, anon)
    client.postgrest.auth(jwt)
    return client


def main() -> int:
    load_env()
    client = get_request_scoped_client()
    print(f"authenticated as: {TEST_STUDENT_EMAIL} (request-scoped, anon key + JWT, RLS enforced)\n")

    ok = True
    for query in CASES:
        print(f"=== {query!r} ===")
        ctx = answer_query(client, query)
        print(f"route: {ctx.route.value}")
        print(f"has_answer: {ctx.has_answer}")
        for f in ctx.facts:
            print(f"  fact: {f.claim}")
            print(f"        source: {f.source}")
        for s in ctx.snippets:
            print(f"  snippet [{s.document_title}] sim={s.similarity:.3f}: {s.content[:120]!r}")
        for w in ctx.warnings:
            print(f"  warning: {w}")
        if not ctx.has_answer:
            print("  !! NO ANSWER GROUNDED — this is a failure for these 3 required cases")
            ok = False
        print()

    print(json.dumps({"all_three_cases_grounded": ok}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
