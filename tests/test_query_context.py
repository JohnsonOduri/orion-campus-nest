"""Pure, offline tests for backend/query/context.py.

The one property that matters most here (AGENTS.md §6): has_answer must be
False whenever there are no facts and no snippets, and a warning must always
explain why — never a silent empty context that could be mistaken for "I
checked and there's nothing."
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query.context import build_context  # noqa: E402
from backend.query.router import classify  # noqa: E402
from backend.query.types import (  # noqa: E402
    RetrievalResult,
    SemanticSnippet,
    StructuredFact,
)


def test_empty_result_has_no_answer_and_carries_a_reason():
    plan = classify("What is my next class?")
    result = RetrievalResult(plan=plan)
    ctx = build_context(result)
    assert ctx.has_answer is False
    assert ctx.warnings, "an empty context must explain why, never fail silently"


def test_facts_alone_yield_an_answer():
    plan = classify("What is my next class?")
    fact = StructuredFact(claim="Next class: ICS 211 09:00-09:55", data={}, source="orion_next_class RPC")
    ctx = build_context(RetrievalResult(plan=plan, facts=[fact]))
    assert ctx.has_answer is True
    assert ctx.facts[0].source == "orion_next_class RPC"


def test_snippets_alone_yield_an_answer():
    plan = classify("What are the attendance requirements?")
    snippet = SemanticSnippet(
        content="R.6.1 Students should have a minimum of 80% attendance",
        document_title="UG Regulations (2026 admission onwards)",
        section_title="R.6.0 Attendance",
        page_start=10,
        page_end=10,
        similarity=0.58,
        cohort="ADM2026",
        category=None,
        document_type="regulations",
        valid_from=None,
        valid_until=None,
    )
    ctx = build_context(RetrievalResult(plan=plan, snippets=[snippet]))
    assert ctx.has_answer is True
    assert ctx.snippets[0].document_title.startswith("UG Regulations")


def test_existing_warnings_are_preserved_not_duplicated():
    plan = classify("Which faculty work in quantum foo and when can I meet them?")
    result = RetrievalResult(plan=plan, warnings=["no faculty research_interests matched"])
    ctx = build_context(result)
    assert ctx.has_answer is False
    assert ctx.warnings == ["no faculty research_interests matched"]


def test_grounded_context_to_dict_round_trips_key_fields():
    plan = classify("What is my next class?")
    fact = StructuredFact(claim="x", data={"a": 1}, source="s", source_id="sid")
    ctx = build_context(RetrievalResult(plan=plan, facts=[fact]))
    d = ctx.to_dict()
    assert d["has_answer"] is True
    assert d["facts"][0]["source_id"] == "sid"
    assert d["route"] == "structured"
