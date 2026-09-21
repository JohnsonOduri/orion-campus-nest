"""Deterministic query classification (README §8, AGENTS.md §4).

No LLM call here by design — this stage is independently testable and the
router must "not blindly send every question to vector search" (AGENTS.md
§4). Rule-based intent classification is cheap, auditable, and — unlike an
LLM classifier — never costs a token or a quota unit. An LLM-backed
classifier can be added later as a fallback for genuinely ambiguous queries
without changing this module's contract (it still returns a QueryPlan).
"""

from __future__ import annotations

import random
import re
from datetime import datetime

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
_COURSE_INFO_WORD_RE = re.compile(
    r"\b(about|info|information|credits?|syllabus|prerequisites?)\b", re.IGNORECASE
)
_COURSE_ABOUT_LEAD_RE = re.compile(r"^\s*(what\s+is|tell\s+me\s+about|about)\s+", re.IGNORECASE)
# "Tell me about Dr. X" / "Who is Dr. X" — the title is REQUIRED, not
# optional: without it, "tell me about the campus regulations" would be
# swallowed as if "the campus regulations" were a faculty name.
_FACULTY_ABOUT_RE = re.compile(
    r"\b(?:tell\s+me\s+about|who\s+is)\s+(dr\.?|prof\.?|professor|mr\.?|ms\.?|mrs\.?)\s+"
    r"([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)
# "<Name>'s email/office/office hours" — the capitalized-words structure
# itself (a proper-noun heuristic) is distinctive enough that a title isn't
# required here; case-sensitive on purpose so a lowercase sentence doesn't
# accidentally look like a name. The name class deliberately excludes "."
# (no initials support) — with "." allowed, "Dr." itself also matches the
# name pattern, and the optional title group loses the race to the name
# group swallowing "Dr." whole; excluding "." forces "Dr" (no trailing
# period consumed) to fail the immediately-following-'s check, so the
# engine backtracks into the title branch instead, correctly excluding it.
# "office"/"office hours"/"office location" plus the common institute
# synonyms "cabin"/"room" — found live: "Where is cabin of Dr. X?" fell
# through everything since "cabin" wasn't recognized as meaning "office".
_FACULTY_ATTR_WORDS = r"email|e-mail|office\s+hours|office\s+location|office|cabin|room"
_FACULTY_POSSESSIVE_RE = re.compile(
    r"\b(?:(?i:dr|prof|professor|mr|ms|mrs)\.?\s+)?"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})'s\s+"
    rf"(?i:{_FACULTY_ATTR_WORDS})\b"
)
# The other common word order: "where is the cabin of Dr. X", "what is
# the email of Dr. X" — attribute word first, name after "of"/"for",
# anchored to end-of-string (mirrors _FACULTY_ABOUT_RE's approach) so the
# name capture can't run past a trailing "?" or swallow a wrong prefix.
_FACULTY_ATTR_OF_RE = re.compile(
    rf"\b(?:{_FACULTY_ATTR_WORDS})\b.*?\b(?:of|for)\s+"
    r"(dr\.?|prof\.?|professor|mr\.?|ms\.?|mrs\.?)?\s*([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)
_MESS_WORD_RE = re.compile(
    r"\b(mess|canteen|cafeteria|food|menu|breakfast|lunch|dinner|snacks?)\b", re.IGNORECASE
)
_MEAL_RE = re.compile(r"\b(breakfast|lunch|dinner|snacks?)\b", re.IGNORECASE)
_YESTERDAY_RE = re.compile(r"\byesterday\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
# A specific clock time — "class from 10:30", "class at 3pm" — requires
# either a colon (10:30) or an am/pm suffix, never a bare number, so this
# never matches an unrelated number (a course code digit, a count, etc.).
_TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(am|pm)?\b|\b(1[0-2]|0?[1-9])\s*(am|pm)\b",
    re.IGNORECASE,
)

# -------------------------------------------------------------- small talk

# Whole-message only — "hi what is my next class" must still route to a real
# intent below, so these are anchored, not just word-boundary matches.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|good\s*(morning|afternoon|evening)|yo|sup|greetings)\s*[!.]*\s*$",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(r"^\s*(thanks?|thank\s*you|thx|ty|cheers)\s*[!.]*\s*$", re.IGNORECASE)
_BYE_RE = re.compile(r"^\s*(bye|goodbye|see\s*you|later|cya)\s*[!.]*\s*$", re.IGNORECASE)
# "what can you do", "help", "who are you" — extremely common first
# messages to any chatbot; found live these all fell through to the same
# generic UNSUPPORTED response as a nonsense query.
_CAPABILITIES_RE = re.compile(
    r"^\s*(what\s+can\s+you\s+do\??|help\??|who\s+are\s+you\??|what\s+is\s+orion\??|"
    r"what\s+can\s+you\s+help\s+(?:me\s+)?with\??)\s*$",
    re.IGNORECASE,
)
_HOW_ARE_YOU_RE = re.compile(
    r"^\s*(how\s+are\s+you|how'?s\s+it\s+going|what'?s\s+up|how'?s\s+things)\s*\??\s*$",
    re.IGNORECASE,
)

# Reply variety so repeated small talk doesn't read as 3 hardcoded strings
# (the routing decision itself stays fully deterministic — same input
# always -> same RouteType/StructuredIntent — only the reply text varies).
_THANKS_REPLIES = [
    "You're welcome! Let me know if you need anything else.",
    "Anytime! Happy to help.",
    "No problem at all — ask away if you need anything else.",
]
_BYE_REPLIES = [
    "See you! Come back anytime you need campus info.",
    "Bye! I'm here whenever you need something.",
    "Take care! Come back if you have more questions.",
]
_HOW_ARE_YOU_REPLIES = [
    "Doing well, thanks for asking! What can I help you with?",
    "All good here! What do you need help with today?",
]
_CAPABILITIES_REPLY = (
    "I'm ORION, your campus assistant. I can help with: your timetable (today, "
    "a specific day, a specific time, tomorrow/yesterday), the mess menu "
    "(today, this week, a specific meal or day), course info (credits, "
    "syllabus, prerequisites), faculty details (email, office, office hours), "
    "who teaches a course, faculty who work in a research area, and campus "
    "regulations/policies. Just ask in your own words!"
)


def _greeting_reply() -> str:
    """Time-of-day aware rather than one fixed string — a real assistant
    behavior, and still fully deterministic/testable (always one of three
    known variants for a given server clock hour)."""
    hour = datetime.now().hour
    if hour < 12:
        salutation = "Good morning!"
    elif hour < 17:
        salutation = "Good afternoon!"
    else:
        salutation = "Good evening!"
    return f"{salutation} I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations."

# ---------------------------------------------------------------- semantic

# Topics that live in the document corpus (regulations/policies/procedures/
# curriculum), never in a relational table — README §7/§9, AGENTS.md §5.
# Plural forms use an optional trailing "s" (e.g. regulations?) rather than
# a separate alternative — \bregulation\b alone never matches inside
# "regulations" since \b requires a boundary right after "n", and the "s"
# is a word character too, so there's no boundary there. Found live: "Tell
# me about the campus regulations" fell through to UNSUPPORTED.
_SEMANTIC_TOPIC_RE = re.compile(
    r"\b(attendance|regulations?|rules?|polic(?:y|ies)|cgpa|sgpa|grading|grades?|credits?|"
    r"prerequisites?|curriculum|syllabus|hostel|ragging|transcripts?|verification|"
    r"procedures?|condonation|registration requirement|degree requirement|"
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

    # --- small talk: answered directly, never reaches retrieval or the LLM ------
    if _GREETING_RE.match(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SMALL_TALK,
            topic_text=_greeting_reply(),
            reasoning="matched a greeting -> time-of-day canned reply, no retrieval or LLM call",
        )
    if _THANKS_RE.match(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SMALL_TALK,
            topic_text=random.choice(_THANKS_REPLIES),
            reasoning="matched thanks -> canned reply, no retrieval or LLM call",
        )
    if _BYE_RE.match(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SMALL_TALK,
            topic_text=random.choice(_BYE_REPLIES),
            reasoning="matched a farewell -> canned reply, no retrieval or LLM call",
        )
    if _CAPABILITIES_RE.match(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SMALL_TALK,
            topic_text=_CAPABILITIES_REPLY,
            reasoning="matched a capabilities/help question -> canned reply, no retrieval or LLM call",
        )
    if _HOW_ARE_YOU_RE.match(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.SMALL_TALK,
            topic_text=random.choice(_HOW_ARE_YOU_REPLIES),
            reasoning="matched 'how are you' -> canned reply, no retrieval or LLM call",
        )

    # --- structured: mess menu ---------------------------------------------------
    if _MESS_WORD_RE.search(q):
        # A specific meal ("breakfast"/"lunch"/"dinner"/"snacks", as opposed
        # to a generic word like "mess"/"menu"/"food") narrows retrieval to
        # just that meal — found live: leaving all 4 meals in the fact list
        # was ambiguous enough that generation hedged with "I don't have
        # that information" even though the exact fact was present.
        meal_m = _MEAL_RE.search(q)
        meal = None
        if meal_m:
            raw_meal = meal_m.group(1).lower()
            meal = "snacks" if raw_meal.startswith("snack") else raw_meal

        if _WEEK_WORD_RE.search(q):
            return QueryPlan(
                raw_query=query,
                route=RouteType.STRUCTURED,
                structured_intent=StructuredIntent.MESS_WEEK,
                meal=meal,
                reasoning="matched mess/food + week pattern -> mess_week (live mess_menus)",
            )
        # A specific day reference ("yesterday", "tomorrow", a named
        # weekday) must resolve to THAT date, not silently fall back to
        # today's menu — found live: "yesterday's dinner" was returning
        # today's menu mislabeled, since mess_today() always used
        # date.today() regardless of what the query actually asked for.
        day_ref = None
        if _YESTERDAY_RE.search(q):
            day_ref = "yesterday"
        elif _TOMORROW_RE.search(q):
            day_ref = "tomorrow"
        else:
            weekday_m = _WEEKDAY_RE.search(q)
            if weekday_m:
                day_ref = weekday_m.group(1).capitalize()
        if day_ref:
            return QueryPlan(
                raw_query=query,
                route=RouteType.STRUCTURED,
                structured_intent=StructuredIntent.MESS_ON_DAY,
                topic_text=day_ref,
                meal=meal,
                reasoning=f"matched mess/food + day reference ({day_ref}) -> mess_on_day (live mess_menus)",
            )
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.MESS_TODAY,
            meal=meal,
            reasoning="matched mess/food pattern -> mess_today (live mess_menus)",
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
    # A day reference other than "today" — a named weekday, or "yesterday"/
    # "tomorrow" (the exact same class of bug already found and fixed for
    # mess: "What are my classes tomorrow?" fell through everything to
    # UNSUPPORTED since only named weekdays were recognized here).
    day_ref = None
    if _YESTERDAY_RE.search(q):
        day_ref = "yesterday"
    elif _TOMORROW_RE.search(q):
        day_ref = "tomorrow"
    else:
        weekday_m = _WEEKDAY_RE.search(q)
        if weekday_m:
            day_ref = weekday_m.group(1).capitalize()
    if day_ref and _TIMETABLE_WORD_RE.search(q):
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.DAY_OF_WEEK_TIMETABLE,
            topic_text=day_ref,
            reasoning=(
                f"matched a day reference ({day_ref}) + class/timetable word -> "
                "orion_day_timetable for that date"
            ),
        )
    time_m = _TIME_RE.search(q)
    if time_m and _TIMETABLE_WORD_RE.search(q):
        time_text = time_m.group(0).strip()
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.CLASS_AT_TIME,
            topic_text=time_text,
            reasoning=(
                f"matched a specific time ({time_text}) + class/timetable word -> "
                "orion_next_class evaluated as of that time today, same semantics "
                "as NEXT_CLASS but for a caller-specified time instead of now"
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
    if course_m and (_COURSE_INFO_WORD_RE.search(q) or _COURSE_ABOUT_LEAD_RE.match(q)):
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.COURSE_INFO,
            course_code=course_m.group(1).upper().replace(" ", " "),
            reasoning="matched course-info pattern (about/credits/syllabus/prerequisites) -> courses table lookup",
        )

    # --- structured: faculty lookup by name -------------------------------------
    about_m = _FACULTY_ABOUT_RE.search(q)
    if about_m:
        name = about_m.group(2).strip()
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.FACULTY_LOOKUP,
            topic_text=name,
            reasoning=f"matched 'tell me about/who is <title> <name>' ({name}) -> faculty table lookup",
        )
    possessive_m = _FACULTY_POSSESSIVE_RE.search(q)
    if possessive_m:
        name = possessive_m.group(1).strip()
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.FACULTY_LOOKUP,
            topic_text=name,
            reasoning=f"matched '<name>'s email/office/office hours' ({name}) -> faculty table lookup",
        )
    attr_of_m = _FACULTY_ATTR_OF_RE.search(q)
    if attr_of_m:
        name = attr_of_m.group(2).strip()
        return QueryPlan(
            raw_query=query,
            route=RouteType.STRUCTURED,
            structured_intent=StructuredIntent.FACULTY_LOOKUP,
            topic_text=name,
            reasoning=f"matched 'email/office/cabin of/for <name>' ({name}) -> faculty table lookup",
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
