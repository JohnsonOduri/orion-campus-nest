"""Timetable service: pipeline orchestration + student-facing queries.

The service is the ONLY component the API layer talks to. It never accepts
academic context (semester/branch/batch/section) from clients: context comes
from the authenticated student's profile row in Supabase (AGENTS.md §7, §17).

Lifecycle rules (AGENTS.md §13):
  * queries return only status='active' rows with valid_from <= date <= valid_until;
  * breaks are never returned;
  * sports/club activities are excluded from "next class" unless explicitly
    requested via include_activities.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Optional

from .extractor import extract_document
from .normalizer import build_preview, dedupe, normalize_document
from .repository import TimetableRepository, load_repository
from .validator import ValidationReport, validate_records

# The demo student profile is a LOCAL DEVELOPMENT seed. When SUPABASE_URL is
# not configured the service can run in demo mode against it so the vertical
# slice is exercisable without a live database. Production calls must have a
# real authenticated user; demo mode never mixes contexts silently.
DEMO_STUDENT = {
    "user_id": "00000000-0000-0000-0000-0000000000d3",
    "display_name": "Demo Student (dev seed)",
    "semester": 3,
    "programme": "B.Tech",
    "branch": "COMPUTER SCIENCE AND ENGINEERING",
    "batch": "I",
    "section": "I",
}


# ------------------------------------------------------------------ pipeline


@dataclass
class PipelineResult:
    source_id: str
    source_path: Path
    preview: dict
    validation_report: ValidationReport
    imported: bool = False
    import_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.validation_report.ok


def run_pipeline(
    pdf_path: str | Path,
    *,
    source_id: Optional[str] = None,
    import_to_supabase: bool = False,
    approved_by: Optional[str] = None,
    repo: Optional[TimetableRepository] = None,
) -> PipelineResult:
    """Extract → normalize → validate → preview (→ import).

    With import_to_supabase=False this is the safe CR-style dry run: nothing
    touches the database. Importing requires an explicit flag and is audited
    in ingestion_runs (approved_by).
    """
    path = Path(pdf_path)
    sid = source_id or path.name

    doc = extract_document(path)
    results = normalize_document(doc)
    records = [r for res in results for r in res.records]
    records, _ = dedupe(records)

    known_courses = known_faculty = None
    if import_to_supabase and repo is not None:
        # cross-check legends against the DB directory before import
        try:
            known_courses = repo.known_courses()
            known_faculty = repo.known_faculty()
        except Exception:
            known_courses = known_faculty = None

    report = validate_records(records, path, known_courses, known_faculty)

    validation_summary = report.summary()
    preview = build_preview(doc, results, sid, validation_summary)

    result = PipelineResult(
        source_id=sid,
        source_path=path,
        preview=preview,
        validation_report=report,
    )

    if not import_to_supabase:
        return result

    if repo is None:
        result.import_error = "import requested but no repository provided"
        return result
    if not report.ok:
        # never import failing records — stop safely (Definition of Done #6)
        result.import_error = (
            f"validation failed for {len(report.failed)} record(s); "
            "nothing was imported"
        )
        return result

    try:
        stats_total = {
            "courses_upserted": 0,
            "faculty_upserted": 0,
            "periods_upserted": 0,
            "entries_upserted": 0,
        }
        for section in doc.sections:
            s = repo.import_legend(section.legend, sid)
            stats_total["courses_upserted"] += s.courses_upserted
            stats_total["faculty_upserted"] += s.faculty_upserted
        s = repo.import_periods(doc.sections, sid)
        stats_total["periods_upserted"] += s.periods_upserted
        s = repo.import_entries(report.passed, sid, approved_by=approved_by)
        stats_total["entries_upserted"] += s.entries_upserted

        repo.record_ingestion_run(
            sid,
            "imported",
            stats_total,
            validation_errors=len(report.failed),
            validation_warnings=len(preview["stats"]["warnings"]),
            approved_by=approved_by,
        )
        result.imported = True
        result.preview["import"] = stats_total
    except Exception as exc:  # noqa: BLE001 - surfaced to CLI caller
        result.import_error = f"supabase import failed: {exc}"
        try:
            repo.record_ingestion_run(
                sid,
                "failed",
                {},
                validation_errors=len(report.failed),
                validation_warnings=len(preview["stats"]["warnings"]),
            )
        except Exception:
            pass
    return result


def write_reports(result: PipelineResult, out_dir: str | Path = "Data/processed") -> dict[str, Path]:
    """Write preview + validation JSON reports (Phase 4 contract)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = result.source_path.stem.lower().replace(" ", "_")

    preview_path = out / f"{stem}_preview.json"
    preview_path.write_text(json_dumps(result.preview))

    validation = {
        "source_id": result.source_id,
        "summary": result.validation_report.summary(),
        "failed": [
            {
                "record": rec.to_dict(),
                "issues": [i.to_dict() for i in issues],
            }
            for rec, issues in result.validation_report.failed
        ],
    }
    validation_path = out / f"{stem}_validation.json"
    validation_path.write_text(json_dumps(validation))
    return {"preview": preview_path, "validation": validation_path}


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, ensure_ascii=False)


# ------------------------------------------------------------------- queries


class TimetableService:
    """Read-side service used by the API layer."""

    def __init__(self, repo: Optional[TimetableRepository] = None) -> None:
        self._repo = repo
        self._demo = False

    @property
    def repo(self) -> TimetableRepository:
        if self._repo is None:
            self._repo = load_repository()
        return self._repo

    @classmethod
    def demo(cls) -> "TimetableService":
        """Explicit demo instance (no Supabase); never used silently."""
        svc = cls.__new__(cls)
        svc._repo = None
        svc._demo = True
        return svc

    # ------------------------------------------------------------ context

    def student_context(self, user_id: Optional[str] = None) -> Optional[dict]:
        """The authenticated student's academic context (never client input).

        user_id may only be provided by trusted server-side callers; the SQL
        functions re-verify the caller's role and ignore it otherwise.
        """
        if self._demo:
            return dict(DEMO_STUDENT)
        res = self.repo.rpc("orion_student_context", {"p_user_id": user_id})
        data = res.data
        if isinstance(data, list):
            data = data[0] if data else None
        return data

    # ------------------------------------------------------------ queries

    def get_timetable_for_student(
        self, user_id: Optional[str] = None, on_date: Optional[date] = None
    ) -> list[dict]:
        """Full valid timetable for the student's context (any weekday)."""
        if self._demo:
            return demo_entries()
        ctx = self.student_context(user_id)
        if not ctx:
            return []
        return self.repo.active_entries_for_context(
            semester=ctx["semester"],
            branch=ctx["branch"],
            batch=ctx["batch"],
            section=ctx["section"],
            on_date=on_date or date.today(),
        )

    def get_today_timetable(self, user_id: Optional[str] = None) -> list[dict]:
        if self._demo:
            return [
                e
                for e in demo_entries()
                if e["day_of_week"] == _today_isodow()
            ]
        return self.get_timetable_for_student(user_id, on_date=date.today())

    def get_week_timetable(
        self, user_id: Optional[str] = None, on_date: Optional[date] = None
    ) -> list[dict]:
        if self._demo:
            return demo_entries()
        return self.repo.week_timetable(
            user_id=user_id, on_date=on_date or date.today()
        )

    def get_next_class(
        self,
        user_id: Optional[str] = None,
        *,
        at: Optional[datetime] = None,
        include_activities: bool = False,
    ) -> Optional[dict]:
        at = at or datetime.now(timezone.utc)
        if self._demo:
            return demo_next_class(at, include_activities)
        return self.repo.next_class(
            user_id=user_id, at=at, include_activities=include_activities
        )


# ------------------------------------------------------------- demo fixture


def _today_isodow() -> int:
    return date.today().isoweekday()


def demo_entries() -> list[dict]:
    """A tiny in-memory fixture mirroring the DB row shape for offline demo."""
    day = _today_isodow()
    return [
        {
            "course_code": "ICS 211",
            "course_name": "DESIGN AND ANALYSIS OF ALGORITHMS",
            "faculty_names": ["Dr. Priyadarshini"],
            "room": None,
            "day_of_week": day,
            "slot_index": 1,
            "start_time": "09:00:00",
            "end_time": "09:55:00",
            "entry_type": "class",
            "source_id": "demo",
        },
        {
            "course_code": "ICS 212",
            "course_name": "THEORY OF COMPUTATION",
            "faculty_names": ["Dr. Divya Sindhu Lekha", "Dr. Sushitha Susan Joseph"],
            "room": None,
            "day_of_week": day,
            "slot_index": 3,
            "start_time": "11:05:00",
            "end_time": "12:00:00",
            "entry_type": "class",
            "source_id": "demo",
        },
        {
            "course_code": None,
            "course_name": "CODING CLUB ACTIVITIES",
            "faculty_names": [],
            "room": None,
            "day_of_week": day,
            "slot_index": 8,
            "start_time": "17:00:00",
            "end_time": "19:00:00",
            "entry_type": "club_activity",
            "source_id": "demo",
        },
    ]


def demo_next_class(at: datetime, include_activities: bool) -> Optional[dict]:
    entries = demo_entries()
    now_t = at.timetz().replace(tzinfo=None).replace(microsecond=0)
    for e in entries:
        if not include_activities and e["entry_type"] in {"sports", "club_activity"}:
            continue
        start = time.fromisoformat(e["start_time"])
        end = time.fromisoformat(e["end_time"])
        if start <= now_t < end or now_t < start:
            return e
    return None
