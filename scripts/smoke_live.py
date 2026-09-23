"""Post-deploy smoke test against the LIVE API (Render).

Signs in as the pre-existing test student, then calls the deployed endpoints
with that session cookie — the same way the browser does. Asks one question
per answer category inside a single conversation (so the account's chat
history gets one entry, not dozens).

Usage: .venv/bin/python scripts/smoke_live.py [--api https://...]
Exit code 0 = every check passed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_ai_task import sign_in  # noqa: E402

QUESTIONS = [
    ("What is my next class?", "next_class", "Your next class"),
    ("What classes do I have tomorrow?", "day_of_week_timetable", "timetable"),
    ("When do the end semester exams start?", "academic_calendar", "End Semester"),
    ("What is the attendance requirement?", "none", "80%"),
    ("What are the hostel curfew rules?", "none", "11:00 PM"),
    ("Who is the warden of Sahyadri hostel?", "hostel_wardens", "Warden"),
    ("Who teaches ICS 213?", "faculty_for_course", "Database Management Systems"),
    ("Which faculty work on NLP?", "faculty_research", "Natural Language Processing"),
    ("What's for lunch today?", "mess_today", "Lunch"),
    ("How many credits is ICS 213?", "course_info", "credits"),
    ("What is my CGPA?", "out_of_scope", "don't store"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="https://orion-campus-nest.onrender.com")
    args = parser.parse_args()
    api = args.api.rstrip("/")
    s = requests.Session()
    s.cookies.set("orion_access_token", sign_in())
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")

    r = requests.get(f"{api}/health", timeout=90)
    check("GET /health", r.status_code == 200)
    r = requests.get(f"{api}/calendar", timeout=30)
    check("unauthenticated /calendar is rejected", r.status_code == 401, str(r.status_code))
    for path, minimum in [("/calendar", 20), ("/courses", 30), ("/courses/mine", 1), ("/documents", 10)]:
        r = s.get(f"{api}{path}", timeout=60)
        n = len(r.json()) if r.ok else 0
        check(f"GET {path}", r.ok and n >= minimum, f"{r.status_code}, {n} rows")
    r = s.get(f"{api}/me/academic", timeout=30)
    check("GET /me/academic", r.ok and bool(r.json().get("regulations")), r.text[:120])

    conversation_id = None
    for question, intent, expected in QUESTIONS:
        t = time.perf_counter()
        r = s.post(f"{api}/ai/ask", json={"query": question, "conversation_id": conversation_id}, timeout=90)
        ms = (time.perf_counter() - t) * 1000
        if not r.ok:
            check(question, False, f"HTTP {r.status_code} {r.text[:120]}")
            continue
        body = r.json()
        conversation_id = body.get("conversation_id")
        answer = body.get("answer") or ""
        ok = body.get("intent") == intent and expected.lower() in answer.lower()
        check(question, ok, f"{body.get('intent')} · {ms:.0f} ms · {answer[:90]!r}")

    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
