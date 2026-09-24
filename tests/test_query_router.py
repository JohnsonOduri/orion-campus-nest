"""Pure, offline tests for backend/query/router.py — no network, no LLM.

Covers the three required cases plus nearby phrasings and the UNSUPPORTED
fallback, so the router's classification is independently verified before
any retrieval or generation is wired to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query.router import classify, detect_cohort_reference, strip_cohort_noise  # noqa: E402
from backend.query import tempo  # noqa: E402
from backend.query.types import RouteType, StructuredIntent  # noqa: E402


def test_next_class_routes_structured():
    plan = classify("What is my next class?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.NEXT_CLASS


def test_next_class_phrasing_variants():
    for q in ["What is my next class?", "What class do I have right now?"]:
        plan = classify(q)
        assert plan.route == RouteType.STRUCTURED
        assert plan.structured_intent == StructuredIntent.NEXT_CLASS


def test_where_is_my_next_class_also_answers_the_room():
    """2026-09-22: "where" asks for a place, so it routes to CLASSROOM, which
    answers with the next class AND the section's allocated room."""
    plan = classify("Where is my next class?")
    assert plan.structured_intent == StructuredIntent.CLASSROOM


def test_attendance_routes_semantic():
    plan = classify("What are the attendance requirements?")
    assert plan.route == RouteType.SEMANTIC
    assert plan.topic_text


def test_detect_cohort_reference_explicit_mentions_only():
    """CLAUDE.md §20: only an explicit cohort/admission-year mention counts
    — never inferred from a bare year that could mean something else (an
    academic-calendar "2026-27" reference, a course code, etc.)."""
    assert detect_cohort_reference("What is the attendance requirement for students admitted in 2026?") == "26-onwards"
    assert detect_cohort_reference("Under the 26-onwards regulations, what is required?") == "26-onwards"
    assert detect_cohort_reference("What about the 2021-25 batch?") == "21-25"
    assert detect_cohort_reference("Students admitted in 2021 need what CGPA?") == "21-25"
    assert detect_cohort_reference("What is the attendance requirement?") is None
    assert detect_cohort_reference("When does the 2026-27 semester start?") is None


def test_cross_cohort_regulation_question_carries_the_cohort_hint():
    plan = classify("What is the attendance requirement for students admitted in 2026?")
    assert plan.route == RouteType.SEMANTIC
    assert plan.hints.get("cohort_ref") == "26-onwards"
    assert "cohort_compare" not in plan.hints


def test_cross_cohort_comparison_question_carries_the_compare_hint():
    plan = classify("Is the attendance rule different for the 2026 admission batch compared to mine?")
    assert plan.route == RouteType.SEMANTIC
    assert plan.hints.get("cohort_ref") == "26-onwards"
    assert plan.hints.get("cohort_compare") == "yes"


def test_own_cohort_question_carries_no_cohort_hint():
    plan = classify("What is the attendance requirement?")
    assert "cohort_ref" not in plan.hints


def test_strip_cohort_noise_keeps_the_real_subject():
    stripped = strip_cohort_noise(
        "Is the attendance rule different for the 2026 admission batch compared to mine?"
    )
    assert "attendance" in stripped
    assert "2026" not in stripped
    assert "mine" not in stripped.lower()


def test_semantic_topic_keywords():
    for q in [
        "What is the CGPA calculation rule?",
        "What are the hostel rules?",
        "What is the transcript verification procedure?",
    ]:
        assert classify(q).route == RouteType.SEMANTIC


def test_semantic_topic_plural_forms():
    """Plural phrasing must match too — \\bregulation\\b alone never matches
    inside "regulations" (no word boundary between "n" and "s")."""
    for q in [
        "Tell me about the campus regulations",
        "What are the degree requirement procedures?",
        "What are the prerequisites for this course?",
        "What are the grading policies?",
    ]:
        assert classify(q).route == RouteType.SEMANTIC


def test_faculty_nlp_meet_routes_hybrid():
    plan = classify("Which faculty work in NLP and when can I meet them?")
    assert plan.route == RouteType.HYBRID
    assert plan.topic_text == "NLP"


def test_faculty_recommendation_routes_hybrid():
    plan = classify("Recommend a faculty member for computer vision.")
    assert plan.route == RouteType.HYBRID


def test_today_timetable_routes_structured():
    plan = classify("What classes do I have today?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.DAY_TIMETABLE


def test_week_timetable_routes_structured():
    plan = classify("Show me my timetable for this week")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.WEEK_TIMETABLE


def test_named_weekday_routes_structured():
    plan = classify("tell me what my classes are on monday")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE
    assert plan.topic_text == "Monday"


def test_named_weekday_requires_a_timetable_word():
    """A bare weekday mention with no class/timetable word stays
    unsupported rather than guessing intent."""
    plan = classify("I met him on Monday")
    assert plan.route == RouteType.UNSUPPORTED


def test_specific_time_routes_class_at_time():
    """The reported bug: "What is my class from 10:30?" fell through every
    pattern to UNSUPPORTED — no existing regex handled a caller-given clock
    time, only "now"/today/a named weekday."""
    plan = classify("What is my class from 10:30?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.CLASS_AT_TIME
    assert plan.topic_text == "10:30"


def test_specific_time_am_pm_routes_class_at_time():
    for q, expected in [
        ("What class do I have at 3pm?", "3pm"),
        ("what class do I have at 9 am", "9 am"),
    ]:
        plan = classify(q)
        assert plan.route == RouteType.STRUCTURED
        assert plan.structured_intent == StructuredIntent.CLASS_AT_TIME
        assert plan.topic_text == expected


def test_bare_number_does_not_trigger_class_at_time():
    """A bare number with no colon and no am/pm must not be mistaken for a
    time (e.g. a count or unrelated digit in the sentence)."""
    plan = classify("I have 3 classes today")
    assert plan.structured_intent != StructuredIntent.CLASS_AT_TIME


def test_timetable_tomorrow_routes_day_of_week_timetable():
    """The same class of bug already found and fixed for mess ("yesterday's
    dinner") also existed for the general timetable — "tomorrow"/"yesterday"
    were never recognized, only named weekdays."""
    plan = classify("What are my classes tomorrow?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE
    assert plan.topic_text == "tomorrow"


def test_timetable_yesterday_routes_day_of_week_timetable():
    plan = classify("What classes did I have yesterday?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE
    assert plan.topic_text == "yesterday"


def test_timetable_relative_day_requires_a_timetable_word():
    """A day reference alone isn't enough — but "did I have" is: in a
    student assistant "What did I have yesterday?" means classes (AI-task.md)."""
    assert classify("What did I have yesterday?").structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE
    assert classify("It rained yesterday").route == RouteType.UNSUPPORTED


def test_course_info_routes_structured():
    for q in [
        "What is ICS 211 about?",
        "How many credits is CSE 311?",
        "syllabus for IEG 311",
        "Tell me about ICS 211",
    ]:
        plan = classify(q)
        assert plan.route == RouteType.STRUCTURED
        assert plan.structured_intent == StructuredIntent.COURSE_INFO
        assert plan.course_code


def test_who_teaches_wins_over_course_info():
    """"who teaches" must still route to FACULTY_FOR_COURSE, not COURSE_INFO,
    even though both patterns could plausibly match the same course code."""
    plan = classify("Who teaches ICS 211?")
    assert plan.structured_intent == StructuredIntent.FACULTY_FOR_COURSE


def test_faculty_lookup_tell_me_about():
    plan = classify("Tell me about Dr. Manu Madhavan")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Manu Madhavan"


def test_faculty_lookup_who_is():
    plan = classify("Who is Dr. Sara Renjit")
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Sara Renjit"


def test_faculty_about_requires_a_title():
    """Without a title, "tell me about X" must NOT be swallowed as a
    faculty lookup — "tell me about the campus regulations" must still
    reach SEMANTIC, not misfire as a faculty-name search."""
    plan = classify("Tell me about the campus regulations")
    assert plan.route == RouteType.SEMANTIC
    assert plan.structured_intent != StructuredIntent.FACULTY_LOOKUP


def test_faculty_lookup_possessive_email():
    plan = classify("What is Dr. Sara Renjit's email?")
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Sara Renjit"


def test_faculty_lookup_possessive_office_no_title():
    plan = classify("Where is Manu Madhavan's office?")
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Manu Madhavan"


def test_faculty_lookup_possessive_office_hours():
    plan = classify("What are Dr. Manu Madhavan's office hours?")
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Manu Madhavan"


def test_faculty_lookup_cabin_of_name():
    """The reported bug: "cabin" wasn't recognized as meaning "office", and
    the "<attribute> of <name>" word order (as opposed to "<name>'s
    <attribute>") wasn't handled at all."""
    plan = classify("Where is cabin of Dr Divya Sindhu Lekha?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text == "Divya Sindhu Lekha"


def test_faculty_lookup_attribute_of_name_variants():
    for q, expected in [
        ("Where is the office of Dr. Ananth A?", "Ananth A"),
        ("What is the email of Dr. Manu Madhavan?", "Manu Madhavan"),
    ]:
        plan = classify(q)
        assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
        assert plan.topic_text == expected


def test_faculty_attribute_of_does_not_swallow_hybrid_office_hours():
    """"faculty office hours ... meet them" (no "of"/"for" a name) must
    still reach HYBRID, not get misclassified as a FACULTY_LOOKUP."""
    plan = classify("Which faculty have office hours today and when can I meet them?")
    assert plan.route == RouteType.HYBRID


def test_capabilities_routes_small_talk():
    for q in ["what can you do", "help", "who are you", "what can you help with"]:
        plan = classify(q)
        assert plan.route == RouteType.SMALL_TALK
        assert "timetable" in plan.topic_text.lower()


def test_how_are_you_routes_small_talk():
    for q in ["how are you", "what's up", "how's it going"]:
        plan = classify(q)
        assert plan.route == RouteType.SMALL_TALK


def test_client_supplied_batch_is_never_parsed_into_the_plan():
    """A student typing their own batch/section into the message must not
    influence routing or retrieval — personalization comes only from the
    authenticated context (AGENTS.md §17), never free text."""
    plan = classify("i am from batch 3 2024 BCS 66 now tell me what my classes are on monday")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE
    assert plan.topic_text == "Monday"
    assert "batch" not in plan.to_dict()


def test_who_teaches_course_routes_structured():
    plan = classify("Who teaches ICS 212?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.FACULTY_FOR_COURSE
    assert "ICS" in plan.course_code


def test_empty_query_unsupported():
    plan = classify("")
    assert plan.route == RouteType.UNSUPPORTED


def test_ambiguous_query_unsupported():
    assert classify("hello there").route == RouteType.SMALL_TALK  # a greeting, not ambiguous
    for q in ["asdkfj qwer nonsense query", "I met him on Monday", "ok"]:
        assert classify(q).route == RouteType.UNSUPPORTED, q


def test_mess_today_routes_structured():
    for q in ["What's the mess menu today?", "What's for lunch?", "what's on the canteen menu"]:
        plan = classify(q)
        assert plan.route == RouteType.STRUCTURED
        assert plan.structured_intent == StructuredIntent.MESS_TODAY


def test_mess_week_routes_structured():
    plan = classify("Show me the mess menu for this week")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.MESS_WEEK


def test_mess_yesterday_routes_mess_on_day():
    """The reported bug: "yesterday's dinner" must resolve to yesterday's
    date, not silently fall back to today's menu."""
    plan = classify("What was there for yesterday's dinner?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.MESS_ON_DAY
    assert plan.topic_text == "yesterday"


def test_mess_tomorrow_routes_mess_on_day():
    plan = classify("What's for lunch tomorrow?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.MESS_ON_DAY
    assert plan.topic_text == "tomorrow"


def test_mess_named_weekday_routes_mess_on_day():
    plan = classify("What's the mess menu on Monday?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.MESS_ON_DAY
    assert plan.topic_text == "Monday"


def test_mess_meal_is_extracted_for_ambiguous_phrasing():
    """The reported bug: "What was the yesterday's dinner?" retrieved the
    right facts but generation hedged because 4 unrelated meals were in the
    fact list. Narrowing to just the mentioned meal removes the ambiguity."""
    plan = classify("What was the yesterday's dinner?")
    assert plan.structured_intent == StructuredIntent.MESS_ON_DAY
    assert plan.meal == "dinner"


def test_mess_meal_extraction_for_today_and_week():
    assert classify("What's for breakfast today?").meal == "breakfast"
    assert classify("mess menu for this week").meal is None
    assert classify("snacks this week").meal == "snacks"


def test_mess_generic_query_has_no_meal_filter():
    plan = classify("What's the mess menu?")
    assert plan.structured_intent == StructuredIntent.MESS_TODAY
    assert plan.meal is None


def test_greeting_routes_small_talk():
    for q in ["hi", "Hello!", "hey", "heyy", "good morning"]:
        plan = classify(q)
        assert plan.route == RouteType.SMALL_TALK
        assert plan.topic_text


def test_thanks_routes_small_talk():
    plan = classify("thanks!")
    assert plan.route == RouteType.SMALL_TALK


def test_bye_routes_small_talk():
    plan = classify("bye")
    assert plan.route == RouteType.SMALL_TALK


def test_greeting_embedded_in_a_real_question_is_not_swallowed():
    """"hi what is my next class" must still answer the real question — only
    a message that is *only* a greeting should short-circuit to small talk."""
    plan = classify("hi what is my next class")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.NEXT_CLASS


def test_plan_never_carries_fabricated_answer_data():
    """A QueryPlan is a routing decision only — it must never itself carry
    anything that looks like a retrieved fact (AGENTS.md §6)."""
    plan = classify("What is my next class?")
    d = plan.to_dict()
    assert set(d.keys()) == {
        "raw_query",
        "route",
        "structured_intent",
        "topic_text",
        "meal",
        # A date the router resolved from the question's own words — a
        # routing decision, not retrieved data (backend/query/tempo.py).
        "resolved_date",
        "course_code",
        "semantic_filters",
        "reasoning",
        "hints",
    }
    # hints are phrasing cues taken from the question itself, never data
    assert all(isinstance(v, str) for v in d["hints"].values())


# --------------------------------------------------- live-bug regressions

@pytest.mark.parametrize("query", [
    "Where is Dr. Anisth S cabin?",     # no possessive, name ends in an initial
    "Where is Dr Anisth?",              # no attribute word at all
    "Where is Anisth's office?",        # possessive, no title
    "Dr Kala S email",                  # attribute after the name, no question
    "Where is the cabin of Dr. Ansith S?",
])
def test_faculty_location_questions_never_reach_document_search(query):
    """All five phrasings ask one thing: where a person sits. Live, the
    first two fell through the whole router into full-text document search
    and came back quoting an anti-ragging committee memo."""
    plan = classify(query)
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.FACULTY_LOOKUP
    assert plan.topic_text


def test_faculty_name_capture_keeps_a_trailing_initial():
    """"Anisth S" must not be truncated to "Anisth" — under IGNORECASE an
    optional possessive `s?` silently ate the initial."""
    assert classify("Where is Dr. Anisth S cabin?").topic_text == "Anisth S"


@pytest.mark.parametrize("query", [
    "Is there any free class Tomorrow?",
    "Is there any Free lectures?",
    "Do I have a free period tomorrow?",
    "When is my next free period?",
    "free period on monday?",
])
def test_free_period_questions_route_to_the_timetable(query):
    """Live, "free class"/"free lecture" phrasings matched no timetable
    pattern and were answered from curriculum PDFs that happened to contain
    the word "Lectures"."""
    plan = classify(query)
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.FREE_TIME
    assert plan.resolved_date, "a free-period answer must be pinned to a date"


def test_classroom_question_is_not_mistaken_for_a_faculty_lookup():
    assert classify("Where is my class room?").structured_intent == StructuredIntent.CLASSROOM
    assert classify("Where is my next class?").structured_intent == StructuredIntent.CLASSROOM


@pytest.mark.parametrize("query,intent", [
    ("Tomorrow's breakfast?", StructuredIntent.MESS_ON_DAY),
    ("What's for lunch today?", StructuredIntent.MESS_TODAY),
    ("What classes do I have tomorrow?", StructuredIntent.DAY_OF_WEEK_TIMETABLE),
])
def test_day_referencing_plans_carry_a_resolved_date(query, intent):
    """The date has to travel on the QueryPlan: retrieval must not re-parse
    "tomorrow" for itself, and the answer writer must not guess its own
    "today" (backend/query/tempo.py)."""
    plan = classify(query)
    assert plan.structured_intent == intent
    assert plan.resolved_date == tempo.resolve_to_date(tempo.day_reference(query)).isoformat()
