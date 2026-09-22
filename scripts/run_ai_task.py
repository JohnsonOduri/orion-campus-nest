"""Run every question in AI-task.md through ORION's real answer pipeline.

Signs in as the pre-existing test student (orion-test-student-a, Semester 3,
CSE section I — scripts/create_test_students.py), builds the same
request-scoped Supabase client the API uses (RLS applies), and calls
`backend/app/api/ai.answer()` — the exact function behind POST /ai/ask —
without creating stored conversations. Follow-ups (`>>` lines) get the
previous turns as history, like a real chat.

Writes AI-task-results.md. Flags answers that look like misses so they can
be reviewed; it does not judge correctness by itself.

Usage:
  .venv/bin/python scripts/run_ai_task.py            # composer only (no Gemini)
  .venv/bin/python scripts/run_ai_task.py --llm      # allow Gemini rewording
  .venv/bin/python scripts/run_ai_task.py --only 7   # one section
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TEST_EMAIL = "orion-test-student-a@iiitkottayam.ac.in"
TEST_PASSWORD = "OrionTest#2026a"  # pre-existing test account (scripts/create_test_students.py)

MISS_MARKERS = [
    "I couldn't find", "I'm not sure what you mean", "couldn't find that", "temporarily unavailable",
    "doesn't list", "I don't have",
]


def parse_questions(path: Path) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(section, [(question, expectation)])]; a `>>` line is chained to the
    previous question as a follow-up (stored as a list of turns)."""
    sections: list[tuple[str, list]] = []
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
            continue
        m = re.match(r"^(-|>>)\s+(.*?)(?:\s+→\s+(.*))?$", line.rstrip())
        if not m or not sections:
            continue
        kind, question, expect = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
        items = sections[-1][1]
        if kind == ">>" and items:
            items[-1].append((question, expect))
        else:
            items.append([(question, expect)])
    return sections


def sign_in() -> str:
    import requests
    from dotenv import dotenv_values

    env = dotenv_values(ROOT / ".env")
    url = env.get("SUPABASE_URL") or env.get("VITE_SUPABASE_URL")
    anon = env.get("SUPABASE_ANON_KEY") or env.get("VITE_SUPABASE_ANON_KEY") or env.get("SUPABASE_PUBLIC_ANON_KEY")
    resp = requests.post(f"{url}/auth/v1/token?grant_type=password",
                         json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                         headers={"apikey": anon}, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="allow Gemini rewording of document answers")
    parser.add_argument("--only", type=int, help="run only section N")
    parser.add_argument("--out", default=str(ROOT / "AI-task-results.md"))
    args = parser.parse_args()
    os.environ["ORION_LLM_MODE"] = "auto" if args.llm else "off"

    from app.api.ai import answer
    from app.services.supabase_clients import get_request_scoped_client

    client = get_request_scoped_client(sign_in())
    sections = parse_questions(ROOT / "AI-task.md")

    out: list[str] = [
        f"# ORION AI-task results — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Signed in as `{TEST_EMAIL}` (Semester 3, CSE section I). Answers come from "
        f"`backend/app/api/ai.answer()`, the function behind `POST /ai/ask`. "
        f"LLM rewording: **{'on' if args.llm else 'off'}**.",
        "",
    ]
    total = flagged = errors = 0
    latencies: list[float] = []
    for i, (section, chains) in enumerate(sections, start=1):
        if args.only and i != args.only:
            continue
        if not chains or section.startswith("Ground rules") or not re.match(r"\d+\.", section):
            continue
        out += [f"## {section}", ""]
        for chain in chains:
            history: list[dict[str, str]] = []
            for turn, (question, expect) in enumerate(chain):
                total += 1
                start = time.perf_counter()
                try:
                    r = answer(client, question, history)
                    err = None
                except Exception as exc:  # noqa: BLE001 - record and continue
                    r, err = {}, f"{exc.__class__.__name__}: {exc}"
                    errors += 1
                ms = (time.perf_counter() - start) * 1000
                latencies.append(ms)
                text = (r.get("answer") or "").strip()
                miss = err or any(mark in text for mark in MISS_MARKERS)
                flagged += bool(miss)
                prefix = "↳ " if turn else ""
                out.append(f"### {prefix}{question}")
                meta = f"`{r.get('route', '?')}` · `{r.get('intent', '?')}` · {ms:.0f} ms · {r.get('answer_source', '-')}"
                if r.get("resolved_query"):
                    meta += f" · resolved as “{r['resolved_query']}”"
                if miss:
                    meta += " · ⚠️ review"
                out.append(meta)
                if expect:
                    out.append(f"*Expected:* {expect}")
                out.append("")
                out.append(f"ERROR: {err}" if err else text)
                out.append("")
                history += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
                print(f"{'!' if miss else '.'} {ms:6.0f}ms  {question[:70]}", flush=True)

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0
    summary = (f"**{total} questions** · {errors} errors · {flagged} flagged for review · "
               f"median {p50:.0f} ms · p95 {p95:.0f} ms")
    out.insert(4, summary)
    out.insert(5, "")
    Path(args.out).write_text("\n".join(out) + "\n")
    print(summary)


if __name__ == "__main__":
    main()
