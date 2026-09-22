"""Offline tests for the Gemini-free answer engine (2026-09-22, AI-task.md):
router intents, follow-up resolution, passage extraction, the calendar
matcher and answer formatting. No network: Supabase is faked where needed.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import campus, compose, documents, followup  # noqa: E402
from backend.query.router import classify  # noqa: E402
from backend.query.types import GroundedContext, QueryPlan, RouteType, SemanticSnippet, StructuredFact, StructuredIntent as I  # noqa: E402


# ----------------------------------------------------------------- router

@pytest.mark.parametrize("query,route,intent", [
    ("When do the end semester exams start?", RouteType.STRUCTURED, I.ACADEMIC_CALENDAR),
    ("When is the last instructional day?", RouteType.STRUCTURED, I.ACADEMIC_CALENDAR),
    ("What are the upcoming deadlines?", RouteType.STRUCTURED, I.ACADEMIC_CALENDAR),
    ("When is my ICS 213 exam?", RouteType.STRUCTURED, I.EXAM_SCHEDULE),
    ("Are there any current announcements?", RouteType.STRUCTURED, I.ANNOUNCEMENTS),
    ("Who is the warden of Sahyadri hostel?", RouteType.STRUCTURED, I.HOSTEL_WARDENS),
    ("Who is the HOD of ECE?", RouteType.STRUCTURED, I.FACULTY_ROLE),
    ("Is there a counsellor or psychologist I can talk to?", RouteType.STRUCTURED, I.FACULTY_ROLE),
    ("Who researches underwater sensor networks?", RouteType.HYBRID, I.FACULTY_RESEARCH),
    ("Is anyone working on blockchain?", RouteType.HYBRID, I.FACULTY_RESEARCH),
    ("What courses do I have this semester?", RouteType.STRUCTURED, I.MY_COURSES),
    ("Which regulations apply to me?", RouteType.STRUCTURED, I.MY_PROFILE),
    ("When am I free today?", RouteType.STRUCTURED, I.FREE_TIME),
    ("Where is my next class?", RouteType.STRUCTURED, I.CLASSROOM),
    ("Who teaches Database Management Systems?", RouteType.STRUCTURED, I.FACULTY_FOR_COURSE),
    ("How many credits is ICS 213?", RouteType.STRUCTURED, I.COURSE_INFO),
    ("What is my CGPA?", RouteType.UNSUPPORTED, I.OUT_OF_SCOPE),
    ("What is the capital of France?", RouteType.UNSUPPORTED, I.OUT_OF_SCOPE),
    ("How do I pay my fees?", RouteType.UNSUPPORTED, I.OUT_OF_SCOPE),
])
def test_new_intents(query, route, intent):
    plan = classify(query)
    assert (plan.route, plan.structured_intent) == (route, intent), plan.reasoning


@pytest.mark.parametrize("query", [
    "What happens if my attendance is below 80%?",  # a rule, not "my attendance record"
    "Can I write a make-up exam if I miss the end semester exam?",  # a rule, not an exam date
    "What are the hostel curfew rules?",
    "How do I report ragging?",
])
def test_rule_questions_go_to_documents(query):
    assert classify(query).route == RouteType.SEMANTIC


def test_unmatched_questions_fall_back_to_documents_but_statements_do_not():
    assert classify("What is IT Workshop III?").hints.get("fallback") == "yes"
    assert classify("asdkfj qwer nonsense query").route == RouteType.UNSUPPORTED


def test_timetable_hints():
    assert classify("What is my first class tomorrow?").hints == {"focus": "first"}
    assert classify("Which labs do I have this week?").hints.get("entry_type") == "lab"
    assert classify("When is my Data Structures class this week?").hints.get("course_filter") == "Data Structures"


def test_broad_rule_questions_get_an_overview():
    assert classify("What are the hostel rules?").hints == {"overview": "hostel"}
    assert classify("What are the anti-ragging rules?").hints == {"overview": "anti-ragging"}


# ----------------------------------------------------------------- follow-ups

def _hist(*turns):
    return [{"role": r, "content": c} for r, c in turns]


def test_followup_course_from_previous_question():
    h = _hist(("user", "Tell me about ICS 211"), ("assistant", "Design and Analysis of Algorithms (ICS 211) ..."))
    assert followup.resolve("Who teaches it?", h) == "Who teaches ICS 211?"


def test_followup_course_from_previous_answer():
    h = _hist(("user", "What is my next class?"), ("assistant", "Your next class is **IT Workshop III (ICS 214)**"))
    assert followup.resolve("Who teaches it?", h) == "Who teaches ICS 214?"


def test_followup_person():
    h = _hist(("user", "What is Dr. Manu Madhavan's email?"), ("assistant", "manum@iiitkottayam.ac.in"))
    assert followup.resolve("What does he research?", h) == "What does Dr. Manu Madhavan research?"


def test_followup_ellipsis_swaps_the_meal():
    h = _hist(("user", "What's for lunch today?"), ("assistant", "Lunch: ..."))
    assert followup.resolve("And dinner?", h) == "What's for dinner today?"


def test_followup_leaves_complete_questions_alone():
    h = _hist(("user", "Tell me about ICS 211"), ("assistant", "..."))
    assert followup.resolve("What is the attendance requirement?", h) == "What is the attendance requirement?"
    assert followup.resolve("Who teaches ICS 213?", h) == "Who teaches ICS 213?"
    assert followup.resolve("Who teaches it?", []) == "Who teaches it?"


# ----------------------------------------------------------------- passages

def _snip(content, title="UG Regulations (2021-25 batch)", rank=1.0, dtype="regulations"):
    return SemanticSnippet(content=content, document_title=title, section_title=None, page_start=7, page_end=7,
                           similarity=rank, cohort="21-25", category=None, document_type=dtype,
                           valid_from=None, valid_until=None)


REGS = ("R.5.0 Attendance and Course Feedback R.5.1 Students are expected to attend all the classes. Students should "
        "have minimum 80% attendance. R.5.2 The incomplete grade I is a transitional grade which will be given to "
        "students who miss the end semester examinations under exceptional circumstances. R.5.3 Students having an "
        "attendance percentage between 65% to 80% may be permitted to continue by paying a nominal penalty. Students "
        "having an attendance percentage less than 65 will be awarded L grade.")


def test_picks_the_clause_that_answers():
    passages, confidence = documents.best_passages("What is an incomplete grade?", [_snip(REGS)])
    assert passages[0].text.startswith("R.5.2")
    assert passages[0].section_title == "R.5.2"
    assert confidence >= 0.5


def test_below_threshold_question_finds_the_consequence_rule():
    passages, _ = documents.best_passages("What happens if my attendance is below 80%?", [_snip(REGS)])
    assert "L grade" in passages[0].text


def test_list_lead_in_keeps_the_list():
    text = ("b) The Committee may award one or more of the following punishments, namely; "
            "i. Suspension from attending classes. ii. Debarring from appearing in any examination. "
            "iii. Expulsion from the hostel.")
    passages, _ = documents.best_passages("What is the punishment for ragging?", [_snip(text, "UGC Anti-Ragging Regulations (2009)", dtype="policy")])
    assert "Suspension" in passages[0].text


def test_clean_text_removes_pdf_debris():
    dirty = "Students should have at- tendance (cid:80) IIIT Kottayam, Kerala IIITK/Acad/Reg./Ver.VII/Senate - 7/22 ok"
    clean = documents.clean_text(dirty)
    assert "attendance" in clean and "(cid" not in clean and "IIITK/Acad" not in clean


def test_times_are_not_mistaken_for_clause_numbers():
    units = documents._units("35. Silence Hours Silence hours will be observed from 11 PM to 6.00 AM on all days.")
    assert any("6.00 AM on all days" in u for u in units)


def test_nothing_relevant_means_no_passage():
    assert documents.best_passages("what is the", [_snip(REGS)]) == ([], 0.0)


# ----------------------------------------------------------------- calendar

EVENTS = [
    {"id": 9, "event_name": "Mid Semester Examination Starts", "event_date": "2026-09-02", "event_type": "exam"},
    {"id": 18, "event_name": "Class Ends", "event_date": "2026-10-26", "event_type": "term_milestone"},
    {"id": 19, "event_name": "End Semester Examination Starts", "event_date": "2026-10-28", "event_type": "exam"},
    {"id": 20, "event_name": "End Semester Exam Ends & Semester Ends", "event_date": "2026-11-13", "event_type": "exam"},
    {"id": 11, "event_name": "Second Class Committee Meeting (S3, S5 & S7)", "event_date": "2026-09-23", "event_type": "meeting"},
    {"id": 23, "event_name": "Result Publication", "event_date": "2026-12-03", "event_type": "result"},
]


@pytest.fixture
def calendar(monkeypatch):
    monkeypatch.setattr(campus, "calendar_events", lambda client: [dict(e, status="active", source_id="cal.pdf") for e in EVENTS])
    monkeypatch.setattr(campus, "today_ist", lambda: date(2026, 9, 22))


def _picked(query):
    return [f.data["event_name"] for f in campus.academic_calendar(None, query).facts]


def test_end_sem_is_never_confused_with_mid_sem(calendar):
    assert _picked("When do the end semester exams start?") == [
        "End Semester Examination Starts", "End Semester Exam Ends & Semester Ends"]


def test_calendar_phrasings(calendar):
    assert _picked("When is the last instructional day?") == ["Class Ends"]
    assert _picked("When will results be published?") == ["Result Publication"]
    assert _picked("When do mid semester exams start?") == ["Mid Semester Examination Starts"]


def test_upcoming_lists_future_events_only(calendar):
    names = _picked("What's coming up on the academic calendar?")
    assert "Mid Semester Examination Starts" not in names and names[0].startswith("Second Class Committee")


# ----------------------------------------------------------------- formatting

def test_formatting_helpers():
    assert compose.fmt_range("10:00:00", "10:55:00") == "10:00–10:55 AM"
    assert compose.fmt_range("11:05:00", "12:00:00") == "11:05 AM – 12:00 PM"
    assert compose.nice_title("DESIGN AND ANALYSIS OF ALGORITHMS") == "Design and Analysis of Algorithms"
    assert compose.nice_title("IT WORKSHOP III") == "IT Workshop III"
    assert compose.nice_title("SAHYADRI HOSTEL (GIRLS)") == "Sahyadri Hostel (Girls)"
    assert compose.person("Dr.Priyadharshini S") == "Dr. Priyadharshini S"


def test_empty_day_is_answered_not_errored():
    ctx = GroundedContext(query="Do I have any class on Sunday?", route=RouteType.STRUCTURED, facts=[], snippets=[],
                          warnings=["no active, valid entries"], has_answer=False,
                          plan=QueryPlan(raw_query="", route=RouteType.STRUCTURED,
                                         structured_intent=I.DAY_OF_WEEK_TIMETABLE, topic_text="Sunday"))
    assert compose.compose(ctx).startswith("You have no classes on Sunday")


def test_out_of_scope_never_invents_a_record():
    ctx = GroundedContext(query="What is my CGPA?", route=RouteType.UNSUPPORTED, facts=[], snippets=[], warnings=[],
                          has_answer=False, plan=classify("What is my CGPA?"))
    reply = compose.compose(ctx)
    assert "doesn't store" in reply and not any(ch.isdigit() for ch in reply)


def test_only_the_students_own_regulations_say_they_apply():
    assert "apply to you" in compose._cohort_label("UG Regulations (2021-25 batch)", "21-25", "regulations")
    assert "apply to you" not in compose._cohort_label("Hostel Rules and Regulations (July 2026)", "21-25", "policy")


def test_requirement_question_prefers_the_clause_with_the_number():
    """Regression (smoke test, 2026-09-22): R.5.2 mentions "attendance
    requirements" but R.5.1 states the 80% rule — the rule must win."""
    passages, _ = documents.best_passages("What is the attendance requirement?", [_snip(REGS)])
    assert "80% attendance" in passages[0].text
