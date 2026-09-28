"""Offline tests for the CR upload workflow (2026-09-28):
backend/cr_ingest/ (rules, timetable drafts, pipeline), the CR/admin API
decisions, class-scoped announcement visibility, and quiz/assignment
questions reaching class notices.

The database side (RLS on announcements/approval_requests/storage, the
submit/review/archive RPCs) is verified against the live project inside a
rolled-back transaction — see docs/cr-workflow.md §Verification.
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
from cr_ingest import pipeline, rules, timetable_draft as td, vision  # noqa: E402
from query import campus, compose, router  # noqa: E402
from query.types import GroundedContext, RouteType, StructuredFact, StructuredIntent  # noqa: E402

TODAY = date(2026, 9, 28)  # a Monday
CR_PROFILE = {"id": "u-cr", "role": "CR", "semester": 5, "programme": "B.Tech",
              "department": "COMPUTER SCIENCE AND ENGINEERING", "batch": "III", "section": "III"}


# ------------------------------------------------------------------ fakes

class _Q:
    def __init__(self, fake, name):
        self.fake, self.name = fake, name

    def __getattr__(self, _):
        return lambda *a, **k: self

    def insert(self, row):
        self.fake.inserted.append((self.name, row))
        return _Q(self.fake, "_inserted")

    def execute(self):
        if self.name == "_inserted":
            return SimpleNamespace(data=[{"id": 99}])
        return SimpleNamespace(data=self.fake.tables.get(self.name, []))


class FakeDB:
    def __init__(self, **tables):
        self.tables = tables
        self.inserted: list = []
        self.rpcs: list = []

    def table(self, name):
        return _Q(self, name)

    def rpc(self, name, params=None):
        self.rpcs.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={"success": True, "id": 7, "status": "pending"}))


COURSES = [
    {"id": 1, "course_code": "CSE 311", "course_name": "ARTIFICIAL INTELLIGENCE", "semester": 5},
    {"id": 2, "course_code": "CSE 312", "course_name": "SOFTWARE ARCHITECTURE", "semester": 5},
    {"id": 3, "course_code": "IEG 313", "course_name": "DIGITAL SIGNAL PROCESSING", "semester": 5},
]
FACULTY = [
    {"id": 10, "full_name": "Dr. Ansith S", "initials": "ATS", "status": "active"},
    {"id": 11, "full_name": "Dr. Athira B", "initials": "AB", "status": "active"},
]


def directory() -> td.Directory:
    return td.Directory.load(FakeDB(courses=COURSES, faculty=FACULTY))


def period(day=1, start="09:30", end="10:25", code="CSE 311", fac=("ATS",), etype="class", lab=None):
    return {"day_of_week": day, "start_time": start, "end_time": end, "course_code": code,
            "faculty_initials": list(fac), "entry_type": etype, "lab_batch": lab}


# ------------------------------------------------------------------ rules

@pytest.mark.parametrize("text, category", [
    ("DSA quiz on 12 Oct at 10:30 AM", "QUIZ"),
    ("Mid sem exam of CSE 311 on 05/10/2026", "EXAM"),
    ("Assignment 3 due by Friday", "ASSIGNMENT"),
    ("OS class cancelled tomorrow", "CLASS_UPDATE"),
    ("Extra class on Saturday 2pm", "CLASS_UPDATE"),
    ("Last date for course registration is 3 Oct", "DEADLINE"),
    ("Attendance will be taken in every lecture", "ACADEMIC"),
    ("Coding club meet-up this evening", "CLUB"),
    ("Hackathon registrations open", "EVENT"),
    ("Flat 50% off on Udemy courses, buy now", "ADVERTISEMENT"),
    ("Hostel water supply off on Oct 3", "GENERAL"),
])
def test_category(text, category):
    assert rules.classify_category(text) == category


def test_promotional_words_do_not_hide_an_academic_notice():
    assert rules.classify_category("Quiz on Monday. 20% off at the canteen after!") == "QUIZ"


@pytest.mark.parametrize("text, found", [
    ("Call 9876543210 for details", "a personal phone number"),
    ("Aadhaar 2345 6789 0123 needed", "an Aadhaar-like 12-digit number"),
    ("Portal password: hunter2", "a password or OTP"),
    ("Pay to IFSC SBIN0001234", "bank account details"),
])
def test_sensitive(text, found):
    assert found in rules.sensitive_findings(text)


def test_clean_notice_has_no_findings():
    assert rules.sensitive_findings("CSE 311 quiz on 14 Oct 2026 at 10:30 AM in LH-2") == []


@pytest.mark.parametrize("text, expected", [
    ("quiz on 14 October 2026", date(2026, 10, 14)),
    ("quiz on Oct 14", date(2026, 10, 14)),
    ("quiz on 14/10/2026", date(2026, 10, 14)),
    ("quiz on 2026-10-14", date(2026, 10, 14)),
    ("quiz tomorrow", date(2026, 9, 29)),
    ("quiz on Friday", date(2026, 10, 2)),
    ("quiz next Monday", date(2026, 10, 5)),
    ("quiz on 3 Jan", date(2027, 1, 3)),  # no year: the next 3 January
    ("no date here", None),
])
def test_dates(text, expected):
    assert rules.extract_date(text, TODAY) == expected


def test_times():
    assert str(rules.extract_time("at 10:30 AM")) == "10:30:00"
    assert str(rules.extract_time("at 2pm")) == "14:00:00"
    assert str(rules.extract_time("from 14:15")) == "14:15:00"


def test_draft_expiry_and_title():
    d = rules.draft_announcement("NOTICE\nAI quiz 2 on 14 Oct 2026 at 10:30 AM", TODAY, title="NOTICE")
    assert d.title == "AI quiz 2 on 14 Oct 2026 at 10:30 AM"  # a bare "NOTICE" heading says nothing
    assert d.category == "QUIZ" and d.event_date == "2026-10-14" and d.event_time == "10:30"
    assert d.valid_until == "2026-10-15" and d.auto_publish
    undated = rules.draft_announcement("Assignment 4 has been uploaded", TODAY)
    assert undated.valid_until == "2026-10-12"  # two weeks
    assert rules.default_valid_until(date(2027, 3, 1), TODAY) == date(2026, 11, 27)  # 60-day ceiling


def test_sensitive_academic_notice_is_not_auto_published():
    d = rules.draft_announcement("Quiz tomorrow. Contact 9876543210", TODAY)
    assert d.category == "QUIZ" and not d.auto_publish


def test_academic_categories_match_the_database_function():
    sql = (ROOT / "supabase/migrations/20260928150000_cr_upload_workflow.sql").read_text()
    for c in rules.ACADEMIC_CATEGORIES:
        assert f"'{c}'" in sql


# ------------------------------------------------------- timetable drafts

@pytest.mark.parametrize("raw, expected", [
    ("9.30", "09:30"), ("9:30 AM", "09:30"), ("2 pm", "14:00"), ("14:00", "14:00"),
    ("2:30", "14:30"),  # a bare 1-7 o'clock is afternoon
    ("12:30 PM", "12:30"), ("25:00", None), ("soon", None),
])
def test_norm_time(raw, expected):
    assert td.norm_time(raw) == expected


def test_norm_day():
    assert td.norm_day("Monday") == 1 and td.norm_day("wed") == 3 and td.norm_day(6) == 6
    assert td.norm_day("x") is None and td.norm_day(9) is None


def test_type_markers_and_codes_are_split():
    d = directory()
    lab = td.normalise({"day": "Tue", "start_time": "11:30", "end_time": "13:25", "course_code": "CSE 312 LAB"}, d)
    assert lab["course_code"] == "CSE 312" and lab["entry_type"] == "lab"
    tut = td.normalise({"day": "Tue", "start_time": "9:30", "end_time": "10:25", "course_code": "CSE311 (T)",
                        "faculty_initials": "ATS (T)"}, d)
    assert tut["course_code"] == "CSE 311" and tut["entry_type"] == "tutorial" and tut["faculty_initials"] == ["ATS"]
    two = td.normalise({"day": 1, "start_time": "9:30", "end_time": "10:25", "course_code": "IEG 311/313"}, d)
    assert two["course_code"] == "IEG 311/313"  # two codes: the CR decides, nothing is guessed


def test_check_reports_instead_of_guessing():
    entries, issues = td.check([
        period(),
        period(day=2, code="XYZ 999"),
        period(day=3, fac=("QQ",)),
        period(day=4, code=None, fac=()),
        period(day=5, fac=("ATS", "DSP")),  # DSP = Digital Signal Processing, not a person
    ], directory())
    msgs = {(i.index, i.severity, i.message) for i in issues}
    assert entries[0]["course_name"] == "ARTIFICIAL INTELLIGENCE" and entries[0]["faculty_names"] == ["Dr. Ansith S"]
    assert (1, "error", '"XYZ 999" isn\'t in the course catalogue.') in msgs
    assert (2, "error", 'No faculty member has the initials "QQ".') in msgs
    assert (3, "error", "A class needs a course code.") in msgs
    assert entries[4]["faculty_initials"] == ["ATS"]
    assert any(i.index == 4 and i.severity == "warning" and "DSP" in i.message for i in issues)
    assert td.blocking(issues)


def test_overlaps():
    _, clash = td.check([period(), period(start="10:00", end="10:55", code="CSE 312", fac=("AB",))], directory())
    assert any(i.severity == "error" and "Overlaps" in i.message for i in clash)
    _, labs = td.check([period(etype="lab", lab=1), period(code="CSE 312", fac=("AB",), etype="lab", lab=2)], directory())
    assert not labs  # batch 1 and batch 2 in different labs at the same time
    _, club = td.check([period(start="16:30", end="17:25"),
                        period(start="17:00", end="18:30", code=None, fac=(), etype="club_activity")], directory())
    assert club and all(i.severity == "warning" for i in club)  # the institute's own timetables do this


def test_untimed_activity_is_a_warning_but_an_untimed_class_is_an_error():
    _, issues = td.check([{"day_of_week": 6, "entry_type": "sports", "source_text": "Sports"}], directory())
    assert issues and not td.blocking(issues)
    _, issues = td.check([period(start=None, end=None)], directory())
    assert td.blocking(issues)


def test_breaks_are_dropped_and_storable_keeps_only_canonical_fields():
    entries, _ = td.check([period(), {**period(code=None, fac=()), "entry_type": "break"}], directory())
    assert len(entries) == 1
    stored = td.storable(entries)[0]
    assert "course_name" not in stored and "faculty_names" not in stored and stored["course_code"] == "CSE 311"


def test_diff():
    cur = [period(), period(day=2), period(day=3)]
    new = [period(), period(day=2, fac=("AB",)), period(day=4)]
    d = td.diff(cur, new)
    assert (len(d["added"]), len(d["removed"]), len(d["changed"]), d["unchanged"]) == (1, 1, 1, 1)


def test_institute_pdf_is_read_without_any_model():
    pdf = ROOT / "Data/Structured/Semester 5_Timetable_Odd_2026.pdf"
    if not pdf.exists():
        pytest.skip("source PDF not in this checkout")
    found = td.from_institute_pdf(pdf.read_bytes(), pipeline.class_of(CR_PROFILE))
    assert found is not None and len(found["entries"]) == 36 and len(found["classes"]) == 13
    other = td.from_institute_pdf(pdf.read_bytes(), {**pipeline.class_of(CR_PROFILE), "semester": 3})
    assert other is not None and other["entries"] == []


# ---------------------------------------------------------------- pipeline

def test_sniff():
    assert pipeline.sniff(b"%PDF-1.7 ...") == "application/pdf"
    assert pipeline.sniff(b"\xff\xd8\xff\xe0....") == "image/jpeg"
    assert pipeline.sniff(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert pipeline.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    for bad in (b"", b"MZ\x90\x00 an exe", b"%PDF-" + b"0" * (pipeline.MAX_BYTES + 1)):
        with pytest.raises(pipeline.UploadRejected):
            pipeline.sniff(bad)


def test_class_comes_from_the_profile():
    assert pipeline.class_of(CR_PROFILE)["section"] == "III"
    assert pipeline.class_of({"role": "CR"}) is None


def _vision(monkeypatch, out):
    monkeypatch.setattr(vision, "extract", lambda data, mime, class_hint=None: out)


def test_photo_of_a_notice(monkeypatch):
    _vision(monkeypatch, {"kind": "announcement", "confidence": 0.95, "text": "…",
                          "announcement_title": "NOTICE",
                          "announcement_body": "CSE 311 quiz 2 on 14 October 2026 at 10:30 AM in LH-2."})
    d = pipeline.process(FakeDB(), CR_PROFILE, b"\xff\xd8\xff\xe0fake", TODAY).to_dict()
    a = d["announcement"]
    assert d["kind"] == "announcement" and d["method"] == "vision"
    assert a["category"] == "QUIZ" and a["event_date"] == "2026-10-14" and a["auto_publish"]


def test_photo_of_a_timetable_uses_the_legend(monkeypatch):
    _vision(monkeypatch, {
        "kind": "timetable", "confidence": 0.9, "text": "…", "class_label": "SEMESTER V CSE BATCH-III",
        "entries": [{"day": "Monday", "start_time": "9:30", "end_time": "10:25", "course_code": "CSE 311",
                     "faculty_initials": [], "entry_type": "class"},
                    {"day": "Tuesday", "start_time": "11:30", "end_time": "13:25", "course_code": "CSE 312 LAB",
                     "faculty_initials": ["AB"], "entry_type": "class"}],
        "legend": [{"course_code": "CSE 311", "course_name": "Artificial Intelligence", "faculty_initials": "ATS"}],
    })
    db = FakeDB(courses=COURSES, faculty=FACULTY, timetable_entries=[])
    tt = pipeline.process(db, CR_PROFILE, b"\x89PNG\r\n\x1a\nfake", TODAY).to_dict()["timetable"]
    assert tt["can_submit"], tt["issues"]
    assert tt["entries"][0]["faculty_initials"] == ["ATS"]  # from the page's own legend
    assert tt["entries"][1]["entry_type"] == "lab"
    assert "It will be submitted for Semester 5" in tt["notes"][0]


def test_unreadable_image_without_vision_is_a_clear_refusal(monkeypatch):
    def down(*a, **k):
        raise vision.VisionUnavailable("quota exhausted")
    monkeypatch.setattr(vision, "extract", down)
    with pytest.raises(pipeline.UploadRejected, match="type the announcement instead"):
        pipeline.process(FakeDB(), CR_PROFILE, b"\xff\xd8\xff\xe0fake", TODAY)


def test_timetable_photo_needs_a_class(monkeypatch):
    _vision(monkeypatch, {"kind": "timetable", "confidence": 0.9, "text": "", "entries": []})
    with pytest.raises(pipeline.UploadRejected, match="academic profile"):
        pipeline.process(FakeDB(), {"id": "u", "role": "CR"}, b"\xff\xd8\xff\xe0fake", TODAY)


# ------------------------------------------------------------ API decisions

def _as(monkeypatch, profile, db):
    def fake_require_role(request, allowed):
        if profile["role"] not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return db, profile
    monkeypatch.setattr(cr_api, "require_role", fake_require_role)
    monkeypatch.setattr(cr_api, "today_ist", lambda: TODAY)


def _post(**kw):
    from app.schemas import ClassAnnouncementRequest
    return ClassAnnouncementRequest(**{"title": "AI quiz 2", "content": "Quiz on 14 Oct 2026 at 10:30 AM", **kw})


def test_cr_academic_notice_goes_live_scoped_to_their_class(monkeypatch):
    db = FakeDB()
    _as(monkeypatch, CR_PROFILE, db)
    out = cr_api.submit_announcement(_post(event_date="2026-10-14"), request=None)
    assert out["status"] == "active" and out["auto_published"]
    row = db.inserted[0][1]
    assert (row["semester"], row["department"], row["section"]) == (5, "COMPUTER SCIENCE AND ENGINEERING", "III")
    assert row["valid_until"].startswith("2026-10-15") and row["source_kind"] == "typed"


def test_cr_event_or_sensitive_notice_waits_for_an_admin(monkeypatch):
    db = FakeDB()
    _as(monkeypatch, CR_PROFILE, db)
    assert cr_api.submit_announcement(_post(title="Hackathon", content="Hackathon on Friday", category="EVENT"),
                                      request=None)["status"] == "pending"
    assert cr_api.submit_announcement(_post(content="Quiz tomorrow, call 9876543210"), request=None)["status"] == "pending"
    # pending notices are still locked to the CR's own class (batch-specific)
    assert all(r["status"] == "pending" and r["section"] == "III" and r["semester"] == 5 for _, r in db.inserted)


def test_cr_cannot_claim_someone_elses_upload(monkeypatch):
    _as(monkeypatch, CR_PROFILE, FakeDB())
    with pytest.raises(HTTPException) as exc:
        cr_api.submit_announcement(_post(upload_path="someone-else/file.pdf"), request=None)
    assert exc.value.status_code == 400


def test_auto_publish_expiry_is_capped(monkeypatch):
    db = FakeDB()
    _as(monkeypatch, CR_PROFILE, db)
    cr_api.submit_announcement(_post(valid_until="2027-06-01"), request=None)
    assert db.inserted[0][1]["valid_until"].startswith("2026-11-27")


def test_student_is_refused(monkeypatch):
    _as(monkeypatch, {**CR_PROFILE, "role": "STUDENT"}, FakeDB())
    with pytest.raises(HTTPException) as exc:
        cr_api.submit_announcement(_post(), request=None)
    assert exc.value.status_code == 403


def test_timetable_submit_blocks_on_errors_and_sends_only_canonical_fields(monkeypatch):
    db = FakeDB(courses=COURSES, faculty=FACULTY)
    _as(monkeypatch, CR_PROFILE, db)
    from app.schemas import TimetableSubmitRequest
    with pytest.raises(HTTPException) as exc:
        cr_api.submit_timetable(TimetableSubmitRequest(entries=[period(code="XYZ 999")]), request=None)
    assert exc.value.status_code == 400 and "XYZ 999" in exc.value.detail
    with pytest.raises(HTTPException):
        cr_api.submit_timetable(TimetableSubmitRequest(entries=[period()], valid_from="2026-01-01"), request=None)
    cr_api.submit_timetable(TimetableSubmitRequest(entries=[{**period(), "course_name": "forged"}]), request=None)
    name, params = db.rpcs[-1]
    assert name == "submit_cr_timetable" and "course_name" not in params["p_entries"][0]


def test_preview_explains_the_decision(monkeypatch):
    from app.schemas import AnnouncementPreviewRequest
    _as(monkeypatch, CR_PROFILE, FakeDB())
    live = cr_api.preview_announcement(AnnouncementPreviewRequest(content="Quiz on Friday"), request=None)
    assert live["decision"]["publish_now"] and live["category"] == "QUIZ"
    held = cr_api.preview_announcement(AnnouncementPreviewRequest(content="Club meet on Friday"), request=None)
    assert not held["decision"]["publish_now"] and "admin" in held["decision"]["reason"]


# ------------------------------------------------- visibility + questions

def test_class_notices_reach_only_that_class():
    row = {"semester": 5, "department": "COMPUTER SCIENCE AND ENGINEERING", "batch": "III", "section": "III"}
    assert campus.announcement_visible_to(row, CR_PROFILE)
    assert not campus.announcement_visible_to(row, {**CR_PROFILE, "section": "I", "batch": "I"})
    assert campus.announcement_visible_to({"semester": None, "department": None}, {"semester": 3})
    assert campus.announcement_visible_to(row, {"role": "ADMIN"})


@pytest.mark.parametrize("q, kind", [
    ("when is the quiz?", "QUIZ"),
    ("is there any quiz this week", "QUIZ"),
    ("when is the DSA assignment due", "ASSIGNMENT"),
    ("is class cancelled tomorrow", "CLASS_UPDATE"),
    ("extra class on saturday?", "CLASS_UPDATE"),
    ("any updates from my CR", "NOTICE"),
])
def test_notice_questions_route_to_class_announcements(q, kind):
    plan = router.classify(q)
    assert plan.structured_intent == StructuredIntent.ANNOUNCEMENTS and plan.hints.get("notice") == kind


def test_rule_questions_still_go_to_the_regulations():
    assert router.classify("what are the rules for late assignment submission").route == RouteType.SEMANTIC


def _ctx(facts, notice):
    plan = router.classify({"QUIZ": "when is the quiz?"}.get(notice, "any announcements?"))
    return GroundedContext(query="", route=RouteType.STRUCTURED, facts=facts, snippets=[], warnings=[],
                           has_answer=bool(facts), plan=plan)


def test_quiz_answer_leads_with_the_date():
    fact = StructuredFact(claim="AI quiz 2", source="announcements", data={
        "title": "AI quiz 2", "content": "Units 3-4, LH-2", "event_date": "2026-10-14", "event_time": "10:30:00",
        "auto_published": True})
    text = compose.compose_announcements(_ctx([fact], "QUIZ"))
    assert text.startswith("**AI quiz 2** — **Wednesday, 14 October** at 10:30 AM")
    assert "posted by your CR" in text


def test_no_quiz_is_an_honest_answer():
    assert compose.compose_announcements(_ctx([], "QUIZ")).startswith("No quiz has been posted for your class")
