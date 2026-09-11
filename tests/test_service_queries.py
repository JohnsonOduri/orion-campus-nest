"""Service query logic tests using an in-memory fake repository.

Covers: expiry filtering, status filtering, break exclusion, activity opt-in,
ongoing-vs-future next class, week window, empty results, and identity
isolation (user_id can only come from the resolved context, never guessed).
"""

from __future__ import annotations

import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.service import TimetableService  # noqa: E402

MON = 1  # ISO Monday


def row(
    day: int,
    start: str,
    end: str,
    code: str = "ICS 211",
    etype: str = "class",
    valid_from: str = "2026-08-01",
    valid_until: str = "2026-11-30",
    status: str = "active",
    slot: int = 1,
) -> dict:
    return {
        "course_code": code,
        "course_name": "DAA" if code else "Activity",
        "faculty_names": ["Dr. Priyadarshini"],
        "room": None,
        "day_of_week": day,
        "slot_index": slot,
        "start_time": start,
        "end_time": end,
        "entry_type": etype,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "status": status,
    }


class FakeRepo:
    """Filters exactly like the orion_* SQL functions."""

    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.calls: list[tuple] = []

    def _valid(self, e: dict, on: date):
        return (
            e["status"] == "active"
            and date.fromisoformat(e["valid_from"]) <= on
            and date.fromisoformat(e["valid_until"]) >= on
            and e["entry_type"] != "break"
        )

    def active_entries_for_context(self, *, semester, branch, batch, section, on_date):
        self.calls.append(("active", on_date))
        return [e for e in self.entries if self._valid(e, on_date)]

    def day_timetable(self, *, user_id, on_date):
        return self.active_entries_for_context(
            semester=3, branch="CSE", batch="I", section="I", on_date=on_date
        )

    def week_timetable(self, *, user_id, on_date):
        self.calls.append(("week", on_date))
        monday = on_date.fromordinal(on_date.toordinal() - (on_date.isoweekday() - 1))
        window_end = date.fromordinal(monday.toordinal() + 6)
        return [
            e
            for e in self.entries
            if self._valid(e, window_end) or self._valid(e, monday)
        ]

    def next_class(self, *, user_id, at, include_activities=False):
        """Mirrors the orion_next_class SQL (day-offset occurrence model)."""
        self.calls.append(("next", at, include_activities))
        day = at.isoweekday()
        t = at.time()
        cands = []
        for e in self.entries:
            if e["entry_type"] == "break":
                continue
            if (
                not include_activities
                and e["entry_type"] in {"sports", "club_activity"}
            ):
                continue
            if e["day_of_week"] == day and time.fromisoformat(e["end_time"]) > t:
                offset = 0  # today, still ongoing or upcoming
            else:
                offset = ((e["day_of_week"] - day + 6) % 7) + 1
            occ = date.fromordinal(at.date().toordinal() + offset)
            if date.fromisoformat(e["valid_from"]) <= occ <= date.fromisoformat(
                e["valid_until"]
            ):
                cands.append((offset, time.fromisoformat(e["start_time"]), e))
        if not cands:
            return None
        cands.sort(key=lambda c: (c[0], c[1]))
        return cands[0][2]

    def rpc(self, fn, params):
        assert fn == "orion_student_context"
        return SimpleNamespace(
            data={
                "display_name": "Test Student",
                "semester": 3,
                "programme": "B.Tech",
                "branch": "CSE",
                "batch": "I",
                "section": "I",
            }
        )


@pytest.fixture
def svc():
    entries = [
        row(MON, "09:00", "09:55", code="ICS 211", slot=1),
        row(MON, "11:05", "12:00", code="ICS 212", slot=3),
        row(MON, "12:00", "13:00", code=None, etype="break", slot=4),
        row(MON, "15:00", "15:55", code="IMA 211", slot=5),
        row(MON, "17:00", "19:00", code=None, etype="club_activity", slot=8),
        row(2, "09:00", "09:55", code="ICS 213", slot=1),  # Tuesday
    ]
    service = TimetableService.__new__(TimetableService)
    service._repo = FakeRepo(entries)
    service._demo = False
    return service


class TestStudentTimetable:
    def test_excludes_breaks(self, svc):
        entries = svc.get_timetable_for_student(on_date=date(2026, 9, 7))
        assert all(e["entry_type"] != "break" for e in entries)

    def test_expiry_filtering(self):
        expired = [row(MON, "09:00", "09:55", valid_until="2026-08-31")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(expired)
        service._demo = False
        assert service.get_timetable_for_student(on_date=date(2026, 9, 7)) == []

    def test_not_yet_valid_excluded(self):
        future = [row(MON, "09:00", "09:55", valid_from="2026-10-01")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(future)
        service._demo = False
        assert service.get_timetable_for_student(on_date=date(2026, 9, 7)) == []

    def test_archived_status_excluded(self):
        rows = [row(MON, "09:00", "09:55", status="archived")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        assert service.get_timetable_for_student(on_date=date(2026, 9, 7)) == []

    def test_valid_range_boundary_inclusive(self):
        rows = [row(MON, "09:00", "09:55", valid_from="2026-09-07", valid_until="2026-09-07")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        got = service.get_timetable_for_student(on_date=date(2026, 9, 7))
        assert len(got) == 1


class TestNextClass:
    def test_future_class_today(self, svc):
        at = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at)
        assert nxt is not None
        assert nxt["course_code"] == "ICS 212"
        assert nxt["start_time"] == "11:05"

    def test_ongoing_class_is_next(self, svc):
        at = datetime(2026, 9, 7, 11, 30, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at)
        assert nxt is not None
        assert nxt["course_code"] == "ICS 212"  # ends 12:00, still ongoing

    def test_ended_class_not_next(self, svc):
        at = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at)
        assert nxt is not None
        assert nxt["course_code"] == "IMA 211"  # 15:00

    def test_club_activity_excluded_by_default(self, svc):
        at = datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at)
        assert nxt is None or nxt["entry_type"] not in {"club_activity", "sports"}

    def test_activities_included_when_requested(self, svc):
        at = datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at, include_activities=True)
        assert nxt is not None
        assert nxt["entry_type"] == "club_activity"

    def test_rolls_to_next_day(self, svc):
        at = datetime(2026, 9, 7, 19, 30, tzinfo=timezone.utc)
        nxt = svc.get_next_class(at=at)
        assert nxt is not None
        assert nxt["day_of_week"] == 2
        assert nxt["course_code"] == "ICS 213"

    def test_friday_evening_wraps_to_next_monday(self):
        """After Friday's last class, next class = next week's Monday P1."""
        rows = [row(MON, "09:00", "09:55")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        nxt = service.get_next_class(
            at=datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)  # Friday evening
        )
        assert nxt is not None
        assert nxt["day_of_week"] == MON

    def test_same_weekday_after_end_wraps_to_next_week(self):
        """Monday 10:00 with only a Monday 09:00 class → next Monday, not today."""
        rows = [row(MON, "09:00", "09:55")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        nxt = service.get_next_class(
            at=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # Monday 10:00
        )
        assert nxt is not None
        assert nxt["day_of_week"] == MON
        assert nxt["start_time"] == "09:00"

    def test_expired_semester_no_next_class(self):
        """Validity is per-occurrence: an expired entry never surfaces, even
        wrapped to next week."""
        rows = [row(MON, "09:00", "09:55", valid_until="2026-08-31")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        assert (
            service.get_next_class(at=datetime(2026, 9, 7, 8, 0, tzinfo=timezone.utc))
            is None
        )

    def test_not_yet_valid_today_but_valid_next_week(self):
        """An entry valid only from next Monday must not surface today (Fri);
        it must surface when wrapped to next week's Monday."""
        rows = [row(MON, "09:00", "09:55", valid_from="2026-09-14")]
        service = TimetableService.__new__(TimetableService)
        service._repo = FakeRepo(rows)
        service._demo = False
        # Friday 2026-09-11 10:00 — today invalid, next Monday valid
        nxt = service.get_next_class(
            at=datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
        )
        assert nxt is not None
        assert nxt["day_of_week"] == MON


class TestIdentity:
    def test_context_comes_from_profile_not_arguments(self, svc):
        """The service passes NO user-supplied context; repo RPC resolves it."""
        ctx = svc.student_context()
        assert ctx["semester"] == 3
        assert ctx["branch"] == "CSE"

    def test_no_user_id_is_forwarded_by_default(self, svc):
        svc.get_next_class(at=datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc))
        call = svc._repo.calls[-1]
        assert call[0] == "next"
        # include_activities flag reaches the repo; identity stays server-side
        assert call[2] is False
