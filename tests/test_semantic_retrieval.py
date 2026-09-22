"""Offline tests for the Gemini-backed retrieval paths in
backend/query/retrieval.py and their routing through service.answer_query.

Embeddings are mocked at backend.query.embeddings.embed_query; Supabase is a
recording fake. Expiry/validity filtering itself lives in SQL
(match_document_chunks_gemini) and is verified against the live database —
see docs/embeddings.md §Verification — these tests pin what the Python
side sends to it and how it degrades when it fails.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import embeddings, retrieval  # noqa: E402
from backend.query.service import answer_query  # noqa: E402
from backend.query.types import RouteType  # noqa: E402

DIM = embeddings.EMBEDDING_DIM


class _Query:
    """Chainable stand-in for a PostgREST request builder."""

    def __init__(self, fake, name, params=None):
        self.fake, self.name, self.params = fake, name, params

    def __getattr__(self, _attr):
        # select/eq/order/not_/is_/... all just chain
        return lambda *a, **k: self

    @property
    def not_(self):
        return self

    def execute(self):
        outcome = self.fake.responses.get(self.name, [])
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(data=outcome, count=None)


class FakeSupabase:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.rpc_calls: list[tuple[str, dict]] = []
        self.tables: list[str] = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _Query(self, name, params)

    def table(self, name):
        self.tables.append(name)
        return _Query(self, name)


class EmbedSpy:
    def __init__(self, result=None, exc=None):
        self.calls: list[tuple[str, dict]] = []
        self.result, self.exc = result, exc

    def __call__(self, text, **kwargs):
        self.calls.append((text, kwargs))
        if self.exc:
            raise self.exc
        return self.result or [0.01] * DIM


@pytest.fixture
def spy(monkeypatch):
    s = EmbedSpy()
    monkeypatch.setattr(embeddings, "embed_query", s)
    monkeypatch.delenv("ORION_EMBEDDING_PROVIDER", raising=False)
    return s


CHUNK = {
    "chunk_id": 1,
    "document_id": 10,
    "title": "UG Regulations 2026",
    "section_title": "Attendance",
    "content": "A student must have at least 75% attendance ...",
    "page_start": 12,
    "page_end": 12,
    "similarity": 0.81,
    "cohort": "UG26",
    "category": "regulation",
    "document_type": "regulation",
    "valid_from": "2026-07-01",
    "valid_until": None,
}


# --------------------------------------------------------------- semantic path


def test_semantic_search_embeds_once_and_calls_gemini_rpc(spy):
    sb = FakeSupabase({"match_document_chunks_gemini": [CHUNK]})
    res = retrieval.semantic_search(sb, "What is the attendance requirement?", top_k=4, cohort="UG26")

    assert len(spy.calls) == 1
    assert [name for name, _ in sb.rpc_calls] == ["match_document_chunks_gemini"]
    params = sb.rpc_calls[0][1]
    assert len(params["query_embedding"]) == DIM
    assert params["match_count"] == 4 and params["filter_cohort"] == "UG26"
    # no as_of override: the SQL default (current_date) evaluates validity
    assert "as_of" not in params
    s = res.snippets[0]
    assert (s.document_title, s.section_title, s.page_start, s.cohort) == ("UG Regulations 2026", "Attendance", 12, "UG26")
    assert res.warnings == []


# 2026-09-22: the answer path uses Postgres full-text search
# (search_document_chunks) — no embedding call, no Gemini quota. The vector
# functions above stay as an optional path and keep their own tests.
LEXICAL = {**CHUNK, "rank": 1.2, "chunk_index": 3}


def test_semantic_route_uses_lexical_search_and_never_embeds(spy):
    sb = FakeSupabase({"search_document_chunks": [LEXICAL]})
    ctx = answer_query(sb, "What is the attendance requirement?", profile={"semester": 3, "cohort": "2021_2025"})
    assert ctx.route == RouteType.SEMANTIC
    assert spy.calls == []
    names = [n for n, _ in sb.rpc_calls]
    assert names and set(names) == {"search_document_chunks"}
    # cohort isolation: the student's regulation family is sent to SQL
    assert all(params["cohort_family"] == "21-25" for _, params in sb.rpc_calls)
    assert ctx.has_answer


def test_no_matches_is_an_honest_no_answer(spy):
    ctx = answer_query(FakeSupabase({"search_document_chunks": []}), "What is the attendance requirement?")
    assert ctx.has_answer is False
    assert any("no document passages matched" in w for w in ctx.warnings)


# ------------------------------------------------------------- structured path


def test_structured_query_never_embeds(spy, monkeypatch):
    def boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("structured query must not call Gemini embeddings")

    monkeypatch.setattr(embeddings, "embed_query", boom)
    monkeypatch.setattr(embeddings, "embed_documents", boom)
    sb = FakeSupabase({"orion_day_timetable": [{"course_code": "CS301", "course_name": "OS", "start_time": "09:30", "end_time": "10:25"}]})
    ctx = answer_query(sb, "What classes do I have today?")
    assert ctx.route == RouteType.STRUCTURED
    assert [n for n, _ in sb.rpc_calls] == ["orion_day_timetable"]
    assert ctx.has_answer


# ----------------------------------------------------------------- hybrid path


def test_hybrid_faculty_matches_research_text_and_schedule_without_embeddings(spy):
    fac = [
        {"id": 7, "full_name": "Dr. A", "initials": "AA", "designation": "Assistant Professor", "email": "a@x",
         "office_location": None, "office_hours": None, "status": "active",
         "research_interests": "Natural Language Processing; Machine Learning"},
        {"id": 8, "full_name": "Dr. B", "initials": "BB", "designation": "Assistant Professor", "email": "b@x",
         "office_location": None, "office_hours": None, "status": "active",
         "research_interests": "VLSI Design; Embedded Systems"},
    ]
    sched = [{"timetable_entries": {"day_of_week": 2, "start_time": "10:30", "end_time": "11:25", "status": "active",
                                    "courses": {"course_code": "CS401"}}}]
    sb = FakeSupabase({"faculty": fac, "timetable_entry_faculty": sched})
    ctx = answer_query(sb, "Which faculty work on NLP and when can I meet them?")

    assert ctx.route == RouteType.HYBRID
    assert spy.calls == []  # no Gemini call
    assert [f.data["faculty"]["full_name"] for f in ctx.facts] == ["Dr. A"]
    assert ctx.facts[0].data["teaching_slots"][0]["course_code"] == "CS401"
    # office hours are never invented
    assert ctx.facts[0].data["faculty"]["office_hours"] is None


def test_hybrid_drops_rows_below_threshold(spy):
    fac = {"id": 1, "full_name": "X", "initials": "X", "email": None, "office_location": None,
           "office_hours": None, "research_interests": "y", "similarity": 0.1}
    res = retrieval.faculty_topic_and_schedule(FakeSupabase({"match_faculty_research": [fac]}), "NLP")
    assert res.facts == []


# ------------------------------------------------------------ graceful failure


@pytest.mark.parametrize(
    "exc",
    [
        embeddings.EmbeddingNotConfigured("GEMINI_API_KEY is not set"),
        embeddings.EmbeddingUnavailable("429 after retries"),
        embeddings.EmbeddingResponseError("expected 768"),
    ],
)
def test_answers_do_not_depend_on_gemini_embeddings(monkeypatch, exc):
    """Gemini being down or out of quota changes nothing on the answer path."""
    monkeypatch.setattr(embeddings, "embed_query", EmbedSpy(exc=exc))
    sb = FakeSupabase({"search_document_chunks": [LEXICAL]})
    ctx = answer_query(sb, "What is the attendance requirement?")
    assert ctx.has_answer is True
    assert not any("temporarily unavailable" in w for w in ctx.warnings)


def test_rpc_failure_degrades_to_warning(spy):
    err = APIError({"message": "function does not exist", "code": "42883"})
    ctx = answer_query(FakeSupabase({"search_document_chunks": err}), "What is the attendance requirement?")
    assert ctx.has_answer is False
    assert any("temporarily unavailable" in w for w in ctx.warnings)
    # internals are not echoed to the user
    assert not any("42883" in w for w in ctx.warnings)


def test_programming_errors_still_surface(monkeypatch):
    monkeypatch.setattr(embeddings, "embed_query", EmbedSpy(exc=KeyError("bug")))
    with pytest.raises(KeyError):
        retrieval.semantic_search(FakeSupabase(), "q")


# -------------------------------------------------------------------- rollback


def test_minilm_rollback_switch_uses_legacy_rpc(monkeypatch):
    monkeypatch.setenv("ORION_EMBEDDING_PROVIDER", "minilm")
    monkeypatch.setattr(retrieval, "_legacy_minilm_embed", lambda text: [0.02] * 384)
    monkeypatch.setattr(embeddings, "embed_query", EmbedSpy(exc=AssertionError("gemini must not be called")))
    sb = FakeSupabase({"match_document_chunks": [CHUNK]})
    res = retrieval.semantic_search(sb, "attendance")
    assert sb.rpc_calls[0][0] == "match_document_chunks"
    assert len(sb.rpc_calls[0][1]["query_embedding"]) == 384
    assert res.snippets


def test_minilm_rollback_restores_legacy_faculty_search(monkeypatch):
    np = pytest.importorskip("numpy")  # only present with the rollback requirements

    monkeypatch.setenv("ORION_EMBEDDING_PROVIDER", "minilm")
    monkeypatch.setattr(embeddings, "embed_query", EmbedSpy(exc=AssertionError("gemini must not be called")))

    class FakeMiniLM:
        def encode(self, texts, normalize_embeddings=True):
            return np.array([[1.0, 0.0] if "language" in t.lower() or t == "NLP" else [0.0, 1.0] for t in texts])

    monkeypatch.setattr(retrieval, "_LEGACY_MINILM_MODEL", FakeMiniLM())
    fac = [
        {"id": 1, "full_name": "Dr. NLP", "initials": "DN", "email": None, "office_location": None,
         "office_hours": None, "research_interests": "Natural Language Processing"},
        {"id": 2, "full_name": "Dr. VLSI", "initials": "DV", "email": None, "office_location": None,
         "office_hours": None, "research_interests": "VLSI"},
    ]
    sb = FakeSupabase({"faculty": fac, "timetable_entry_faculty": []})
    res = retrieval.faculty_topic_and_schedule(sb, "NLP")
    assert [f.data["faculty"]["full_name"] for f in res.facts] == ["Dr. NLP"]
    assert sb.rpc_calls == []
