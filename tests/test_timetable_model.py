"""Unit tests: canonical model primitives (extraction building blocks)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.model import (  # noqa: E402
    TimetableRecord,
    document_metadata,
    entry_type_from_cell,
    parse_day_row,
    parse_period_header,
)


class TestPeriodHeaderParsing:
    @pytest.mark.parametrize(
        ("raw", "slot", "start", "end"),
        [
            ("6\n(3.00-3.55 PM)", 6, "15:00", "15:55"),
            ("1\n(9.00-9.55 AM)", 1, "09:00", "09:55"),
            ("4\n(12.05-1.00 PM)", 4, "12:05", "13:00"),
            ("8\n(5.00-7.00 PM)", 8, "17:00", "19:00"),
            ("9 (5.00-7.00 PM)", 9, "17:00", "19:00"),
            ("1\n(9.00-9.55\nAM)", 1, "09:00", "09:55"),
        ],
    )
    def test_combined_headers(self, raw, slot, start, end):
        h = parse_period_header(raw)
        assert h is not None
        assert h.slot_index == slot
        assert h.start == start
        assert h.end == end
        assert h.kind == "teaching"

    def test_split_rows_join(self):
        """Fragments joined by the extractor's separator parse as one header."""
        h = parse_period_header("(9.00-9.55 | AM)")
        assert h is None  # bare time fragment without slot number is not a header
        h2 = parse_period_header("1 | (9.00-9.55 | AM)")
        assert h2 is not None
        assert (h2.start, h2.end) == ("09:00", "09:55")

    def test_cross_noon_range(self):
        """'11.05-12.00 PM' must not become 23:05 (case + meridiem inference)."""
        h = parse_period_header("3\n(11.05- 12.00 PM)")
        assert h is not None
        assert (h.start, h.end) == ("11:05", "12:00")

    def test_overlapping_glyph_artifact(self):
        """The '(5.0P0M-7). 00' Word artifact still yields 17:00-19:00."""
        h = parse_period_header("8 | (5.0P0M-7). 00")
        assert h is not None
        assert (h.start, h.end) == ("17:00", "19:00")

    def test_break_headers(self):
        for raw in ("B\nr\ne\na\nk\nk", "L\nu\nn\nc\nh\nB\nr\ne\na\nk"):
            h = parse_period_header(raw)
            assert h is not None
            assert h.kind == "break"

    def test_untimed_slot(self):
        h = parse_period_header("8")
        assert h is not None
        assert h.slot_index == 8
        assert h.start is None and h.end is None

    @pytest.mark.parametrize("raw", ["DAYS", "", None, "Mon", "(9.00-9.55 AM)"])
    def test_non_headers(self, raw):
        assert parse_period_header(raw) is None


class TestDayParsing:
    @pytest.mark.parametrize(
        ("raw", "day"),
        [
            ("Mon", "Monday"),
            ("Tuesday", "Tuesday"),
            ("Wed", "Wednesday"),
            ("Sat", "Saturday"),
            ("DAYS", None),
            ("", None),
            (None, None),
        ],
    )
    def test_days(self, raw, day):
        assert parse_day_row(raw) == day


class TestEntryType:
    def test_precedence(self):
        assert entry_type_from_cell("Sports/Yoga/Cultural Activities", False) == "sports"
        assert entry_type_from_cell("CODING CLUB ACTIVITIES", False) == "club_activity"
        assert entry_type_from_cell("ICS 214 LAB DJ", True) == "lab"
        assert entry_type_from_cell("ICS 211(T) PS", False) == "tutorial"
        assert entry_type_from_cell("ICS 211 PS", False) == "class"


class TestDocumentMetadata:
    def test_full_title(self):
        meta = document_metadata(
            "B.TECH. SEMESTER III COMPUTER SCIENCE AND ENGINEERING BATCH-I [Adm-2025]",
            "B.TECH. TIME TABLE FOR AUGUST-NOVEMBER 2026",
        )
        assert meta is not None
        assert meta.semester == 3
        assert meta.branch == "COMPUTER SCIENCE AND ENGINEERING"
        assert meta.batch == "I"
        assert meta.valid_from == "2026-08-01"
        assert meta.valid_until == "2026-11-30"

    def test_non_matching(self):
        assert document_metadata("Random page", "Some title") is None


class TestSourceUid:
    def test_deterministic_and_distinct(self):
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
            course_name="DAA",
            source_id="s.pdf",
            source_page=1,
            valid_from="2026-08-01",
            valid_until="2026-11-30",
        )
        a = TimetableRecord(**base)
        b = TimetableRecord(**base)
        assert a.source_uid == b.source_uid
        c = TimetableRecord(**{**base, "day": "Tuesday"})
        assert a.source_uid != c.source_uid
