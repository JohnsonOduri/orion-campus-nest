"""Unit tests: strict validation rules and report shape."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.model import TimetableRecord  # noqa: E402
from backend.timetable.validator import validate_records  # noqa: E402

SOURCE = Path("Data/Structured/Semester 3_TimeTable_Odd_2026.pdf")


def make_record(**overrides) -> TimetableRecord:
    base = dict(
        programme="B.Tech",
        branch="CSE",
        semester=3,
        batch="I",
        section="I",
        day="Monday",
        slot_index=1,
        start_time="09:00",
        end_time="09:55",
        course_code="ICS 211",
        course_name="DESIGN AND ANALYSIS OF ALGORITHMS",
        faculty_initials=["PS"],
        faculty_names=["Dr. Priyadarshini"],
        source_id="s.pdf",
        source_page=1,
        valid_from="2026-08-01",
        valid_until="2026-11-30",
    )
    base.update(overrides)
    return TimetableRecord(**base)


@pytest.fixture
def existing_source(tmp_path):
    p = tmp_path / "timetable.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


class TestHappyPath:
    def test_valid_record_passes(self, existing_source):
        report = validate_records([make_record()], existing_source)
        assert report.ok
        assert report.summary() == {"total": 1, "passed": 1, "failed": 0, "ok": True}


class TestFailureRules:
    def test_invalid_day(self, existing_source):
        report = validate_records([make_record(day="Funday")], existing_source)
        assert not report.ok
        assert any(i.rule == "valid_day" for _, issues in report.failed for i in issues)

    @pytest.mark.parametrize(
        ("start", "end"),
        [(None, "10:00"), ("09:00", None), ("10:00", "09:00"), ("25:00", "26:00")],
    )
    def test_bad_time_ranges(self, existing_source, start, end):
        report = validate_records(
            [make_record(start_time=start, end_time=end)], existing_source
        )
        assert not report.ok
        rules = {i.rule for _, issues in report.failed for i in issues}
        assert rules & {"time_range", "valid_time", "time_order"}

    def test_unresolved_course(self, existing_source):
        rec = make_record(course_code="XXX 999", course_name=None)
        report = validate_records([rec], existing_source)
        assert not report.ok
        assert any(i.rule == "course_resolves" for _, iss in report.failed for i in iss)

    def test_unresolved_faculty(self, existing_source):
        rec = make_record(faculty_initials=[], faculty_names=[])
        report = validate_records([rec], existing_source)
        assert not report.ok
        rules = {i.rule for _, iss in report.failed for i in iss}
        assert rules & {"faculty_resolves", "faculty_names"}

    def test_invalid_entry_type(self, existing_source):
        report = validate_records([make_record(entry_type="lecture")], existing_source)
        assert not report.ok
        assert any(i.rule == "valid_entry_type" for _, iss in report.failed for i in iss)

    def test_missing_validity(self, existing_source):
        report = validate_records([make_record(valid_from="")], existing_source)
        assert not report.ok
        assert any(i.rule == "validity_dates" for _, iss in report.failed for i in iss)

    def test_validity_order(self, existing_source):
        report = validate_records(
            [make_record(valid_from="2026-12-01", valid_until="2026-08-01")],
            existing_source,
        )
        assert not report.ok
        assert any(i.rule == "validity_order" for _, iss in report.failed for i in iss)

    def test_incomplete_context(self, existing_source):
        report = validate_records([make_record(section="")], existing_source)
        assert not report.ok
        assert any(i.rule == "context" for _, iss in report.failed for i in iss)

    def test_missing_source_file(self, tmp_path):
        report = validate_records([make_record()], tmp_path / "nope.pdf")
        assert not report.ok
        assert any(i.rule == "source_exists" for _, iss in report.failed for i in iss)


class TestDuplicatesAndOverlaps:
    def test_exact_duplicate_rejected(self, existing_source):
        report = validate_records(
            [make_record(), make_record()], existing_source
        )
        assert not report.ok
        assert any(i.rule == "duplicate" for _, iss in report.failed for i in iss)

    def test_overlapping_same_context_rejected(self, existing_source):
        a = make_record()
        b = make_record(
            course_code="IMA 211",
            course_name="PROBABILITY",
            faculty_initials=["ANM"],
            faculty_names=["Dr. Anandhu Mohan"],
            start_time="09:30",
            end_time="10:25",
        )
        report = validate_records([a, b], existing_source)
        assert not report.ok
        assert any(i.rule == "no_overlap" for _, iss in report.failed for i in iss)
        assert report.summary()["passed"] == 0

    def test_adjacent_slots_do_not_overlap(self, existing_source):
        a = make_record()
        b = make_record(
            slot_index=2,
            start_time="10:00",
            end_time="10:55",
            course_code="IMA 211",
            course_name="PROBABILITY",
            faculty_initials=["ANM"],
            faculty_names=["Dr. Anandhu Mohan"],
        )
        report = validate_records([a, b], existing_source)
        assert report.ok

    def test_different_days_do_not_overlap(self, existing_source):
        a = make_record()
        b = make_record(
            day="Tuesday",
            course_code="IMA 211",
            course_name="PROBABILITY",
            faculty_initials=["ANM"],
            faculty_names=["Dr. Anandhu Mohan"],
        )
        report = validate_records([a, b], existing_source)
        assert report.ok

    def test_activities_exempt_from_overlap(self, existing_source):
        a = make_record()
        b = make_record(
            day="Monday",
            slot_index=8,
            start_time="17:00",
            end_time="19:00",
            course_code=None,
            course_name="CODING CLUB ACTIVITIES",
            faculty_initials=[],
            faculty_names=[],
            entry_type="club_activity",
        )
        report = validate_records([a, b], existing_source)
        assert report.ok


class TestDirectoryCrossCheck:
    def test_unknown_course_against_directory(self, existing_source):
        report = validate_records(
            [make_record()],
            existing_source,
            known_courses={"ICS 211": {"code": "ICS 211"}},
            known_faculty={"PS": {"initials": "PS"}},
        )
        assert report.ok

    def test_missing_from_directory_rejected(self, existing_source):
        report = validate_records(
            [make_record()],
            existing_source,
            known_courses={},
            known_faculty={"PS": {"initials": "PS"}},
        )
        assert not report.ok
        assert any(i.rule == "course_in_catalog" for _, iss in report.failed for i in iss)

    def test_missing_faculty_from_directory_rejected(self, existing_source):
        report = validate_records(
            [make_record()],
            existing_source,
            known_courses={"ICS 211": {"code": "ICS 211"}},
            known_faculty={},
        )
        assert not report.ok
        assert any(i.rule == "faculty_in_directory" for _, iss in report.failed for i in iss)
