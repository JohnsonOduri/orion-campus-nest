"""Pure, offline tests for backend/query/router.py — no network, no LLM.

Covers the three required cases plus nearby phrasings and the UNSUPPORTED
fallback, so the router's classification is independently verified before
any retrieval or generation is wired to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query.router import classify  # noqa: E402
from backend.query.types import RouteType, StructuredIntent  # noqa: E402


def test_next_class_routes_structured():
    plan = classify("What is my next class?")
    assert plan.route == RouteType.STRUCTURED
    assert plan.structured_intent == StructuredIntent.NEXT_CLASS


def test_next_class_phrasing_variants():
    for q in ["Where is my next class?", "What class do I have right now?"]:
        plan = classify(q)
        assert plan.route == RouteType.STRUCTURED
        assert plan.structured_intent == StructuredIntent.NEXT_CLASS


def test_attendance_routes_semantic():
    plan = classify("What are the attendance requirements?")
    assert plan.route == RouteType.SEMANTIC
    assert plan.topic_text


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
    """Same conservative requirement as the named-weekday case — "yesterday"
    alone, with nothing else to disambiguate it, stays unsupported."""
    plan = classify("What did I have yesterday?")
    assert plan.route == RouteType.UNSUPPORTED


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
    plan = classify("hello there")
    assert plan.route == RouteType.UNSUPPORTED


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
        "course_code",
        "semantic_filters",
        "reasoning",
    }
