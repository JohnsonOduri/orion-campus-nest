"""Typed contracts for the ORION query router / retrieval / context layer.

This module has no side effects and no Supabase/embedding dependency —
router.py produces these types, retrieval.py fills them, context.py
consumes them. Keeping them here lets each stage be tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class RouteType(str, Enum):
    """AGENTS.md §4 / README §8: the router must not send every question to
    vector search — classify first, then pick the source of truth."""

    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    SMALL_TALK = "small_talk"
    UNSUPPORTED = "unsupported"


class StructuredIntent(str, Enum):
    NEXT_CLASS = "next_class"
    DAY_TIMETABLE = "day_timetable"
    WEEK_TIMETABLE = "week_timetable"
    DAY_OF_WEEK_TIMETABLE = "day_of_week_timetable"
    CLASS_AT_TIME = "class_at_time"
    FACULTY_FOR_COURSE = "faculty_for_course"
    COURSE_INFO = "course_info"
    FACULTY_LOOKUP = "faculty_lookup"
    MESS_TODAY = "mess_today"
    MESS_WEEK = "mess_week"
    MESS_ON_DAY = "mess_on_day"
    # Added 2026-09-22 (AI-task.md): data that was in Supabase but that the
    # assistant had no way to reach.
    ACADEMIC_CALENDAR = "academic_calendar"
    EXAM_SCHEDULE = "exam_schedule"
    ANNOUNCEMENTS = "announcements"
    HOSTEL_WARDENS = "hostel_wardens"
    FACULTY_ROLE = "faculty_role"
    FACULTY_RESEARCH = "faculty_research"
    MY_COURSES = "my_courses"
    MY_PROFILE = "my_profile"
    CLASSROOM = "classroom"
    FREE_TIME = "free_time"
    OUT_OF_SCOPE = "out_of_scope"
    # Added 2026-09-28 (AI-Tests/): "who are the teachers/professors here?",
    # "which faculty are assistant professors?" — the directory as a whole,
    # filtered by designation/category/department, not one named person.
    FACULTY_DIRECTORY = "faculty_directory"
    # "Which source did you use?", "What was the first question I asked?" —
    # answered from the conversation itself (backend/app/api/ai.py), never
    # from campus data.
    CONVERSATION = "conversation"
    # "Is today a working day?", "do I have class on the 15th?" — calendar
    # holidays + the timetable for that date (2026-09-28).
    WORKING_DAY = "working_day"
    NONE = "none"


@dataclass(frozen=True)
class QueryPlan:
    """The router's output: what kind of question this is and how to answer
    it — never the answer itself. `reasoning` is for audit/debug logs only,
    never shown to the user as a fact."""

    raw_query: str
    route: RouteType
    structured_intent: StructuredIntent = StructuredIntent.NONE
    # free-text extracted from the query to drive semantic search / faculty
    # topic matching (e.g. "attendance requirements", "NLP")
    topic_text: Optional[str] = None
    # a course code detected in the query, for FACULTY_FOR_COURSE
    course_code: Optional[str] = None
    # a specific meal detected in the query ("breakfast"/"lunch"/"dinner"/
    # "snacks"), for MESS_TODAY/MESS_WEEK/MESS_ON_DAY — narrows retrieval
    # to just that meal instead of returning all 4 and making a generation
    # step guess which one the question meant (found live: an ambiguous
    # 4-fact list for one day was enough to make the LLM hedge with "I
    # don't have that information" even though the exact fact was present).
    meal: Optional[str] = None
    # The date a relative reference in the question ("tomorrow", "Monday",
    # "the day after tomorrow") actually means, resolved ONCE here in ISO
    # form and then carried through retrieval and composition. Retrieval
    # must prefer this over re-parsing `topic_text`, and the answer writer
    # must never derive its own "today" — a mismatch between the two was a
    # real live bug ("tomorrow's breakfast" answered with today's menu).
    resolved_date: Optional[str] = None
    # optional explicit filters the query text itself implied (rare — cohort
    # etc. normally comes from the authenticated user's academic context,
    # never from free-text query parsing, per AGENTS.md §17)
    semantic_filters: dict[str, str] = field(default_factory=dict)
    reasoning: str = ""
    # Free-form hints for the answer composer (e.g. {"focus": "first"} for
    # "what is my first class tomorrow", {"course_name": "..."}).
    hints: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "route": self.route.value,
            "structured_intent": self.structured_intent.value,
            "topic_text": self.topic_text,
            "meal": self.meal,
            "resolved_date": self.resolved_date,
            "course_code": self.course_code,
            "semantic_filters": self.semantic_filters,
            "reasoning": self.reasoning,
            "hints": self.hints,
        }


@dataclass
class StructuredFact:
    """One deterministic fact pulled from PostgreSQL, always carrying where
    it came from so the context builder never has to guess provenance."""

    claim: str
    data: dict[str, Any]
    source: str  # e.g. "orion_next_class RPC (live timetable)"
    source_id: Optional[str] = None  # the timetable/document source_id, if any


@dataclass
class SemanticSnippet:
    """One retrieved chunk, always carrying its citation and validity so the
    context builder can filter/attribute without re-querying."""

    content: str
    document_title: str
    section_title: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    similarity: float
    cohort: Optional[str]
    category: Optional[str]
    document_type: Optional[str]
    valid_from: Optional[str]
    valid_until: Optional[str]
    # Cosine similarity of this chunk's Gemini vector to the question
    # (documents.search, hybrid retrieval) — None when vector search didn't
    # run. Used by compose to judge relevance by meaning, not just shared words.
    vector_similarity: Optional[float] = None


@dataclass
class RetrievalResult:
    plan: QueryPlan
    facts: list[StructuredFact] = field(default_factory=list)
    snippets: list[SemanticSnippet] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class GroundedContext:
    """The grounding-ready payload for an eventual LLM call. Nothing in here
    is generated text — it's exactly what was retrieved, with citations,
    ready to hand to a generator or to render directly when no LLM is
    involved (AGENTS.md §16: bypass generation when a structured answer is
    sufficient)."""

    query: str
    route: RouteType
    facts: list[StructuredFact]
    snippets: list[SemanticSnippet]
    warnings: list[str]
    has_answer: bool
    # The router's plan (intent, topic, hints) — the answer composer needs it
    # to phrase an answer for the question that was actually asked.
    plan: Optional[QueryPlan] = None

    @property
    def intent(self) -> StructuredIntent:
        return self.plan.structured_intent if self.plan else StructuredIntent.NONE

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "route": self.route.value,
            "intent": self.intent.value,
            "has_answer": self.has_answer,
            "facts": [
                {"claim": f.claim, "data": f.data, "source": f.source, "source_id": f.source_id}
                for f in self.facts
            ],
            "snippets": [
                {
                    "content": s.content,
                    "document_title": s.document_title,
                    "section_title": s.section_title,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                    "similarity": s.similarity,
                    "cohort": s.cohort,
                    "category": s.category,
                    "document_type": s.document_type,
                    "valid_from": s.valid_from,
                    "valid_until": s.valid_until,
                }
                for s in self.snippets
            ],
            "warnings": self.warnings,
        }
