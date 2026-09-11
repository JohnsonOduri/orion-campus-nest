"""Strict pre-insert validation (Phase 3).

Every record must pass all rules or it is excluded from the authoritative
import and reported for human review. The validator never "fixes" data —
it only accepts or rejects, and produces a human-readable report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .model import VALID_ENTRY_TYPES, WEEKDAYS, TimetableRecord


@dataclass
class ValidationIssue:
    rule: str
    message: str
    source_uid: str = ""
    record: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "message": self.message,
            "source_uid": self.source_uid,
            "record": self.record,
        }


@dataclass
class ValidationReport:
    passed: list[TimetableRecord] = field(default_factory=list)
    failed: list[tuple[TimetableRecord, list[ValidationIssue]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> dict:
        return {
            "total": len(self.passed) + len(self.failed),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "ok": self.ok,
        }


def _valid_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_records(
    records: list[TimetableRecord],
    source_path: Path,
    known_courses: dict[str, dict] | None = None,
    known_faculty: dict[str, dict] | None = None,
) -> ValidationReport:
    """Validate normalized records. Returns passed + failed with exact reasons.

    known_courses/known_faculty are optional dicts resolved from the database
    (course code -> row, faculty initials -> row) for cross-checking legends.
    None means "no directory available — skip the cross-check"; an explicitly
    passed empty dict means "the directory is known to contain nothing", so
    every teaching record fails the cross-check.
    """
    report = ValidationReport()
    source_path = Path(source_path)

    if not source_path.exists():
        report.failed.append(
            (
                _ghost_record(source_path),
                [
                    ValidationIssue(
                        "source_exists",
                        f"source file not found: {source_path}",
                    )
                ],
            )
        )
        return report

    seen_uids: set[str] = set()

    for rec in records:
        issues: list[ValidationIssue] = []
        d = rec.to_dict()

        # --- day ------------------------------------------------------------
        if rec.day not in WEEKDAYS:
            issues.append(ValidationIssue("valid_day", f"invalid day {rec.day!r}", d))

        # --- times ------------------------------------------------------------
        if rec.entry_type != "sports" and rec.day != "Saturday":
            if not rec.start_time or not rec.end_time:
                issues.append(
                    ValidationIssue(
                        "time_range",
                        f"missing time for slot {rec.slot_index} ({rec.day})",
                        d,
                        d,
                    )
                )
            else:
                if not (_valid_hhmm(rec.start_time) and _valid_hhmm(rec.end_time)):
                    issues.append(
                        ValidationIssue(
                            "valid_time", f"malformed time {rec.start_time!r}-{rec.end_time!r}", d, d
                        )
                    )
                elif rec.start_time >= rec.end_time:
                    issues.append(
                        ValidationIssue(
                            "time_order",
                            f"start_time {rec.start_time} >= end_time {rec.end_time}",
                            d,
                            d,
                        )
                    )

        # --- entry type -------------------------------------------------------
        if rec.entry_type not in VALID_ENTRY_TYPES:
            issues.append(
                ValidationIssue("valid_entry_type", f"invalid entry_type {rec.entry_type!r}", d, d)
            )

        # --- course resolution --------------------------------------------------
        if rec.entry_type in {"class", "lab", "tutorial"}:
            if not rec.course_code:
                issues.append(
                    ValidationIssue("course_resolves", "teaching entry without course code", d, d)
                )
            elif not rec.course_name:
                issues.append(
                    ValidationIssue(
                        "course_resolves",
                        f"course code {rec.course_code!r} not resolved to a course name",
                        d,
                        d,
                    )
                )
            elif known_courses is not None and rec.course_code not in known_courses:
                issues.append(
                    ValidationIssue(
                        "course_in_catalog",
                        f"course {rec.course_code} missing from resolved catalog",
                        d,
                        d,
                    )
                )

        # --- faculty resolution ---------------------------------------------------
        if rec.entry_type in {"class", "lab", "tutorial"}:
            if not rec.faculty_initials:
                issues.append(
                    ValidationIssue("faculty_resolves", "teaching entry without faculty", d, d)
                )
            else:
                unresolved = [
                    i
                    for i in rec.faculty_initials
                    if known_faculty is not None and i not in known_faculty
                ]
                if unresolved:
                    issues.append(
                        ValidationIssue(
                            "faculty_in_directory",
                            f"faculty initials not in directory: {unresolved}",
                            d,
                            d,
                        )
                    )
                if not rec.faculty_names:
                    issues.append(
                        ValidationIssue(
                            "faculty_names", f"no faculty names for {rec.faculty_initials}", d, d
                        )
                    )

        # --- validity dates -----------------------------------------------------
        if not _valid_iso_date(rec.valid_from) or not _valid_iso_date(rec.valid_until):
            issues.append(
                ValidationIssue(
                    "validity_dates",
                    f"invalid validity window {rec.valid_from!r}..{rec.valid_until!r}",
                    d,
                    d,
                )
            )
        elif rec.valid_from >= rec.valid_until:
            issues.append(
                ValidationIssue("validity_order", "valid_from must precede valid_until", d, d)
            )

        # --- academic context ------------------------------------------------------
        if rec.semester <= 0:
            issues.append(ValidationIssue("context", "missing semester", d, d))
        if not rec.branch or not rec.batch or not rec.section or not rec.programme:
            issues.append(
                ValidationIssue(
                    "context",
                    f"incomplete academic context (branch={rec.branch!r}, batch={rec.batch!r}, "
                    f"section={rec.section!r}, programme={rec.programme!r})",
                    d,
                    d,
                )
            )

        # --- duplicates ------------------------------------------------------------
        if rec.source_uid in seen_uids:
            issues.append(
                ValidationIssue("duplicate", f"duplicate source_uid {rec.source_uid}", d, d)
            )
        seen_uids.add(rec.source_uid)

        if issues:
            report.failed.append((rec, issues))
        else:
            report.passed.append(rec)

    _check_overlaps(report)
    return report


def _check_overlaps(report: ValidationReport) -> None:
    """Reject records that overlap another valid record in the same context.

    Two entries overlap when they share (branch, batch, section, day) and their
    time ranges intersect. Club/sports whole-grid activities span the day and
    are exempt — they are not timed teaching slots.
    """
    groups: dict[tuple, list[TimetableRecord]] = {}
    for rec in report.passed:
        key = (rec.branch, rec.batch, rec.section, rec.day)
        groups.setdefault(key, []).append(rec)

    overlapping_uids: set[str] = set()
    for recs in groups.values():
        timed = [
            r
            for r in recs
            if r.start_time and r.end_time and r.entry_type not in {"sports", "club_activity"}
        ]
        for i, a in enumerate(timed):
            for b in timed[i + 1 :]:
                if a.start_time < b.end_time and b.start_time < a.end_time:
                    if a.source_uid != b.source_uid:
                        overlapping_uids.add(a.source_uid)
                        overlapping_uids.add(b.source_uid)

    if overlapping_uids:
        still_passed: list[TimetableRecord] = []
        for rec in report.passed:
            if rec.source_uid in overlapping_uids:
                d = rec.to_dict()
                report.failed.append(
                    (
                        rec,
                        [
                            ValidationIssue(
                                "no_overlap",
                                "overlaps another valid entry for the same day/context",
                                d,
                                d,
                            )
                        ],
                    )
                )
            else:
                still_passed.append(rec)
        report.passed = still_passed


def _valid_hhmm(value: str) -> bool:
    parts = value.split(":")
    if len(parts) != 2:
        return False
    h, m = parts
    return h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59


def _ghost_record(source_path: Path) -> TimetableRecord:
    return TimetableRecord(
        programme="?",
        branch="?",
        semester=0,
        batch="?",
        section="?",
        day="Monday",
        slot_index=0,
        start_time=None,
        end_time=None,
        course_code=None,
        course_name=None,
        source_id=source_path.name,
        source_page=0,
    )
