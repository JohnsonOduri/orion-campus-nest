"""Supabase repository: idempotent writes + typed reads for timetable data.

The repository is the ONLY component that talks to Supabase. Ingestion runs
with the service-role key (server-side only); the API service reads through
the same PostgREST interface.

Idempotency contract:
  * courses    upsert on natural key `code`
  * faculty    upsert on natural key `initials`
  * entries    upsert on natural key `source_uid` (deterministic, see model)
  * periods    fetch-then-diff on (source_id, slot_index, start_time)
Running ingestion twice must not create duplicate rows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .extractor import Legend, LegendEntry
from .model import TimetableRecord

try:  # pragma: no cover - import guard keeps unit tests dependency-free
    from supabase import create_client, Client
except Exception:  # pragma: no cover
    create_client = None  # type: ignore[assignment]
    Client = Any  # type: ignore[misc,assignment]


class RepositoryError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RepositoryError(
            f"missing environment variable {name}; see .env.example"
        )
    return value


def load_repository() -> "TimetableRepository":
    """Build a repository from SUPABASE_URL + SUPABASE_SECRET_KEY."""
    if create_client is None:
        raise RepositoryError(
            "supabase package not installed; run `.venv/bin/pip install supabase`"
        )
    url = _require_env("SUPABASE_URL")
    key = _require_env("SUPABASE_SECRET_KEY") or _require_env("SUPABASE_SERVICE_ROLE_KEY")
    return TimetableRepository(create_client(url, key))


@dataclass
class ImportStats:
    courses_upserted: int = 0
    faculty_upserted: int = 0
    periods_upserted: int = 0
    entries_upserted: int = 0
    entries_skipped: int = 0


class TimetableRepository:
    """Thin, explicit data-access layer over PostgREST."""

    def __init__(self, client: Any) -> None:
        self.client = client

    # ------------------------------------------------------------- lookups

    def known_courses(self) -> dict[str, dict]:
        res = self.client.table("courses").select("code,title").execute()
        return {row["code"]: row for row in res.data or []}

    def known_faculty(self) -> dict[str, dict]:
        res = self.client.table("faculty").select("initials,full_name").execute()
        return {row["initials"]: row for row in res.data or []}

    def get_or_create_student_profile(
        self,
        user_id: str,
        *,
        semester: int,
        branch: str,
        batch: str,
        section: str,
        programme: str = "B.Tech",
        display_name: Optional[str] = None,
    ) -> dict:
        existing = (
            self.client.table("student_profiles")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        if existing.data:
            return existing.data[0]
        payload = {
            "user_id": user_id,
            "display_name": display_name,
            "semester": semester,
            "programme": programme,
            "branch": branch,
            "batch": batch,
            "section": section,
        }
        res = self.client.table("student_profiles").insert(payload).execute()
        return res.data[0]

    # ------------------------------------------------------------- imports

    def import_legend(self, legend: Legend, source_id: str) -> ImportStats:
        """Upsert courses + faculty discovered on one page's legend."""
        stats = ImportStats()
        seen_courses: set[str] = set()
        seen_faculty: set[str] = set()
        for entry in legend.entries:
            if entry.course_code not in seen_courses:
                seen_courses.add(entry.course_code)
                self._upsert_course(entry, source_id)
                stats.courses_upserted += 1
            for i, initials in enumerate(entry.faculty_initials):
                if initials in seen_faculty:
                    continue
                seen_faculty.add(initials)
                name = entry.faculty_names[i] if i < len(entry.faculty_names) else ""
                if not name:
                    continue
                self._upsert_faculty(initials, name, source_id)
                stats.faculty_upserted += 1
        return stats

    def _upsert_course(self, entry: LegendEntry, source_id: str) -> None:
        row = {
            "code": entry.course_code,
            "title": entry.course_name or entry.course_code,
            "credits_raw": entry.credits_raw,
            "source_id": source_id,
        }
        self.client.table("courses").upsert(
            row, on_conflict="code"
        ).execute()

    def _upsert_faculty(self, initials: str, full_name: str, source_id: str) -> None:
        row = {
            "initials": initials,
            "full_name": full_name,
            "source_id": source_id,
        }
        self.client.table("faculty").upsert(
            row, on_conflict="initials"
        ).execute()

    def import_periods(self, sections: list, source_id: str) -> ImportStats:
        """Insert period definitions that don't already exist for this source."""
        stats = ImportStats()
        existing_res = (
            self.client.table("timetable_periods")
            .select("slot_index,start_time,end_time,kind")
            .eq("source_id", source_id)
            .execute()
        )
        existing = {
            (r["slot_index"], r["start_time"], r["kind"]) for r in existing_res.data or []
        }
        for section in sections:
            for col in section.periods:
                h = col.header
                key = (h.slot_index, h.start, h.kind)
                if key in existing:
                    continue
                existing.add(key)
                self.client.table("timetable_periods").insert(
                    {
                        "source_id": source_id,
                        "slot_index": h.slot_index,
                        "start_time": h.start,
                        "end_time": h.end,
                        "kind": h.kind,
                        "is_time_derived": h.is_time_derived,
                        "source_page": section.page,
                    }
                ).execute()
                stats.periods_upserted += 1
        return stats

    def import_entries(
        self,
        records: list[TimetableRecord],
        source_id: str,
        *,
        approved_by: Optional[str] = None,
    ) -> ImportStats:
        """Upsert validated records; identical reruns change nothing."""
        stats = ImportStats()
        now = datetime.now(timezone.utc).isoformat()
        rows = [self._entry_row(r, source_id, now, approved_by) for r in records]
        # PostgREST has a per-request size limit; chunk conservatively.
        for chunk_start in range(0, len(rows), 200):
            chunk = rows[chunk_start : chunk_start + 200]
            self.client.table("timetable_entries").upsert(
                chunk, on_conflict="source_uid"
            ).execute()
            stats.entries_upserted += len(chunk)
        return stats

    def _entry_row(
        self,
        rec: TimetableRecord,
        source_id: str,
        now: str,
        approved_by: Optional[str],
    ) -> dict:
        return {
            "source_uid": rec.source_uid,
            "source_id": source_id,
            "source_page": rec.source_page,
            "day_of_week": rec.weekday_index,
            "slot_index": rec.slot_index,
            "start_time": rec.start_time,
            "end_time": rec.end_time,
            "course_code": rec.course_code or "",
            "course_name": rec.course_name or rec.course_code or "",
            "faculty_initials": rec.faculty_initials,
            "faculty_names": rec.faculty_names,
            "room": rec.room,
            "entry_type": rec.entry_type,
            "lab_batch": rec.lab_batch,
            "semester": rec.semester,
            "programme": rec.programme,
            "branch": rec.branch,
            "batch": rec.batch,
            "section": rec.section,
            "source_text": rec.source_text,
            "valid_from": rec.valid_from,
            "valid_until": rec.valid_until,
            "status": "active",
            "approved_at": now,
            "approved_by": approved_by or "ingestion-pipeline",
        }

    # -------------------------------------------------------------- audits

    def record_ingestion_run(
        self,
        source_id: str,
        status: str,
        stats: dict,
        validation_errors: int,
        validation_warnings: int,
        approved_by: Optional[str] = None,
    ) -> None:
        self.client.table("ingestion_runs").insert(
            {
                "source_id": source_id,
                "status": status,
                "stats": stats,
                "validation_errors": validation_errors,
                "validation_warnings": validation_warnings,
                "approved_by": approved_by,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

    # --------------------------------------------------------------- reads

    def rpc(self, fn: str, params: dict) -> Any:
        return self.client.rpc(fn, params).execute()

    def active_entries_for_context(
        self,
        *,
        semester: int,
        branch: str,
        batch: str,
        section: str,
        on_date: date,
    ) -> list[dict]:
        res = self.rpc(
            "orion_active_entries",
            {
                "p_semester": semester,
                "p_branch": branch,
                "p_batch": batch,
                "p_section": section,
                "p_on_date": on_date.isoformat(),
            },
        )
        return res.data or []

    def next_class(
        self,
        *,
        user_id: str,
        at: datetime,
        include_activities: bool = False,
    ) -> Optional[dict]:
        res = self.rpc(
            "orion_next_class",
            {
                "p_user_id": user_id,
                "p_at": at.isoformat(),
                "p_include_activities": include_activities,
            },
        )
        data = res.data
        if isinstance(data, list):
            data = data[0] if data else None
        return data

    def day_timetable(self, *, user_id: str, on_date: date) -> list[dict]:
        res = self.rpc(
            "orion_day_timetable",
            {"p_user_id": user_id, "p_on_date": on_date.isoformat()},
        )
        return res.data or []

    def week_timetable(self, *, user_id: str, on_date: date) -> list[dict]:
        res = self.rpc(
            "orion_week_timetable",
            {"p_user_id": user_id, "p_on_date": on_date.isoformat()},
        )
        return res.data or []
