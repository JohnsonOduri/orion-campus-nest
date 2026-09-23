"""Offline tests for backend/app/api/ai.py — the /ai/ask answer pipeline.

Contract since 2026-09-22 (AI-task.md): every question gets an answer
written from retrieved data (backend/query/compose.py). Gemini is optional:
it may only reword a document passage, and any failure — timeout, quota,
network, missing key — falls back to the quoted passage without raising.

Calls the functions directly (auth, Supabase and retrieval are faked) like
tests/test_query_service.py, so no network or real session is needed.
"""

from __future__ import annotations

import socket
import ssl
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.api import ai  # noqa: E402
from app.schemas import AskRequest  # noqa: E402
from query import llm_client  # noqa: E402
from query.types import GroundedContext, QueryPlan, RouteType, SemanticSnippet, StructuredFact, StructuredIntent  # noqa: E402


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Chainable stand-in for supabase-py's query builder (only .execute().data matters)."""

    def __init__(self, data, log=None, table=None):
        self._data, self._log, self._table = data, log, table

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def insert(self, row):
        if self._log is not None:
            self._log.append((self._table, row))
        rows = row if isinstance(row, list) else [row]
        self._data = [{"id": "conv-1", **r} for r in rows]
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeClient:
    def __init__(self):
        self.inserts: list = []

    def table(self, name):
        return _FakeQuery([{"id": "conv-1"}] if name == "ai_conversations" else [], self.inserts, name)

    def rpc(self, *_a, **_k):
        return _FakeQuery(None)


SNIPPET = SemanticSnippet(
    content="R.5.1 Students are expected to attend all the classes. Students should have minimum 80% attendance.",
    document_title="UG Regulations (2021-25 batch)", section_title="R.5.0 Attendance", page_start=7, page_end=7,
    similarity=1.2, cohort="21-25", category=None, document_type="regulations", valid_from=None, valid_until=None,
)


def _semantic_context(query: str) -> GroundedContext:
    plan = QueryPlan(raw_query=query, route=RouteType.SEMANTIC, topic_text=query)
    return GroundedContext(query=query, route=RouteType.SEMANTIC, facts=[], snippets=[SNIPPET], warnings=[],
                           has_answer=True, plan=plan)


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(ai.campus, "student_context", lambda client, key=None: {"semester": 3, "cohort": "2021_2025"})
    monkeypatch.setattr(ai.query_service, "answer_query", lambda client, query, **kw: _semantic_context(query))
    monkeypatch.setattr(llm_client, "llm_available", lambda: True)


@pytest.mark.parametrize(
    "exc",
    [
        llm_client.LLMUnavailable("HTTP 429"),
        llm_client.LLMUnavailable("TimeoutError"),
        llm_client.LLMUnavailable("model found no answer in the passage"),
    ],
)
def test_llm_failure_falls_back_to_the_quoted_rule(monkeypatch, patched, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(llm_client, "rephrase_passage", boom)
    result = ai.answer(_FakeClient(), "What is the attendance requirement?")
    assert result["answer_source"] == "composer"
    assert "80% attendance" in result["answer"]
    assert "UG Regulations (2021-25 batch)" in result["answer"]


@pytest.mark.parametrize(
    "exc",
    [TimeoutError("read timed out"), socket.timeout("timed out"), urllib.error.URLError("unreachable"),
     ssl.SSLError("bad handshake"), ConnectionResetError("reset"), OSError("network unreachable")],
)
def test_rephrase_converts_every_network_failure_and_trips_the_breaker(monkeypatch, exc):
    """The live bug from AI-test.md: a bare TimeoutError escaped and 500'd."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ORION_LLM_MODE", "auto")
    monkeypatch.setattr(llm_client, "_breaker_open_until", 0.0)

    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", boom)
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.rephrase_passage("q", "passage", "Doc")
    assert llm_client.llm_available() is False  # later requests skip Gemini entirely


def test_quota_exhaustion_opens_the_breaker_for_longer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client, "_breaker_open_until", 0.0)

    def quota(*a, **k):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", quota)
    now = llm_client._time.monotonic()
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.rephrase_passage("q", "passage", "Doc")
    assert llm_client._breaker_open_until - now >= 1700


def test_llm_off_never_calls_gemini(monkeypatch, patched):
    monkeypatch.setattr(llm_client, "llm_available", lambda: False)

    def must_not_run(*a, **k):  # pragma: no cover
        raise AssertionError("Gemini must not be called when disabled")

    monkeypatch.setattr(llm_client, "rephrase_passage", must_not_run)
    result = ai.answer(_FakeClient(), "What is the attendance requirement?")
    assert result["answer_source"] == "composer" and result["answer"]


def test_successful_rephrase_keeps_the_quote_and_source(monkeypatch, patched):
    monkeypatch.setattr(llm_client, "rephrase_passage", lambda *a, **k: "You need at least 80% attendance.")
    result = ai.answer(_FakeClient(), "What is the attendance requirement?")
    assert result["answer_source"] == "llm"
    assert result["answer"].startswith("You need at least 80% attendance.")
    assert "> R.5.1" in result["answer"]  # the verbatim rule is still shown
    assert "*Source:" in result["answer"]


def test_small_talk_never_calls_the_llm(monkeypatch):
    monkeypatch.setattr(ai.campus, "student_context", lambda client, key=None: None)

    def must_not_run(*a, **k):  # pragma: no cover
        raise AssertionError("small talk must not call Gemini")

    monkeypatch.setattr(llm_client, "rephrase_passage", must_not_run)
    result = ai.answer(None, "hi")
    assert result["route"] == "small_talk" and result["answer"]


def test_structured_answers_are_composed_without_an_llm(monkeypatch):
    monkeypatch.setattr(ai.campus, "student_context", lambda client, key=None: None)
    ctx = GroundedContext(
        query="What is my next class?", route=RouteType.STRUCTURED,
        facts=[StructuredFact(claim="Next class", source="t", data={
            "_role": "next", "_when": "tomorrow (Wednesday)", "_gap": "", "course_code": "ICS 214",
            "course_name": "IT WORKSHOP III", "start_time": "10:00:00", "end_time": "10:55:00",
            "faculty_names": ["Dr. Deepak Jose"], "entry_type": "lab"})],
        snippets=[], warnings=[], has_answer=True,
        plan=QueryPlan(raw_query="What is my next class?", route=RouteType.STRUCTURED,
                       structured_intent=StructuredIntent.NEXT_CLASS),
    )
    monkeypatch.setattr(ai.query_service, "answer_query", lambda client, query, **kw: ctx)
    monkeypatch.setattr(llm_client, "rephrase_passage", lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    result = ai.answer(_FakeClient(), "What is my next class?")
    assert "**IT Workshop III (ICS 214)**" in result["answer"]
    assert "10:00–10:55 AM" in result["answer"] and "Dr. Deepak Jose" in result["answer"]


def test_ask_persists_both_turns_and_returns_the_conversation(monkeypatch, patched):
    client = _FakeClient()
    monkeypatch.setattr(ai, "get_current_client", lambda request: client)
    monkeypatch.setattr(ai.ASK_LIMITER, "check_request", lambda request: None)
    monkeypatch.setattr(llm_client, "llm_available", lambda: False)
    request = SimpleNamespace(cookies={"orion_access_token": "session-token"})
    result = ai.ask(AskRequest(query="What is the attendance requirement?"), request=request)
    assert result["conversation_id"] == "conv-1"
    rows = [r for t, r in client.inserts if t == "ai_messages"]
    assert len(rows) == 1 and [m["role"] for m in rows[0]] == ["user", "assistant"]
