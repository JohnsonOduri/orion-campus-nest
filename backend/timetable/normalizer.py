"""Normalization: raw extracted geometry → canonical TimetableRecords.

Responsibilities:
  * attribute grid cells to weekdays (row-order/overlap, Word fragments incl.),
  * assign cells to period columns by best x-overlap; whole-grid activities
    (club/sports) may occupy several columns and emit one record per column,
  * merge stacked fragments inside a (day, column) bucket in y-order,
  * resolve course codes/names and faculty initials via the page legend,
  * classify entry types (class/lab/tutorial/seminar/project/club/sports),
  * collect unresolved references instead of guessing (AGENTS.md §6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .extractor import PeriodColumn, Section, TimetableDocument
from .model import (
    NON_COURSE_ACTIVITIES,
    TimetableRecord,
    entry_type_from_cell,
    parse_day_row,
)

_COURSE_CODE_IN_CELL = re.compile(
    r"\b([IUE][A-Z]{2}\s?\d{3}|[A-Z]{2,4}\s?\d{3})\b", re.IGNORECASE
)
_INITIALS_RE = re.compile(r"\(([A-Za-z][A-Za-z/ .]*?)\)")


@dataclass
class NormalizationResult:
    records: list[TimetableRecord] = field(default_factory=list)
    unresolved_courses: list[str] = field(default_factory=list)
    unresolved_faculty: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] - 1 and a[1] > b[0] + 1


def _overlap_width(x0: float, x1: float, col: PeriodColumn) -> float:
    return min(x1, col.x1) - max(x0, col.x0)


def _best_period(x0: float, x1: float, periods: list[PeriodColumn]) -> Optional[PeriodColumn]:
    """Column with maximal x-overlap; None when there is no real overlap."""
    best = None
    best_ov = 0.0
    for col in periods:
        ov = _overlap_width(x0, x1, col)
        if ov > best_ov:
            best_ov = ov
            best = col
    return best


def _significant_periods(
    x0: float, x1: float, periods: list[PeriodColumn], min_fraction: float = 0.25
) -> list[PeriodColumn]:
    """Columns overlapped by at least min_fraction of the cell width."""
    width = max(x1 - x0, 1e-6)
    return [
        col
        for col in periods
        if _overlap_width(x0, x1, col) / width >= min_fraction
    ]


def _classify_cell(text: str) -> tuple[str, Optional[str]]:
    """Return (kind, course_code) for raw cell text.

    kind: 'entry' (course), 'activity', 'other', 'empty', 'noise'
    """
    flat = _clean(text)
    if not flat:
        return "empty", None
    m = _COURSE_CODE_IN_CELL.search(flat)
    if m:
        code = re.sub(r"\s+", "", m.group(1)).upper()
        # re-insert the space: "ICS211" -> "ICS 211" (legend keys use a space)
        code = re.sub(r"^([A-Z]{3})(\d{3})$", r"\1 \2", code)
        return "entry", code
    lowered = flat.lower()
    for needle, etype in NON_COURSE_ACTIVITIES.items():
        if needle in lowered:
            return "activity", None
    # Named non-course slots like "FA Interaction" -> other
    if re.search(r"[A-Za-z]{3}", flat):
        return "other", None
    return "noise", None


def _lab_batch(text: str) -> Optional[int]:
    m = re.search(r"LAB\s*(\d)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# Parenthesised tokens that are NOT faculty initials. '(T)' is the source
# document's tutorial marker; the rest are lab-room labels.
_NON_INITIAL_TOKENS = {"T", "EC LAB I", "EC LAB II", "CS LAB I", "CS LAB II"}


def _extract_cell_initials(text: str) -> list[str]:
    """Initials printed directly in a cell, e.g. 'ICS 214 LAB DJ' -> DJ.

    '(T)' (tutorial marker) and lab-room labels are excluded.
    """
    out: list[str] = []
    for blk in _INITIALS_RE.findall(text):
        for p in blk.split("/"):
            token = re.sub(r"[^A-Za-z]", "", p).upper()
            if not token or p.strip().upper() in _NON_INITIAL_TOKENS:
                continue
            out.append(token)
    return out


def _resolve_faculty(
    text: str,
    course_code: Optional[str],
    section: Section,
    result: NormalizationResult,
) -> tuple[list[str], list[str]]:
    """Resolve faculty initials/names from the legend, then the cell itself."""
    initials: list[str] = []
    names: list[str] = []
    entry = section.legend.by_code(course_code) if course_code else None
    if entry:
        initials = list(entry.faculty_initials)
        names = list(entry.faculty_names)
    else:
        if course_code and course_code not in result.unresolved_courses:
            result.unresolved_courses.append(course_code)
    for ini in _extract_cell_initials(text):
        if ini and ini not in initials:
            initials.append(ini)
    # align names to initials; empty name means unresolved (kept auditable)
    aligned: list[str] = []
    for i, ini in enumerate(initials):
        if entry and ini in entry.faculty_initials:
            j = entry.faculty_initials.index(ini)
            aligned.append(entry.faculty_names[j] if j < len(entry.faculty_names) else "")
        else:
            aligned.append(names[i] if i < len(names) else "")
    return initials, aligned


def normalize_section(section: Section, source_id: str) -> NormalizationResult:
    """Turn one section's extracted grid into normalized records."""
    result = NormalizationResult()
    meta = section.metadata
    if meta is None:
        result.warnings.append(f"page {section.page}: no section metadata; skipped")
        return result

    day_spans = section.day_spans
    day_order = section.day_order
    periods = section.periods

    # ---- 1. group cells by day --------------------------------------------
    cells = sorted(section.records_raw, key=lambda c: (c["row"], c["x0"]))
    by_day: dict[str, list[dict]] = {d: [] for d in day_order}
    for cell in cells:
        text = _clean(cell["text"])
        if not text or parse_day_row(text):
            continue  # empty or a day label
        # The merged full-width Saturday row is a whole-grid activity that is
        # emitted exactly once via the dedicated saturday path below; do not
        # also split it across period columns (that double-counted it).
        if (
            section.saturday_text
            and "Saturday" in day_spans
            and _clean(section.saturday_text).lower() in text.lower()
        ):
            continue
        top, bottom = cell["top"], cell["bottom"]
        target = None
        for day in day_order:
            if _overlaps((top, bottom), day_spans[day]):
                target = day
                break
        if target is None:
            above = [d for d in day_order if day_spans[d][0] <= top]
            if above:
                target = max(above, key=lambda d: day_spans[d][0])
        if target is None:
            result.warnings.append(
                f"page {section.page}: cell y={top:.0f} matches no day row; skipped"
            )
            continue
        by_day.setdefault(target, []).append(cell)

    # ---- 2. per day: assign to columns, merge fragments, emit records ------
    for day, day_cells in by_day.items():
        buckets: dict[int, list[dict]] = {}  # id(periodcolumn) -> cells
        col_by_id: dict[int, PeriodColumn] = {}
        for cell in day_cells:
            x0, x1 = cell["x0"], cell["x1"]
            kind, _ = _classify_cell(cell["text"])
            if kind in {"empty", "noise"}:
                continue
            targets: list[PeriodColumn]
            if kind == "activity":
                # whole-grid activities span every column they cover
                targets = _significant_periods(x0, x1, periods)
                if not targets:
                    best = _best_period(x0, x1, periods)
                    targets = [best] if best else []
            else:
                best = _best_period(x0, x1, periods)
                targets = [best] if best else []
            if not targets:
                result.warnings.append(
                    f"page {section.page}: cell '{_clean(cell['text'])[:40]}' "
                    "does not map to a period column"
                )
                continue
            for col in targets:
                buckets.setdefault(id(col), []).append(cell)
                col_by_id[id(col)] = col

        for key, group in buckets.items():
            col = col_by_id[key]
            if col.is_break:
                continue
            frags = sorted(group, key=lambda c: (c["top"], c["x0"]))
            text = _clean(" ".join(_clean(f["text"]) for f in frags))
            if not text:
                continue

            kind, course_code = _classify_cell(text)
            if kind in {"empty", "noise"}:
                continue

            h = col.header
            if kind == "activity":
                lowered = text.lower()
                entry_type = next(
                    (t for n, t in NON_COURSE_ACTIVITIES.items() if n in lowered),
                    "other",
                )
                course_code = None
                faculty_initials: list[str] = []
                faculty_names: list[str] = []
            else:
                has_lab = bool(re.search(r"\bLAB\b", text, re.IGNORECASE))
                entry_type = entry_type_from_cell(text, has_lab)
                if kind == "other":
                    entry_type = "other"
                legend_entry = section.legend.by_code(course_code) if course_code else None
                if entry_type == "class" and legend_entry and re.search(
                    r"\bB\.?\s?TECH\.?\s?PROJECT\b|\bBTP\b|\bPROJECT\b",
                    legend_entry.course_name,
                    re.IGNORECASE,
                ):
                    # legend names the course itself a project (e.g. "BTP-I"):
                    # individually supervised, legitimately no fixed faculty.
                    entry_type = "project"
                faculty_initials, faculty_names = _resolve_faculty(
                    text, course_code, section, result
                )

            result.records.append(
                TimetableRecord(
                    programme=meta.programme,
                    branch=meta.branch,
                    semester=meta.semester,
                    batch=meta.batch,
                    section=meta.batch,
                    day=day,
                    slot_index=h.slot_index,
                    start_time=h.start,
                    end_time=h.end,
                    course_code=course_code,
                    course_name=(section.legend.by_code(course_code).course_name
                                 if course_code and section.legend.by_code(course_code)
                                 else None),
                    faculty_initials=faculty_initials,
                    faculty_names=faculty_names,
                    room=None,  # rooms come from the classroom-details source
                    entry_type=entry_type,
                    lab_batch=_lab_batch(text),
                    source_id=source_id,
                    source_page=section.page,
                    source_text=text[:200],
                    valid_from=meta.valid_from,
                    valid_until=meta.valid_until,
                )
            )

    # ---- 3. Saturday: one merged whole-grid activity row --------------------
    if section.saturday_text and "Saturday" in day_spans:
        lowered = section.saturday_text.lower()
        etype = next(
            (t for n, t in NON_COURSE_ACTIVITIES.items() if n in lowered),
            "other",
        )
        result.records.append(
            TimetableRecord(
                programme=meta.programme,
                branch=meta.branch,
                semester=meta.semester,
                batch=meta.batch,
                section=meta.batch,
                day="Saturday",
                slot_index=1,
                start_time=None,
                end_time=None,
                course_code=None,
                course_name=section.saturday_text,
                faculty_initials=[],
                faculty_names=[],
                room=None,
                entry_type=etype,
                source_id=source_id,
                source_page=section.page,
                source_text=section.saturday_text,
                valid_from=meta.valid_from,
                valid_until=meta.valid_until,
            )
        )

    return result


def normalize_document(doc: TimetableDocument) -> list[NormalizationResult]:
    """Normalize every section of an extracted document."""
    return [normalize_section(section, doc.source_id) for section in doc.sections]


def dedupe(records: list[TimetableRecord]) -> tuple[list[TimetableRecord], int]:
    """Remove exact duplicates by source_uid, preserving order."""
    seen: set[str] = set()
    out: list[TimetableRecord] = []
    dupes = 0
    for r in records:
        uid = r.source_uid
        if uid in seen:
            dupes += 1
            continue
        seen.add(uid)
        out.append(r)
    return out, dupes


def build_preview(
    doc: TimetableDocument,
    results: list[NormalizationResult],
    source_id: str,
    validation_summary: Optional[dict] = None,
) -> dict:
    """Human-inspectable preview document (Phase 4 contract)."""
    records: list[TimetableRecord] = []
    for res in results:
        records.extend(res.records)
    records, dupes = dedupe(records)

    courses = sorted({r.course_code for r in records if r.course_code})
    faculty = sorted({i for r in records for i in r.faculty_initials if i})
    unresolved_courses: list[str] = []
    unresolved_faculty: list[str] = []
    warnings = list(doc.warnings)
    for res in results:
        for c in res.unresolved_courses:
            if c not in unresolved_courses:
                unresolved_courses.append(c)
        for f in res.unresolved_faculty:
            if f not in unresolved_faculty:
                unresolved_faculty.append(f)
        warnings.extend(res.warnings)

    preview = {
        "source": {
            "source_id": source_id,
            "file": doc.path.name,
            "pages_processed": doc.pages_processed,
            "sections": [
                {
                    "page": s.page,
                    "title": s.title,
                    "periods": [
                        {
                            "slot_index": c.header.slot_index,
                            "start_time": c.header.start,
                            "end_time": c.header.end,
                            "kind": c.header.kind,
                            "derived": "[derived]" in c.header.raw,
                        }
                        for c in s.periods
                    ],
                }
                for s in doc.sections
            ],
        },
        "stats": {
            "pages_processed": doc.pages_processed,
            "records_extracted": len(records),
            "records_valid": 0,
            "records_rejected": 0,
            "courses_discovered": courses,
            "faculty_discovered": faculty,
            "unresolved_initials": unresolved_faculty,
            "unresolved_courses": unresolved_courses,
            "duplicate_records": dupes,
            "warnings": warnings,
        },
        "records": [r.to_dict() for r in records],
    }
    if validation_summary is not None:
        preview["validation"] = validation_summary
        preview["stats"]["records_valid"] = validation_summary.get("passed", 0)
        preview["stats"]["records_rejected"] = validation_summary.get("failed", 0)
    return preview
