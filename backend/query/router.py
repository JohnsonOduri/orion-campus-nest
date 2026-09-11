"""Deterministic query classification (README §8, AGENTS.md §4).

No LLM call here by design — this stage is independently testable and the
router must "not blindly send every question to vector search" (AGENTS.md
§4). Rule-based intent classification is cheap, auditable, and — unlike an
LLM classifier — never costs a token or a quota unit. An LLM-backed
classifier can be added later as a fallback for genuinely ambiguous queries
without changing this module's contract (it still returns a QueryPlan).
"""

from __future__ import annotations

import re

from .types import QueryPlan, RouteType, StructuredIntent

# ------------------------------------------------------------- structured

_NEXT_CLASS_RE = re.compile(
    r"\b(next class|where.*(is|s)\s+my\s+next\s+class|what.*(class|lecture).*(now|currently|right now))\b",
    re.IGNORECASE,
)
_TODAY_TIMETABLE_RE = re.compile(
    r"\btoday\b.*\b(class|classes|timetable|schedule)\b|\b(class|classes|timetable|schedule)\b.*\btoday\b",
    re.IGNORECASE,
)
_WEEK_WORD_RE = re.compile(r"\b(this week|weekly|week.s)\b", re.IGNORECASE)
_TIMETABLE_WORD_RE = re.compile(r"\b(class|classes|timetable|schedule)\b", re.IGNORECASE)
_WEEKDAY_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_WHO_TEACHES_RE = re.compile(
    r"\bwho\s+teaches\b|\bfaculty\s+(for|teaching)\b|\binstructor\s+for\b", re.IGNORECASE
)
_COURSE_CODE_RE = re.compile(r"\b([IUE][A-Z]{2}\s?\d{3}|[A-Z]{2,4}\s?\d{3})\b")

# ---------------------------------------------------------------- semantic

# Topics that live in the document corpus (regulations/policies/procedures/
# curriculum), never in a relational table — README §7/§9, AGENTS.md §5.
_SEMANTIC_TOPIC_RE = re.compile(
    r"\b(attendance|regulation|rule|policy|policies|cgpa|sgpa|grading|grade|credit|"
    r"prerequisite|curriculum|syllabus|hostel|ragging|transcript|verification|"
    r"procedure|condonation|registration requirement|degree requirement|"
    r"summer term|continuation requirement)\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------------ hybrid

# Faculty + a topic + (implicitly or explicitly) wanting to know when/where
# to reach them — README §8 hybrid example, AGENTS.md §5.
_FACULTY_MENTION_RE = re.compile(
    r"\b(faculty|professor|instructor)\b.*\b(work|works|working|research|specializ|"
    r"interest)\w*\b|\bwho\s+(works|is\s+working)\s+(on|in)\b|\brecommend\s+a\s+faculty\b",
    re.IGNORECASE,
)
_MEET_AVAILABILITY_RE = re.compile(
    r"\b(meet|available|availability|office hours|when can i|when.s a good time)\b",
    re.IGNORECASE,
)


def classify(query: str) -> QueryPlan:
    """Classify a raw user query into a QueryPlan. Pure function, no I/O."""
    q = (query or "").strip()
    if not q:
        return QueryPlan(
            raw_query=query,
            route=RouteType.UNSUPPORTED,
            reasoning="empty query",
        )

    # --- structured: timetable -------------------------------------------------
    if _NEXT_CLASS_RE.search(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.NEXT_CLASS,
            reasoning="matched next-class pattern -> orion_next_class (live timetable)",
        )
    if _WEEK_WORD_RE.search(q) and _TIMETABLE_WORD_RE.search(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.WEEK_TIMETABLE,
            reasoning="matched week-timetable pattern -> orion_week_timetable",
        )
    if _TODAY_TIMETABLE_RE.search(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.DAY_TIMETABLE,
            reasoning="matched today-timetable pattern -> orion_day_timetable",
        )
    weekday_m = _WEEKDAY_RE.search(q)
    if weekday_m and _TIMETABLE_WORD_RE.search(q):
        weekday_name = weekday_m.group(1).capitalize()
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.DAY_OF_WEEK_TIMETABLE,
            topic_text=weekday_name,
            reasoning=(
                f"matched a named weekday ({weekday_name}) + class/timetable word -> "
                "orion_day_timetable for the nearest upcoming occurrence of that weekday"
            ),
        )

    course_m = _COURSE_CODE_RE.search(q)
    if _WHO_TEACHES_RE.search(q) and course_m:
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.FACULTY_FOR_COURSE,
            course_code=course_m.group(1).upper().replace(" ", " "),
            reasoning="matched 'who teaches <course code>' -> timetable/course join",
        )

    # --- hybrid: faculty + topic + meet/availability ----------------------------
    if _FACULTY_MENTION_RE.search(q) or (
        "faculty" in q.lower() and _MEET_AVAILABILITY_RE.search(q)
    ):
        topic = _extract_topic(q)
        return QueryPlan(
            raw_query=query,
            route=RouteType.HYBRID,
            topic_text=topic,
            reasoning=(
                "faculty + topic/meet pattern -> faculty.research_interests match "
                "(structured) + timetable schedule (structured); no document corpus "
                "involved for this intent"
            ),
        )

    # --- semantic: document corpus -----------------------------------------------
    if _SEMANTIC_TOPIC_RE.search(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SEMANTIC,
            topic_text=q,
            reasoning="matched a regulations/policy/procedure topic -> document_chunks",
        )

    return QueryPlan(
        raw_query=query,
        route=RouteType.UNSUPPORTED,
        reasoning="no structured/semantic/hybrid pattern matched — ambiguous or out of scope",
    )


_STOPWORDS = {
    "which", "who", "what", "faculty", "professor", "instructor", "work", "works",
    "working", "on", "in", "and", "when", "can", "i", "meet", "them", "is", "the",
    "a", "an", "recommend", "for", "of", "to", "with", "research", "interests",
}


def _extract_topic(query: str) -> str:
    """Best-effort topic phrase for faculty-matching (e.g. "NLP" from "Which
    faculty work in NLP and when can I meet them?"). Falls back to the full
    query if nothing better is found — matching against research_interests
    text is tolerant of extra words."""
    words = re.findall(r"[A-Za-z][A-Za-z.+-]*", query)
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept) if kept else query
