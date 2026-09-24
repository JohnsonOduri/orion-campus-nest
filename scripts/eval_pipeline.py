"""Stage-attributed evaluation of the ORION answer pipeline.

`scripts/run_ai_task.py` runs a broad question bank and flags answers that
*look* like misses. This is the complement: a smaller set of cases, each
with an explicit expectation per pipeline stage, so a failure names the
stage that caused it instead of leaving that to be guessed from the reply.

    ROUTER            wrong route/intent for the question
    ENTITY_RESOLUTION the right intent, but the name/course wasn't resolved
    DATE_RESOLUTION   the query resolved to the wrong date
    RETRIEVAL         right plan and date, but nothing came back
    ANSWER_GROUNDING  answered from the wrong source, or asserted something
                      the retrieved evidence doesn't support (the classic
                      case: an unrelated document quoted as if it answered)
    DATA_MISSING      ORION correctly has no data and correctly says so

Usage:
    .venv/bin/python scripts/eval_pipeline.py
    .venv/bin/python scripts/eval_pipeline.py --verbose
    .venv/bin/python scripts/eval_pipeline.py --only mess

Exit code 0 only when every case passes.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from query import tempo  # noqa: E402

TODAY = tempo.today_ist()
TOMORROW = TODAY + timedelta(days=1)


@dataclass
class Case:
    """One question plus what each stage should have decided.

    Only the expectations that are set are checked, so a case can pin down
    exactly the stage it is about (a routing case need not assert on the
    answer text, and vice versa).
    """

    group: str
    query: str
    intent: Optional[str] = None
    # An intent from this set is acceptable — for questions where more than
    # one routing is genuinely defensible.
    intent_in: Optional[set[str]] = None
    date: Optional[str] = None
    source: Optional[str] = None  # structured | documents | none
    # Substrings that must / must not appear in the answer (case-insensitive).
    expect: list[str] = field(default_factory=list)
    reject: list[str] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)
    note: str = ""


def cases() -> list[Case]:
    iso = lambda d: d.isoformat()  # noqa: E731
    return [
        # --- A. Faculty -----------------------------------------------------
        Case("faculty", "Where is Dr. Anisth S cabin?", intent="faculty_lookup", source="structured",
             reject=["ragging", "curriculum"],
             note="live bug: routed to document search, answered with an anti-ragging memo"),
        Case("faculty", "Where is Dr Anisth?", intent="faculty_lookup", source="structured",
             reject=["ragging"]),
        Case("faculty", "Where is Anisth's office?", intent="faculty_lookup", source="structured",
             reject=["ragging"]),
        Case("faculty", "Tell me about Dr. Anisth S", intent="faculty_lookup", source="structured"),
        Case("faculty", "What is Dr. Manu Madhavan's email?", intent="faculty_lookup",
             source="structured", expect=["manum@iiitkottayam.ac.in"]),
        Case("faculty", "Where is Dr. Manu Madhavan's cabin?", intent="faculty_lookup",
             source="structured", expect=["BC 307"]),
        Case("faculty", "Where is the cabin of Dr. Zzzz Nonexistent?", intent="faculty_lookup",
             reject=["ragging", "curriculum"], expect=["couldn't find"],
             note="no such person: must say so, never fall through to document search"),

        # --- B. Mess --------------------------------------------------------
        Case("mess", "What's for breakfast today?", intent="mess_today", date=iso(TODAY),
             source="structured", expect=["breakfast"]),
        Case("mess", "What's for lunch today?", intent="mess_today", date=iso(TODAY),
             source="structured", expect=["lunch"]),
        Case("mess", "What's for dinner tomorrow?", intent="mess_on_day", date=iso(TOMORROW),
             source="structured", expect=["dinner"]),
        Case("mess", "Tomorrow's breakfast?", intent="mess_on_day", date=iso(TOMORROW),
             source="structured", expect=["breakfast"],
             note="live bug: answered with today's menu"),
        Case("mess", "tomorrow?", intent="mess_on_day", date=iso(TOMORROW), source="structured",
             expect=["lunch"], history=[("user", "What's for lunch today?")],
             note="live bug: became an unsupported query"),
        Case("mess", "What about dinner?", intent="mess_on_day", date=iso(TOMORROW),
             source="structured", expect=["dinner"],
             history=[("user", "What's for lunch tomorrow?")],
             note="meal changes, the day the conversation is on must stay"),
        Case("mess", "what about the next day?", intent="mess_on_day", date=iso(TOMORROW),
             source="structured", history=[("user", "What's for lunch today?")]),

        # --- C. Timetable / free periods ------------------------------------
        Case("timetable", "What is my next class?", intent="next_class", source="structured"),
        Case("timetable", "What classes do I have tomorrow?", intent="day_of_week_timetable",
             date=iso(TOMORROW), source="structured"),
        Case("timetable", "Do I have a free period tomorrow?", intent="free_time",
             date=iso(TOMORROW), source="structured", reject=["curriculum"]),
        Case("timetable", "Is there any free class tomorrow?", intent="free_time",
             date=iso(TOMORROW), source="structured", reject=["curriculum", "syllabus"],
             note="live bug: answered with curriculum text"),
        Case("timetable", "Is there any Free lectures?", intent="free_time", date=iso(TODAY),
             source="structured", reject=["curriculum", "Synthesis Lectures"],
             note="live bug: answered with curriculum text containing the word 'Lectures'"),
        Case("timetable", "When is my next free period?", intent="free_time", source="structured"),
        Case("timetable", "what about Friday?", intent="day_of_week_timetable", source="structured",
             history=[("user", "What is my next class?")],
             note="follow-up whose slot does not exist in the previous sentence"),

        # --- C2. Pronouns, misspellings, ambiguity, mixed domains ------------
        Case("context", "Where is his cabin?", intent="faculty_lookup", source="structured",
             expect=["BC 307"], history=[("user", "Tell me about Dr. Manu Madhavan")],
             note="pronoun refers to the faculty member from the previous turn"),
        Case("context", "What does he research?", intent_in={"faculty_lookup", "faculty_research"},
             source="structured", history=[("user", "What is Dr. Manu Madhavan's email?")]),
        Case("context", "Who teaches it?", intent="faculty_for_course", source="structured",
             history=[("user", "Tell me about ICS 213")]),
        Case("robustness", "Where is Dr. Manu Madhvan's office?", intent="faculty_lookup",
             source="structured", expect=["BC 307"],
             note="misspelled surname must still resolve (fuzzy entity resolution)"),
        Case("robustness", "whats for lunch tomorow", intent="mess_on_day", date=iso(TOMORROW),
             source="structured", expect=["lunch"],
             note="no apostrophe, no question mark, misspelled 'tomorrow'"),
        Case("robustness", "free period on monday?", intent="free_time", source="structured",
             reject=["curriculum"]),

        # --- C3. Faculty research topics ------------------------------------
        Case("research", "Which faculty work on natural language processing?",
             intent="faculty_research", source="structured", expect=["Natural Language Processing"]),
        Case("research", "Who researches computer vision on campus?", intent="faculty_research",
             source="structured", expect=["Computer Vision"],
             note="live: the locative tail 'on campus' was searched literally and matched nobody"),
        Case("research", "Who works on cryptography and network security?", intent="faculty_research",
             source="structured", expect=["Cryptography"],
             note="live: a compound topic had to match ONE interest phrase, so it matched nobody"),
        Case("research", "Recommend someone for quantum computing.", intent="faculty_research",
             source="structured", expect=["Quantum Computing"],
             note="live: 'recommend someone' (no 'faculty' word) never reached the research route"),
        Case("research", "Which faculty specialise in cooking recipes?", intent="faculty_research",
             expect=["couldn't find"], reject=["french", "german"],
             note="no such research area: must say so, not surface language teachers"),
        Case("research", "Is anyone researching medieval history?", intent="faculty_research",
             expect=["couldn't find"]),

        # --- D. Documents (genuinely need retrieval) -------------------------
        Case("documents", "What is the attendance requirement?", source="documents",
             expect=["80%"]),
        Case("documents", "What are the hostel curfew rules?", source="documents",
             expect=["11:00 PM"]),
        Case("documents", "How do I report ragging?", source="documents"),
        Case("documents", "What is the transcript verification fee?", source="documents"),

        # --- E. No data / out of scope --------------------------------------
        Case("unsupported", "What is my CGPA?", intent="out_of_scope",
             expect=["don't store"], reject=["curriculum"]),
        Case("unsupported", "Who won the cricket match yesterday?", source="none",
             reject=["*source:"],
             note="must not answer from campus documents — no citation means nothing was quoted"),
        Case("unsupported", "What is the price of a laptop on campus?",
             reject=["Synthesis Lectures"],
             note="no such data: must not quote an unrelated passage"),
    ]


# --------------------------------------------------------------- evaluation

def classify_failure(case: Case, trace: dict, answer: str) -> Optional[str]:
    """The first stage whose expectation this case failed, or None."""
    intent = trace.get("intent")
    if case.intent and intent != case.intent:
        return "ROUTER"
    if case.intent_in and intent not in case.intent_in:
        return "ROUTER"
    if case.date and trace.get("resolved_date") != case.date:
        return "DATE_RESOLUTION"
    if case.source and trace.get("source") != case.source:
        # Right plan, nothing came back -> retrieval; answered from the
        # wrong kind of source entirely -> grounding.
        if trace.get("source") == "none":
            return "RETRIEVAL"
        return "ANSWER_GROUNDING"
    low = (answer or "").lower()
    for needle in case.expect:
        if needle.lower() not in low:
            # A faculty question that routed correctly but produced no name
            # is an entity-resolution failure, not a grounding one.
            if case.group == "faculty" and trace.get("facts") == 0:
                return "ENTITY_RESOLUTION"
            return "ANSWER_GROUNDING"
    for needle in case.reject:
        if needle.lower() in low:
            return "ANSWER_GROUNDING"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run one group (faculty/mess/timetable/documents/unsupported)")
    parser.add_argument("--verbose", action="store_true", help="print every answer, not just failures")
    args = parser.parse_args()

    import os

    os.environ["ORION_DEBUG_TRACE"] = "1"  # the trace is the point of this script
    from run_ai_task import sign_in  # noqa: PLC0415
    from app.services.supabase_clients import get_request_scoped_client  # noqa: PLC0415
    from app.api.ai import answer as answer_fn  # noqa: PLC0415

    client = get_request_scoped_client(sign_in())
    selected = [c for c in cases() if not args.only or c.group == args.only]

    failures: dict[str, list[str]] = {}
    passed = 0
    for case in selected:
        history = [{"role": r, "content": c} for r, c in case.history]
        try:
            result = answer_fn(client, case.query, history)
        except Exception as exc:  # noqa: BLE001 - a crash is itself a result
            failures.setdefault("PIPELINE_ERROR", []).append(f"{case.query} -> {exc.__class__.__name__}: {exc}")
            print(f"FAIL  PIPELINE_ERROR  {case.query}")
            continue
        trace = result.get("trace") or {}
        text = result.get("answer") or ""
        category = classify_failure(case, trace, text)
        if category is None:
            passed += 1
            print(f"PASS  {case.group:11} {case.query}")
            if args.verbose:
                print(f"      intent={trace.get('intent')} date={trace.get('resolved_date')} "
                      f"source={trace.get('source')}\n      {text[:160]}")
        else:
            failures.setdefault(category, []).append(case.query)
            print(f"FAIL  {category:17} {case.query}")
            print(f"      expected intent={case.intent} date={case.date} source={case.source}")
            print(f"      got      intent={trace.get('intent')} date={trace.get('resolved_date')} "
                  f"source={trace.get('source')}")
            print(f"      answer: {text[:200]}")
            if case.note:
                print(f"      note: {case.note}")

    total = len(selected)
    print(f"\n{passed}/{total} passed")
    for category, queries in sorted(failures.items()):
        print(f"  {category}: {len(queries)}")
        for q in queries:
            print(f"    - {q}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
