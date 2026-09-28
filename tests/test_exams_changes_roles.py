"""Offline tests for round 3 of the CR/admin workflow (2026-09-28):
exam schedules from uploads (backend/cr_ingest/exam_draft.py), one-off class
changes (cr_ingest/class_changes.py + query/schedule.py), their effect on
schedule / exam answers, and the API rules (CR target ignored, admin
publishes directly, notices locked to the CR's class).

The database rules (RLS, submit/review RPCs, admin_set_role) are verified
against the live project in rolled-back transactions — docs/cr-workflow.md.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api import cr as cr_api  # noqa: E402
from app.schemas import ClassAnnouncementRequest, ExamSubmitRequest, TargetClass, TimetableSubmitRequest  # noqa: E402
from cr_ingest import class_changes as ccx, exam_draft as ed, pipeline, timetable_draft as td  # noqa: E402
from query import compose, router, schedule  # noqa: E402
from query.types import GroundedContext, RouteType, StructuredFact, StructuredIntent  # noqa: E402

TODAY = date(2026, 9, 28)  # Monday
EXAM_PDF = ROOT / "AI-Tests" / "END_EXAM SEM V-OCT_ODD_2026.pdf"
S5 = ["AI AND DATA SCIENCE", "COMPUTER SCIENCE AND ENGINEERING", "CYBER SECURITY", "ELECTRONICS AND COMMUNICATION ENGINEERING"]
CR = {"id": "u-cr", "role": "CR", "semester": 5, "programme": "B.Tech", "department": "COMPUTER SCIENCE AND ENGINEERING",
      "batch": "III", "section": "III"}
ADMIN = {"id": "u-ad", "role": "ADMIN"}


# ------------------------------------------------------------------ fakes

class _Q:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def __getattr__(self, _):
        return lambda *a, **k: self

    def insert(self, row):
        self.db.inserted.append((self.name, row))
        return _Q(self.db, "_inserted")

    def execute(self):
        if self.name == "_inserted":
            return SimpleNamespace(data=[{"id": 1}])
        return SimpleNamespace(data=self.db.tables.get(self.name, []))


class FakeDB:
    def __init__(self, **tables):
        self.tables = tables
        self.inserted, self.rpcs = [], []

    def table(self, name):
        return _Q(self, name)

    def rpc(self, name, params=None):
        self.rpcs.append((name, params))
        data = {"orion_class_options": [{"programme": "B.Tech", "semester": 5, "department": d, "section": "I"} for d in S5]}
        out = data.get(name, {"success": True, "id": 42, "status": "pending", "inserted": 1})
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=out))


COURSES = [{"id": 1, "course_code": "CSE 311", "course_name": "ARTIFICIAL INTELLIGENCE", "semester": 5},
           {"id": 2, "course_code": "IHS 311", "course_name": "HUMAN RESOURCE MANAGEMENT", "semester": 5}]


def _as(monkeypatch, profile, db):
    def fake_require_role(request, allowed):
        if profile["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return db, profile
    monkeypatch.setattr(cr_api, "require_role", fake_require_role)
    monkeypatch.setattr(cr_api, "today_ist", lambda: TODAY)


# ------------------------------------------------------------ exam reading

@pytest.mark.skipif(not EXAM_PDF.exists(), reason="sample exam PDF not in this checkout")
def test_reads_the_real_exam_pdf():
    entries, notes, text = ed.from_pdf(EXAM_PDF.read_bytes(), TODAY)
    assert len(entries) == 33  # 8 days x 4 departments + 2 alternatives - 1 empty cell
    assert ed.parse_title(text) == {"exam_type": "end_sem", "semester": 5}
    assert any("12.30 AM" in n for n in notes)
    assert {e["end_time"] for e in entries} == {"12:30"}
    alt = [e for e in entries if e["alt_group"] == "IEG311/IEG313"]
    assert len(alt) == 4 and {e["course_code"] for e in alt} == {"IEG 311", "IEG 313"}
    mine, _ = ed.scope_entries(entries, "COMPUTER SCIENCE AND ENGINEERING", S5)
    assert len(mine) == 9 and {e["department"] for e in mine} == {"COMPUTER SCIENCE AND ENGINEERING"}
    everyone, _ = ed.scope_entries(entries, None, S5)
    assert {e["department"] for e in everyone} == set(S5)  # "CSE WITH SPECIALISATION IN CYBER SECURITY" -> "CYBER SECURITY"


@pytest.mark.parametrize("text, expected", [
    ("09.30 AM-12.30 AM", ("09:30", "12:30")),
    ("2.00 PM - 5.00 PM", ("14:00", "17:00")),
    ("10:00-13:00", ("10:00", "13:00")),
    ("9:30 to 12:30", ("09:30", "12:30")),
    ("FN", ("09:30", "12:30")),
    ("AN", ("14:00", "17:00")),
])
def test_time_ranges(text, expected):
    assert ed.parse_time_range(text)[:2] == expected


def test_supply_chain_is_not_a_supplementary_exam():
    assert ed.parse_title("END SEMESTER EXAMINATION - SEMESTER V\nIHS313 Operations and Supply Chain Management")["exam_type"] == "end_sem"
    assert ed.parse_title("SUPPLEMENTARY EXAMINATION DEC 2026")["exam_type"] == "repeat"
    assert ed.parse_title("Mid Semester Exam - Sem III")["exam_type"] == "mid_sem"


def test_list_layouts():
    rows, _ = ed.from_tables([[["Date", "Time", "Course"],
                               ["14-10-2026", "10:00-11:00", "CSE311 Artificial Intelligence"],
                               ["16/10/2026", "2.00 PM-3.00 PM", "IHS 311 HRM"]]], TODAY)
    assert [(r["exam_date"], r["start_time"], r["course_code"]) for r in rows] == [
        ("2026-10-14", "10:00", "CSE 311"), ("2026-10-16", "14:00", "IHS 311")]
    text_rows, _ = ed.from_text("Quiz\n14 Oct 2026 10:00-11:00 CSE311 Artificial Intelligence", TODAY)
    assert text_rows[0]["exam_date"] == "2026-10-14" and text_rows[0]["course_code"] == "CSE 311"


def test_department_keys():
    assert ed.dept_key("CSE WITH SPECIALISATION IN CYBER SECURITY") == ed.dept_key("CYBER SECURITY") == "cyber"
    assert ed.dept_key("CSE WITH SPECIALISATION IN AI & DATA SCIENCE") == ed.dept_key("AI AND DATA SCIENCE") == "aids"
    assert ed.dept_key("ELECTRONICS AND\nCOMMUNICATION ENGINEERING") == "ece"


def test_exam_checks():
    directory = td.Directory.load(FakeDB(courses=COURSES, faculty=[]))
    rows, issues = ed.check([
        {"exam_date": "2026-10-28", "start_time": "09:30", "end_time": "12:30", "course_code": "CSE311", "department": "X"},
        {"exam_date": "2026-10-28", "start_time": "10:00", "end_time": "11:00", "course_code": "IHS 311", "department": "X"},
        {"exam_date": "2026-09-01", "start_time": "09:30", "end_time": "12:30", "course_code": "ZZZ 999", "department": "X"},
        {"exam_date": None, "start_time": "12:30", "end_time": "09:30", "course_code": "", "department": "X"},
    ], directory, TODAY)
    assert rows[0]["course_code"] == "CSE 311" and rows[0]["course_name"] == "ARTIFICIAL INTELLIGENCE"
    msgs = {(i.index, i.severity, i.field) for i in issues}
    assert (1, "warning", "time") in msgs            # clash with CSE 311, same department and day
    assert (2, "warning", "exam_date") in msgs       # already passed
    assert (2, "warning", "course_code") in msgs     # not in the catalogue: saved as printed
    assert {(3, "error", "exam_date"), (3, "error", "time"), (3, "error", "course_code")} <= msgs


def test_alternatives_do_not_clash():
    directory = td.Directory.load(FakeDB(courses=COURSES, faculty=[]))
    _, issues = ed.check([
        {"exam_date": "2026-11-04", "start_time": "09:30", "end_time": "12:30", "course_code": "IEG 311", "department": "X", "alt_group": "IEG311/IEG313"},
        {"exam_date": "2026-11-04", "start_time": "09:30", "end_time": "12:30", "course_code": "IEG 313", "department": "X", "alt_group": "IEG311/IEG313"},
    ], directory, TODAY)
    assert not [i for i in issues if i.field == "time"]


def test_exam_upload_is_not_an_announcement(monkeypatch):
    if not EXAM_PDF.exists():
        pytest.skip("sample exam PDF not in this checkout")
    db = FakeDB(courses=COURSES, faculty=[], exams=[])
    draft = pipeline.process(db, CR, EXAM_PDF.read_bytes(), TODAY).to_dict()
    assert draft["kind"] == "exam_timetable" and draft["method"] == "layout"
    assert draft["exams"]["scope_label"] == "Semester 5 · COMPUTER SCIENCE AND ENGINEERING"
    assert draft["exams"]["exam_type"] == "end_sem" and len(draft["exams"]["entries"]) == 9
    wrong_sem = pipeline.process(db, {**CR, "semester": 3}, EXAM_PDF.read_bytes(), TODAY).to_dict()["exams"]
    assert not wrong_sem["can_submit"] and "semester 5" in wrong_sem["issues"][0]["message"]
    admin = pipeline.process(db, ADMIN, EXAM_PDF.read_bytes(), TODAY).to_dict()["exams"]
    assert admin["scope"]["department"] is None and len(admin["entries"]) == 33 and len(admin["departments"]) == 4


# ----------------------------------------------------------- class changes

WEEK = [{"day_of_week": 2, "start_time": "09:00:00", "end_time": "09:55:00", "course_code": "ICS 212"},
        {"day_of_week": 3, "start_time": "10:00:00", "end_time": "10:55:00", "course_code": "ICS 214"},
        {"day_of_week": 5, "start_time": "11:05:00", "end_time": "12:00:00", "course_code": "ICS 211"}]
COURSE_LIST = [{"course_code": "ICS 211", "course_name": "Design and Analysis of Algorithms"},
               {"course_code": "ICS 212", "course_name": "Theory of Computation"},
               {"course_code": "ICS 214", "course_name": "IT Workshop III"}]


@pytest.mark.parametrize("text, kind, code, date_, new", [
    ("Theory of Computation class cancelled tomorrow", "cancel", "ICS 212", "2026-09-29", None),
    ("ICS 214 class on Wednesday is moved to Saturday 10 AM", "reschedule", "ICS 214", "2026-09-30", ("2026-10-03", "10:00", "10:55")),
    ("Extra DAA class on Friday at 4 PM to 5 PM", "extra", "ICS 211", "2026-10-02", ("2026-10-02", "16:00", "17:00")),
    ("TOC class rescheduled to 3pm tomorrow", "reschedule", "ICS 212", "2026-09-29", ("2026-09-29", "15:00", "15:55")),
])
def test_class_changes_from_text(text, kind, code, date_, new):
    found = ccx.extract(text, TODAY, WEEK, COURSE_LIST)
    c = found["changes"][0]
    assert (c["change_type"], c["course_code"], c["change_date"]) == (kind, code, date_)
    if new:
        assert (c["new_date"], c["new_start"], c["new_end"]) == new
    assert not ccx.check(found["changes"], WEEK, TODAY)


def test_permanent_changes_go_to_the_timetable_editor():
    found = ccx.extract("From now on the ICS 214 lab will be on Tuesdays", TODAY, WEEK, COURSE_LIST)
    assert found["permanent"] and not found["changes"]


def test_change_checks():
    msgs = [i.message for i in ccx.check([{"change_type": "cancel", "change_date": "2026-09-29", "course_code": "ICS 211"},
                                          {"change_type": "extra", "change_date": "2026-10-02", "course_code": "ICS 211",
                                           "new_start": "17:00", "new_end": "16:00"},
                                          {"change_type": "cancel", "change_date": "2027-06-01", "course_code": "ICS 212"}],
                                         WEEK, TODAY)]
    assert any("no ICS 211 on Tuesday" in m for m in msgs)
    assert any("must end after it starts" in m for m in msgs)
    assert any("next 90 days" in m for m in msgs)


def test_schedule_apply():
    tuesday = date(2026, 9, 29)
    entries = [{"course_code": "ICS 212", "start_time": "09:00:00", "end_time": "09:55:00", "day_of_week": 2},
               {"course_code": "ICS 213", "start_time": "10:00:00", "end_time": "10:55:00", "day_of_week": 2}]
    changes = [{"id": 1, "change_type": "reschedule", "change_date": "2026-09-29", "course_code": "ICS 212",
                "original_start": "09:00:00", "new_date": "2026-09-29", "new_start": "15:00:00", "new_end": "15:55:00"},
               {"id": 2, "change_type": "extra", "change_date": "2026-09-29", "course_code": "ICS 213",
                "new_date": "2026-09-29", "new_start": "16:00", "new_end": "17:00"}]
    out = schedule.apply(entries, changes, tuesday)
    assert out[0]["_cancelled"] and "moved to" in out[0]["_change_note"]
    moved = next(e for e in out if e.get("_moved_from"))
    assert (moved["start_time"], moved["course_code"]) == ("15:00:00", "ICS 212")
    assert next(e for e in out if e.get("_extra"))["start_time"] == "16:00:00"
    assert [e["course_code"] for e in schedule.active(out)] == ["ICS 213", "ICS 212", "ICS 213"]
    assert schedule.apply(entries, changes, date(2026, 9, 30)) == entries  # another day: untouched


def test_changes_only_for_the_right_class():
    rows = [{"semester": 3, "department": "CSE", "section": "I"}, {"semester": 3, "department": "CSE", "section": "II"}]
    assert schedule.for_class(rows, {"semester": 3, "department": "CSE", "section": "I"}) == [rows[0]]


def _ctx(q, facts):
    return GroundedContext(query=q, route=RouteType.STRUCTURED, facts=facts, snippets=[], warnings=[],
                           has_answer=bool(facts), plan=router.classify(q))


def test_day_answer_shows_cancellations():
    facts = [StructuredFact(claim="", source="t", data={"course_code": "ICS 212", "course_name": "THEORY OF COMPUTATION",
                                                       "start_time": "09:00:00", "end_time": "09:55:00", "_cancelled": True,
                                                       "_change_note": "cancelled"}),
             StructuredFact(claim="", source="t", data={"course_code": "ICS 213", "course_name": "DBMS",
                                                       "start_time": "10:00:00", "end_time": "10:55:00"})]
    text = compose.compose_day(_ctx("What classes do I have tomorrow?", facts), "tomorrow")
    assert "~~cancelled~~" in text and "1 change announced by your CR" in text
    free = compose.compose_free(_ctx("Am I free at 9?", facts), "tomorrow")
    assert free.startswith("Yes — you're free at 9 AM")  # the cancelled class frees the slot


# ------------------------------------------------------------ exam answers

def _exam(code, name, day, alt=None):
    return StructuredFact(claim="", source="exam schedule", data={
        "_exam": True, "course_code": code, "course_name": name, "exam_date": day, "start_time": "09:30:00",
        "end_time": "12:30:00", "exam_type": "end_sem", "alt_group": alt, "_asked_course": False})


def test_exam_answers():
    rows = [_exam("CSE 311", "Artificial Intelligence", "2026-10-28"), _exam("IEG 311", "Digital Signal Processing", "2026-11-04", "IEG311/IEG313")]
    listing = compose.compose_exam(_ctx("What is my exam schedule?", rows))
    assert listing.startswith("Your end-semester exam schedule (2 exams)") and "IEG311 / IEG313" in listing
    one = [_exam("CSE 311", "Artificial Intelligence", "2026-10-28")]
    one[0].data["_asked_course"] = True
    assert compose.compose_exam(_ctx("When is my AI exam?", one)).startswith(
        "Your **Artificial Intelligence** (CSE 311) end-semester exam is on **Wednesday, 28 October**")
    assert compose.compose_exam(_ctx("When is my next exam?", rows)).startswith("Your next exam is **Artificial Intelligence**")


@pytest.mark.parametrize("q, intent", [
    ("What is my exam schedule?", StructuredIntent.EXAM_SCHEDULE),
    ("When is my AI exam?", StructuredIntent.EXAM_SCHEDULE),
    ("When is my next exam?", StructuredIntent.EXAM_SCHEDULE),
    ("What classes do I have on 11 October?", StructuredIntent.DAY_OF_WEEK_TIMETABLE),
    ("When do the end semester exams start?", StructuredIntent.ACADEMIC_CALENDAR),
])
def test_routing(q, intent):
    assert router.classify(q).structured_intent == intent


# ----------------------------------------------------------------- API

def test_cr_target_is_ignored_and_admin_publishes(monkeypatch):
    db = FakeDB(courses=COURSES, faculty=[])
    _as(monkeypatch, CR, db)
    entry = {"day_of_week": 1, "start_time": "09:30", "end_time": "10:25", "course_code": "CSE 311", "faculty_initials": []}
    cr_api.submit_timetable(TimetableSubmitRequest(entries=[entry], target=TargetClass(semester=3, department="X", section="I")), request=None)
    assert db.rpcs[-1][0] == "submit_cr_timetable" and db.rpcs[-1][1]["p_target"] is None
    db = FakeDB(courses=COURSES, faculty=[])
    _as(monkeypatch, ADMIN, db)
    out = cr_api.submit_timetable(TimetableSubmitRequest(entries=[entry], target=TargetClass(
        semester=5, department="COMPUTER SCIENCE AND ENGINEERING", section="III")), request=None)
    assert [n for n, _ in db.rpcs] == ["submit_cr_timetable", "review_cr_timetable"] and out["published"]
    assert db.rpcs[0][1]["p_target"]["section"] == "III"


def test_exam_submit_rules(monkeypatch):
    db = FakeDB(courses=COURSES, faculty=[])
    _as(monkeypatch, CR, db)
    row = {"exam_date": "2026-10-28", "start_time": "09:30", "end_time": "12:30", "course_code": "CSE 311",
           "department": "CYBER SECURITY"}
    cr_api.submit_exams(ExamSubmitRequest(entries=[row], exam_type="end_sem"), request=None)
    name, params = db.rpcs[-1]
    assert name == "submit_exam_schedule" and params["p_entries"][0]["department"] == CR["department"]
    with pytest.raises(HTTPException):
        cr_api.submit_exams(ExamSubmitRequest(entries=[{**row, "course_code": ""}], exam_type="end_sem"), request=None)
    db = FakeDB(courses=COURSES, faculty=[])
    _as(monkeypatch, ADMIN, db)
    with pytest.raises(HTTPException):  # an admin must say which semester
        cr_api.submit_exams(ExamSubmitRequest(entries=[row], exam_type="end_sem"), request=None)
    out = cr_api.submit_exams(ExamSubmitRequest(entries=[row], exam_type="end_sem", target=TargetClass(semester=5)), request=None)
    assert [n for n, _ in db.rpcs] == ["submit_exam_schedule", "review_exam_schedule"] and out["published"]
    assert db.rpcs[0][1]["p_target"] == {"semester": 5, "programme": "B.Tech"}  # every department


def test_class_update_post(monkeypatch):
    db = FakeDB(timetable_entries=[{"day_of_week": 2, "start_time": "09:00:00", "end_time": "09:55:00", "entry_type": "class",
                                    "courses": {"course_code": "CSE 311", "course_name": "AI"}}])
    _as(monkeypatch, CR, db)
    body = ClassAnnouncementRequest(title="AI class cancelled", content="AI class cancelled tomorrow", category="CLASS_UPDATE",
                                    changes=[{"change_type": "cancel", "change_date": "2026-09-29", "course_code": "CSE 311"}])
    out = cr_api.submit_announcement(body, request=None)
    name, params = db.rpcs[-1]
    assert name == "post_class_update" and out["status"] == "active"
    assert (params["p_announcement"]["semester"], params["p_announcement"]["section"]) == (5, "III")
    assert params["p_changes"][0]["course_code"] == "CSE 311"
    bad = ClassAnnouncementRequest(title="x", content="x", category="CLASS_UPDATE",
                                   changes=[{"change_type": "cancel", "change_date": "2026-09-30", "course_code": "CSE 311"}])
    with pytest.raises(HTTPException):  # no CSE 311 on Wednesday
        cr_api.submit_announcement(bad, request=None)


def test_admin_can_post_to_everyone(monkeypatch):
    db = FakeDB()
    _as(monkeypatch, ADMIN, db)
    cr_api.submit_announcement(ClassAnnouncementRequest(title="Holiday", content="Campus closed on Friday", category="OFFICIAL",
                                                        everyone=True), request=None)
    row = db.inserted[-1][1]
    assert row["status"] == "active" and "section" not in row and "semester" not in row
