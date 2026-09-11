"""Repository idempotency tests against a fake PostgREST client.

Running ingestion twice must NOT create duplicate timetable records — the
source_uid natural key drives upserts; periods reconcile via fetch→diff.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.model import TimetableRecord  # noqa: E402
from backend.timetable.repository import TimetableRepository  # noqa: E402


def _as_rows(payload):
    """Normalize like the real supabase-py client: dict -> one-row list."""
    if isinstance(payload, dict):
        return [payload]
    return list(payload)


class FakeTable:
    def __init__(self, store: dict, name: str):
        self.store = store
        self.name = name
        self.rows = store.setdefault(name, [])

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def insert(self, rows):
        self.rows.extend(_as_rows(rows))
        return self

    def upsert(self, rows, on_conflict=None):
        key = on_conflict or "id"
        for row in _as_rows(rows):
            for i, existing in enumerate(self.rows):
                if existing.get(key) == row.get(key):
                    self.rows[i] = {**existing, **row}
                    break
            else:
                self.rows.append(dict(row))
        return self

    def execute(self):
        return type("R", (), {"data": list(self.rows), "error": None})()


class FakeClient:
    def __init__(self):
        self.store: dict = {}
        self.tables: list[str] = []

    def table(self, name):
        self.tables.append(name)
        return FakeTable(self.store, name)


def make_record(slot: int = 1) -> TimetableRecord:
    return TimetableRecord(
        programme="B.Tech",
        branch="CSE",
        semester=3,
        batch="I",
        section="I",
        day="Monday",
        slot_index=slot,
        start_time="09:00",
        end_time="09:55",
        course_code="ICS 211",
        course_name="DESIGN AND ANALYSIS OF ALGORITHMS",
        faculty_initials=["PS"],
        faculty_names=["Dr. Priyadarshini"],
        source_id="Semester 3_TimeTable_Odd_2026.pdf",
        source_page=1,
        valid_from="2026-08-01",
        valid_until="2026-11-30",
    )


class TestEntryIdempotency:
    def test_double_import_no_duplicates(self):
        client = FakeClient()
        repo = TimetableRepository(client)
        stats1 = repo.import_entries([make_record()], "s.pdf", approved_by="t")
        stats2 = repo.import_entries([make_record()], "s.pdf", approved_by="t")
        rows = client.store["timetable_entries"]
        assert stats1.entries_upserted == 1
        assert stats2.entries_upserted == 1
        assert len(rows) == 1  # upserted, not duplicated

    def test_distinct_slots_distinct_rows(self):
        client = FakeClient()
        repo = TimetableRepository(client)
        repo.import_entries(
            [make_record(slot=1), make_record(slot=2)], "s.pdf"
        )
        assert len(client.store["timetable_entries"]) == 2

    def test_row_shape_matches_schema(self):
        client = FakeClient()
        repo = TimetableRepository(client)
        repo.import_entries([make_record()], "s.pdf", approved_by="admin@example.com")
        row = client.store["timetable_entries"][0]
        for col in (
            "source_uid",
            "source_id",
            "source_page",
            "day_of_week",
            "slot_index",
            "start_time",
            "end_time",
            "course_code",
            "course_name",
            "faculty_initials",
            "faculty_names",
            "entry_type",
            "semester",
            "programme",
            "branch",
            "batch",
            "section",
            "valid_from",
            "valid_until",
            "status",
            "approved_at",
            "approved_by",
        ):
            assert col in row, f"missing column {col}"
        assert row["status"] == "active"
        assert row["approved_by"] == "admin@example.com"
        assert row["day_of_week"] == 1


class TestPeriodReconciliation:
    def test_periods_not_duplicated_across_runs(self):
        client = FakeClient()
        repo = TimetableRepository(client)

        class FakeSection:
            page = 1
            periods = [
                type(
                    "C",
                    (),
                    {
                        "x0": 0,
                        "x1": 1,
                        "header": type("H", (), {"slot_index": 1, "start": "09:00", "end": "09:55", "kind": "teaching", "is_time_derived": False})(),
                    },
                )()
            ]

        sections = [FakeSection(), FakeSection()]  # same periods on two pages
        repo.import_periods(sections, "s.pdf")
        repo.import_periods(sections, "s.pdf")
        rows = client.store["timetable_periods"]
        assert len(rows) == 1  # reconciled by (source_id, slot_index, start_time)

    def test_new_period_added(self):
        client = FakeClient()
        repo = TimetableRepository(client)

        def section(slot):
            return type(
                "S",
                (),
                {
                    "page": 1,
                    "periods": [
                        type(
                            "C",
                            (),
                            {
                                "x0": 0,
                                "x1": 1,
                                "header": type("H", (), {"slot_index": slot, "start": "09:00", "end": "09:55", "kind": "teaching", "is_time_derived": False})(),
                            },
                        )()
                    ],
                },
            )()

        repo.import_periods([section(1)], "s.pdf")
        repo.import_periods([section(1), section(2)], "s.pdf")
        rows = client.store["timetable_periods"]
        assert {r["slot_index"] for r in rows} == {1, 2}


class TestAuditTrail:
    def test_ingestion_run_recorded(self):
        client = FakeClient()
        repo = TimetableRepository(client)
        repo.record_ingestion_run("s.pdf", "imported", {"entries_upserted": 5}, 0, 2, approved_by="a@b.c")
        runs = client.store["ingestion_runs"]
        assert len(runs) == 1
        assert runs[0]["status"] == "imported"
        assert runs[0]["stats"]["entries_upserted"] == 5
        assert runs[0]["approved_by"] == "a@b.c"


class TestLegendImport:
    def test_courses_and_faculty_upserted(self):
        from backend.timetable.extractor import Legend, LegendEntry

        client = FakeClient()
        repo = TimetableRepository(client)
        legend = Legend(
            page=1,
            entries=(
                LegendEntry(
                    course_code="ICS 211",
                    course_name="DESIGN AND ANALYSIS OF ALGORITHMS",
                    credits_raw="[3-1-0] 4",
                    faculty_initials=("PS",),
                    faculty_names=("Dr. Priyadarshini",),
                ),
            ),
        )
        repo.import_legend(legend, "s.pdf")
        repo.import_legend(legend, "s.pdf")  # idempotent
        assert len(client.store["courses"]) == 1
        assert len(client.store["faculty"]) == 1
        assert client.store["faculty"][0]["initials"] == "PS"
