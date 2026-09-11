"""Unit tests: extractor + normalizer on the real S3 PDF (skipped if absent)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.extractor import extract_document  # noqa: E402
from backend.timetable.normalizer import dedupe, normalize_document  # noqa: E402

PDF = Path("Data/Structured/Semester 3_TimeTable_Odd_2026.pdf")

PDF_MISSING = not PDF.exists()

pytestmark = pytest.mark.skipif(PDF_MISSING, reason="source PDF not present")


@pytest.fixture(scope="module")
def extracted():
    doc = extract_document(PDF)
    results = normalize_document(doc)
    records = [r for res in results for r in res.records]
    records, dupes = dedupe(records)
    return doc, results, records, dupes


class TestExtraction:
    def test_page_count(self, extracted):
        doc, _, _, _ = extracted
        assert doc.pages_processed == 17

    def test_all_section_grids_found(self, extracted):
        doc, _, _, _ = extracted
        assert len(doc.sections) == 16  # 16 branch/batch grids, page 17 is split-up

    def test_period_times_not_hardcoded_but_extracted(self, extracted):
        """Slot times come from the PDF; S3 grid is 9.00-9.55 AM ... 5.00-7.00 PM."""
        doc, _, _, _ = extracted
        p1 = {c.header.slot_index: (c.header.start, c.header.end) for c in doc.sections[0].periods if not c.is_break}
        assert p1[1] == ("09:00", "09:55")
        assert p1[6] == ("15:00", "15:55")
        assert p1[9] == ("17:00", "19:00")

    def test_break_columns_detected(self, extracted):
        doc, _, _, _ = extracted
        breaks = [c for c in doc.sections[0].periods if c.is_break]
        assert len(breaks) >= 2  # morning break + lunch break

    def test_evening_block_derived(self, extracted):
        """Slots 8/9 share one printed range; derivation is flagged, not silent."""
        doc, _, _, _ = extracted
        derived = [c for c in doc.sections[0].periods if "[derived]" in c.header.raw]
        assert {c.header.slot_index for c in derived} == {8, 9}

    def test_metadata_per_section(self, extracted):
        doc, _, _, _ = extracted
        meta = doc.sections[0].metadata
        assert meta is not None
        assert meta.semester == 3
        assert "BATCH" in meta.raw_title
        assert meta.valid_from == "2026-08-01" and meta.valid_until == "2026-11-30"


class TestNormalization:
    def test_record_volume(self, extracted):
        _, _, records, _ = extracted
        assert 550 <= len(records) <= 700

    def test_all_course_entries_resolved(self, extracted):
        _, _, records, _ = extracted
        teaching = [r for r in records if r.entry_type in {"class", "lab", "tutorial"}]
        assert teaching
        assert all(r.course_code for r in teaching)
        assert all(r.course_name for r in teaching)

    def test_faculty_initials_resolved_via_legend(self, extracted):
        _, _, records, _ = extracted
        teaching = [r for r in records if r.entry_type in {"class", "lab", "tutorial"}]
        assert all(r.faculty_initials for r in teaching)
        initials = {i for r in teaching for i in r.faculty_initials}
        assert "PS" in initials  # Dr. Priyadarshini
        assert "ANM" in initials  # Dr. Anandhu Mohan

    def test_no_marker_tokens_as_faculty(self, extracted):
        """'(T)' tutorial markers and lab labels are not faculty initials."""
        _, _, records, _ = extracted
        initials = {i for r in records for i in r.faculty_initials}
        assert "T" not in initials
        assert "ECLABI" not in initials

    def test_entry_type_preserved(self, extracted):
        _, _, records, _ = extracted
        types = {r.entry_type for r in records}
        assert {"class", "lab", "tutorial", "club_activity", "sports"} <= types

    def test_saturday_rows(self, extracted):
        _, _, records, _ = extracted
        sat = [r for r in records if r.day == "Saturday"]
        assert len(sat) == 16  # one per section grid
        assert all(r.entry_type == "sports" for r in sat)
        assert all(r.start_time is None for r in sat)

    def test_no_duplicates(self, extracted):
        _, _, records, dupes = extracted
        assert dupes == 0
        uids = [r.source_uid for r in records]
        assert len(uids) == len(set(uids))

    def test_validity_on_every_record(self, extracted):
        _, _, records, _ = extracted
        assert all(r.valid_from == "2026-08-01" for r in records)
        assert all(r.valid_until == "2026-11-30" for r in records)

    def test_source_provenance(self, extracted):
        _, _, records, _ = extracted
        assert all(r.source_id == PDF.name for r in records)
        assert all(1 <= r.source_page <= 17 for r in records)
