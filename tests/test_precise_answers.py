"""Offline tests for AI-Tests/ round 2 (2026-09-28): answering exactly the
time asked about (free at / between / after / longest, mess open/close),
people as they're actually typed ("Amit sir", "mirotha;;i chand"), and
the routing that sends each of those questions to the right data.

Live end-to-end checks: scripts/eval_pipeline.py --only ai2
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from query import campus, compose, lexicon, router, timeq  # noqa: E402
from query.types import GroundedContext, RouteType, SemanticSnippet, StructuredFact, StructuredIntent  # noqa: E402

# The Monday timetable from the WhatsApp screenshots (S5 CSE III).
MONDAY = [("09:30", "10:25", "Operations & Supply Chain Management (IHS 313)"),
          ("11:30", "12:25", "Artificial Intelligence (CSE 311)"),
          ("14:30", "15:25", "Human Resource Management (IHS 311)"),
          ("15:30", "16:25", "Interaction with faculty"),
          ("16:30", "17:25", "Artificial Intelligence (CSE 311)"),
          ("17:00", "18:30", "Coding Club Activities")]
BLOCKS = timeq.busy_blocks([{"start_time": a, "end_time": b, "l": l} for a, b, l in MONDAY], lambda e: e["l"])


def ans(q: str, now: int = 14 * 60 + 52) -> str:
    return timeq.answer_free(BLOCKS, timeq.parse(q), "today", now_minute=now)


# ---------------------------------------------------------------- parsing

@pytest.mark.parametrize("q, hints", [
    ("Am I free at 2?", {"at": "14:00"}),
    ("am i free at 10", {"at": "10:00"}),
    ("free at 12:30", {"at": "12:30"}),
    ("Do I have a free hour between 2 and 4?", {"from": "14:00", "to": "16:00", "min": "60"}),
    ("free between 11 and 1", {"from": "11:00", "to": "13:00"}),
    ("Am I free after 3pm?", {"from": "15:00"}),
    ("anything before 11am", {"to": "11:00"}),
    ("What's my longest free slot today?", {"longest": "yes"}),
    ("Is Tuesday evening free?", {"from": "17:00", "to": "20:00", "part": "evening"}),
    ("Do I have a break before lunch?", {"from": "08:00", "to": "12:00", "part": "before lunch"}),
    ("am i free right now", {"now": "yes"}),
    ("do I have 30 minutes free after 2:30", {"from": "14:30", "min": "30"}),
    ("when am I free today", {}),
])
def test_parse(q, hints):
    assert timeq.parse(q).hints() == hints


# ------------------------------------------------------------ free answers

def test_free_at_a_time_answers_that_time_only():
    assert ans("Am I free at 2?").startswith("Yes — you're free at 2 PM today")
    assert "until 2:30 PM" in ans("Am I free at 2?")
    no = ans("Am I free at 3?")
    assert no.startswith("No — at 3 PM today you have **Human Resource Management (IHS 311)**")
    assert "Your classes today" not in no


def test_free_hour_in_a_window():
    text = ans("Do I have a free hour between 2 and 4?")
    assert text.startswith("No — you don't have 1 hour free between 2 PM and 4 PM")
    assert "2 PM–2:30 PM (30 min)" in text
    assert ans("Do I have a free hour between 10 and 12?").startswith("Yes — you have **10:25 AM–11:30 AM** free")


def test_after_a_time_runs_on():
    assert "**from 6:30 PM onwards**" in ans("Am I free after 3pm?")


def test_longest_slot():
    text = ans("What's my longest free slot today?")
    assert text.startswith("Your longest free slot today is **12:25 PM–2:30 PM** (2 h 5 min)")


def test_right_now():
    assert ans("am i free right now", now=15 * 60).startswith("No — right now you have **Human Resource Management")
    assert ans("am i free right now", now=13 * 60).startswith("Yes — you're free right now")


def test_whole_day_only_when_nothing_specific_was_asked():
    assert "Your classes today" in ans("when am I free today")


def test_no_classes():
    assert "free all day" in timeq.answer_free([], timeq.parse("Am I free at 2?"), "on Sunday")


# ----------------------------------------------------------------- mess

TIMINGS = {"breakfast": (420, 585), "lunch": (720, 870), "snacks": (960, 1080), "dinner": (1140, 1230)}


@pytest.mark.parametrize("q, kind", [
    ("Is the mess open now?", "open_now"),
    ("What time does the mess close?", "close"),
    ("What time does the mess open?", "open"),
    ("When is breakfast?", "timing"),
    ("What are the lunch timings?", "timing"),
    ("when does dinner end", "close"),
    ("what's for lunch", None),
    ("what is the mess menu today", None),
])
def test_mess_time_question(q, kind):
    assert timeq.mess_time_question(q) == kind


def test_mess_answers():
    assert timeq.answer_mess_time(TIMINGS, "open_now", None, 14 * 60 + 52).startswith(
        "No — the mess is closed right now. It opens next for **snacks** at **4 PM**")
    assert timeq.answer_mess_time(TIMINGS, "open_now", None, 13 * 60).startswith(
        "Yes — the mess is open now: **lunch** is being served until **2:30 PM**")
    assert timeq.answer_mess_time(TIMINGS, "close", None, 0).startswith("The mess closes at **8:30 PM**")
    assert timeq.answer_mess_time(TIMINGS, "timing", "breakfast", 0) == "Breakfast is served **7 AM–9:45 AM**."
    assert "has closed for the day" in timeq.answer_mess_time(TIMINGS, "open_now", None, 22 * 60)


# ----------------------------------------------------------------- names

FACULTY = [{"full_name": n} for n in (
    "Dr. Amit Kumar Roy", "Dr. A Balu", "Dr. Athira B", "Dr. Mirothali Chand C", "Dr. Ansith S",
    "Dr. Christina Terese Joseph", "Dr. Mathew Joseph", "Dr Augustine Joseph", "Dr.Jobin Jose", "Dr. Deepak Jose",
    "Dr. Manu Madhavan")]


@pytest.mark.parametrize("q, name", [
    ("Amit sir email", "Dr. Amit Kumar Roy"),
    ("Athira mam's office?", "Dr. Athira B"),
    ("Dr. A Balu sir email", "Dr. A Balu"),
    ("mirotha;;i chand contact", "Dr. Mirothali Chand C"),
    ("What Christina Joseph's research area?", "Dr. Christina Terese Joseph"),
    ("What position does Dr. Jobin Jose hold?", "Dr.Jobin Jose"),
    ("Ansith sir office?", "Dr. Ansith S"),
])
def test_names_as_typed(q, name):
    assert campus.match_faculty_names(q, FACULTY) == [name]


def test_shared_name_is_not_guessed():
    found = campus.match_faculty_names("joseph sir email", FACULTY)
    assert len(found) > 1 and campus.match_faculty_name("joseph sir email", FACULTY) is None


def test_unknown_person():
    assert campus.match_faculty_names("Rekha ma'am email", FACULTY) == []


def test_directory_names_are_never_spell_corrected():
    # "manu" is one edit from "menu": a name must win
    assert lexicon.correct_spelling("manu sir email")[0] == "manu sir email"
    assert lexicon.correct_spelling("manimala boys hostel")[0] == "manimala boys hostel"


def test_closest_match_only_for_real_misspellings():
    assert not compose._matched_differently("Amit sir email", "Dr. Amit Kumar Roy")
    assert not compose._matched_differently("Is Dr. Manu Madhavan available?", "Dr. Manu Madhavan")
    assert compose._matched_differently("Jhon Paul Martin", "Dr.John Paul Martin")


# ---------------------------------------------------------------- routing

@pytest.mark.parametrize("q, intent", [
    ("Am I free at 2?", StructuredIntent.FREE_TIME),
    ("Do I have a break before lunch?", StructuredIntent.FREE_TIME),
    ("Is the mess open now?", StructuredIntent.MESS_TODAY),
    ("Amit sir email", StructuredIntent.FACULTY_LOOKUP),
    ("Athira mam's office?", StructuredIntent.FACULTY_LOOKUP),
    ("What subjects does Dr. Ansith teach?", StructuredIntent.FACULTY_LOOKUP),
    ("Is Dr. Manu Madhavan free right now?", StructuredIntent.FACULTY_LOOKUP),
    ("Is today a working day?", StructuredIntent.WORKING_DAY),
    ("Do I have class on the 15th?", StructuredIntent.WORKING_DAY),
    ("is tomorrow a holiday", StructuredIntent.WORKING_DAY),
    ("Is AC306 my classroom?", StructuredIntent.CLASSROOM),
    ("Where is the lab?", StructuredIntent.CLASSROOM),
    ("is manimala boys hostel or girls hostel", StructuredIntent.HOSTEL_WARDENS),
    ("Who is the sports officer?", StructuredIntent.FACULTY_ROLE),
    ("Who handles academic affair?", StructuredIntent.FACULTY_ROLE),
    ("Faculty who teaches OS", StructuredIntent.FACULTY_FOR_COURSE),
    ("Which faculty handles the lab for CSE 312?", StructuredIntent.FACULTY_FOR_COURSE),
    ("Which of my courses have labs?", StructuredIntent.MY_COURSES),
    ("Do I have anything in the morning?", StructuredIntent.DAY_TIMETABLE),
    ("What did I miss today?", StructuredIntent.DAY_TIMETABLE),
    ("Am I a first year student?", StructuredIntent.MY_PROFILE),
    ("What is OS?", StructuredIntent.COURSE_INFO),
])
def test_routing(q, intent):
    assert router.classify(q).structured_intent == intent


@pytest.mark.parametrize("q", [
    "How do I drop a course?",          # "drop" is not "Dr op"
    "Do I have classes on Saturday?",   # a timetable question, not a working-day check
    "what time does the hostel gate close",
])
def test_not_hijacked(q):
    assert router.classify(q).structured_intent not in (StructuredIntent.FACULTY_LOOKUP, StructuredIntent.WORKING_DAY,
                                                        StructuredIntent.MESS_TODAY)


def test_date_asked_resolves_the_next_15th():
    from datetime import date
    assert router._date_asked("do I have class on the 15th", date(2026, 9, 28)) == date(2026, 10, 15)
    assert router._date_asked("do I have class on the 30th", date(2026, 9, 28)) == date(2026, 9, 30)


# ---------------------------------------------------------------- compose

def _ctx(intent, facts, q, hints=None):
    plan = router.classify(q)
    if hints:
        import dataclasses
        plan = dataclasses.replace(plan, hints={**plan.hints, **hints})
    return GroundedContext(query=q, route=RouteType.STRUCTURED, facts=facts, snippets=[], warnings=[],
                           has_answer=bool(facts), plan=plan)


def test_hostel_gender():
    rows = [StructuredFact(claim="", source="hostel_wardens", data={
        "hall_name": "MANIMALA HOSTEL (BOYS)", "role": "hostel_warden", "full_name": "X", "_mode": "hall"})]
    text = compose.compose_wardens(_ctx(StructuredIntent.HOSTEL_WARDENS, rows, "is manimala boys hostel or girls hostel"))
    assert text.startswith("**Manimala Hostel** is a **boys'** hostel.")


def test_unmentioned_topic_is_declined_not_quoted():
    snip = SemanticSnippet("Degree certificate verification requires copies of the grade card.", "Verification", None,
                           1, 1, 0.9, None, None, "procedure", None, None)
    assert compose._unmentioned_terms("How do I get a bonafide certificate?", [snip]) == ["bonafide"]
    assert compose._unmentioned_terms("How do I get certificate verification?", [snip]) == []
