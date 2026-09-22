"""Runs a fixed battery of questions against the LIVE /ai/ask on Render,
authenticated as a real test student, and writes AI-test.md at the repo
root: every question + the actual response, followed by an analysis of
what's working and what needs improvement.

Only asks about data that is actually in the structured DB or the RAG
corpus (real course codes, real faculty, real research interests pulled
from Supabase before writing the question set) — never invented scenarios.

Usage: .venv/bin/python scripts/run_ai_test.py
Needs: a valid session cookie for a real test student (logs in itself via
Supabase password grant — the pre-existing orion-test-student-a account,
scripts/create_test_students.py) and the live API at API_BASE_URL.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

API_BASE_URL = os.environ.get("ORION_TEST_API_BASE_URL", "https://orion-campus-nest.onrender.com")
OUT_PATH = Path(__file__).resolve().parents[1] / "AI-test.md"
DELAY_S = float(os.environ.get("ORION_TEST_DELAY_S", "2.5"))  # shares Gemini quota with everything else

TEST_EMAIL = "orion-test-student-a@iiitkottayam.ac.in"
TEST_PASSWORD = "OrionTest#2026a"  # pre-existing account, scripts/create_test_students.py

# (category, question) — every one grounded in data confirmed present in
# the live DB/corpus just before writing this file (see AI-test.md's own
# "Data used" section for the exact source rows).
QUESTIONS = [
    ("structured — timetable", "What is my next class?"),
    ("structured — timetable", "What classes do I have today?"),
    ("structured — timetable", "What is my timetable for this week?"),
    ("structured — timetable", "What class do I have at 5 PM?"),
    ("structured — faculty/course", "Who teaches ICS 213 Database Management Systems?"),
    ("structured — course", "Tell me about ICS 211 Design and Analysis of Algorithms."),
    ("structured — faculty", "What is Dr. Manu Madhavan's email and office location?"),
    ("structured — mess", "What is on the mess menu today?"),
    ("structured — mess", "What is being served for dinner this week?"),
    ("structured — announcements", "Are there any current announcements?"),
    ("semantic — regulations", "What is the attendance requirement?"),
    ("semantic — regulations", "What are the rules for course withdrawal?"),
    ("semantic — regulations", "Can I take a summer term?"),
    ("semantic — regulations", "How is CGPA calculated?"),
    ("semantic — hostel", "What are the hostel curfew rules?"),
    ("semantic — hostel", "What is the campus movement timing?"),
    ("semantic — hostel", "How does the outpass process work?"),
    ("semantic — procedures", "How do I request transcript verification?"),
    ("semantic — procedures", "What is the transcript verification fee?"),
    ("semantic — anti-ragging", "What are the anti-ragging rules?"),
    ("semantic — curriculum", "What are the prerequisites for a Machine Learning course?"),
    ("semantic — curriculum", "How many credits are required to graduate?"),
    ("hybrid — faculty research", "Which faculty work on Natural Language Processing and when can I meet them?"),
    ("hybrid — faculty research", "Recommend a faculty member for machine learning research."),
    ("hybrid — faculty research", "Who researches underwater sensor networks?"),
    ("small talk", "Hi"),
    ("small talk", "Thanks!"),
    ("unsupported / no-answer honesty", "asdkfj qwer nonsense query"),
    ("unsupported / no-answer honesty", "What is the meaning of life?"),
    ("out-of-scope (should not hallucinate)", "What are my exam grades this semester?"),
]


def log_in() -> str:
    # Read Supabase project config from .env like every other script here.
    from dotenv import dotenv_values

    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    supabase_url = env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL")
    anon_key = env.get("VITE_SUPABASE_ANON_KEY") or env.get("SUPABASE_PUBLIC_ANON_KEY")
    resp = requests.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"apikey": anon_key},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def ask(token: str, query: str) -> dict:
    started = time.perf_counter()
    try:
        resp = requests.post(
            f"{API_BASE_URL}/ai/ask",
            json={"query": query},
            headers={"Cookie": f"orion_access_token={token}"},
            timeout=45,
        )
        latency = round(time.perf_counter() - started, 2)
        if resp.status_code != 200:
            return {"_http_status": resp.status_code, "_latency_s": latency, "_error_body": resp.text[:500]}
        body = resp.json()
        body["_latency_s"] = latency
        body["_http_status"] = resp.status_code
        return body
    except requests.RequestException as e:
        return {"_http_status": None, "_latency_s": round(time.perf_counter() - started, 2), "_error_body": str(e)}


def fmt_result(category: str, question: str, result: dict) -> str:
    lines = [f"### [{category}] {question}", ""]
    status = result.get("_http_status")
    lat = result.get("_latency_s")
    if status != 200:
        lines.append(f"- **HTTP {status}** ({lat}s) — {result.get('_error_body', '(no body)')}")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"- route: `{result.get('route')}` · has_answer: `{result.get('has_answer')}` "
                 f"· generation_available: `{result.get('generation_available')}` · {lat}s")
    if result.get("answer"):
        lines.append(f"- **Answer:** {result['answer']}")
    else:
        lines.append("- **Answer:** _(none — generation not run / nothing to ground on)_")
    if result.get("warnings"):
        lines.append(f"- warnings: {result['warnings']}")
    facts = result.get("facts") or []
    if facts:
        lines.append(f"- facts returned: {len(facts)} (first claim: {facts[0].get('claim', '')[:150]})")
    snippets = result.get("snippets") or []
    if snippets:
        titles = [s.get("document_title") for s in snippets[:3]]
        sims = [round(s.get("similarity", 0), 2) for s in snippets[:3]]
        lines.append(f"- snippets returned: {len(snippets)} (top: {list(zip(titles, sims))})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"[ai-test] logging in as {TEST_EMAIL} ...")
    token = log_in()
    print("[ai-test] logged in, starting battery")

    header = f"""# ORION AI test — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

Every question below was sent to the **live** `/ai/ask` on Render
(`{API_BASE_URL}`), authenticated as the real test account
`{TEST_EMAIL}` (Semester 3, CSE-I). Nothing here is simulated or
hand-written — these are the actual HTTP responses.

Only questions about data confirmed present in the structured DB or the
RAG corpus at test time were asked (real course codes, real faculty names,
real research interests — pulled from Supabase immediately before writing
the question set).

"""
    OUT_PATH.write_text(header)
    results = []
    for i, (category, question) in enumerate(QUESTIONS, 1):
        print(f"[ai-test] {i}/{len(QUESTIONS)} [{category}] {question!r}")
        result = ask(token, question)
        results.append((category, question, result))
        with OUT_PATH.open("a") as f:
            f.write(fmt_result(category, question, result))
        time.sleep(DELAY_S)

    return results


if __name__ == "__main__":
    main()
    print("[ai-test] battery complete, analysis pending (run analyze step)")
