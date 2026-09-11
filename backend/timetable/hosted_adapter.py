"""Adapt the extracted timetable preview to the ACTUAL hosted Supabase schema.

The hosted ORION project has an existing schema that differs from the local
migration:

  local migration                hosted (live)
  -----------------------------  ------------------------------------------
  faculty.initials (NOT NULL)    faculty.initials (nullable)
  courses.code/title/credits_raw courses.course_code/course_name/credits
  timetable_entries.branch       timetable_entries.department
  timetable_entries.source_uid   (added by hosted_schema_alignment.sql)
  timetable_entries.room (text)  timetable_entries.room_id (FK rooms only)
  approved_by text               approved_by uuid (auth.users)

This module bridges preview JSON -> hosted rows. It performs NO guessing:
values are only mapped/renamed. Faculty identity resolution combines the PDF
legend (authoritative) with repository faculty records
(Data/processed/people.json) when a legend name is absent — only an exact,
unambiguous initials match against official names is accepted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .model import initials_from_name

PEOPLE_JSON = Path("Data/processed/people.json")


@dataclass
class AdaptResult:
    entries: list[dict] = field(default_factory=list)
    courses: dict[str, dict] = field(default_factory=dict)
    faculty: dict[str, dict] = field(default_factory=dict)
    periods: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def load_preview(path: str | Any) -> dict:
    if hasattr(path, "read"):
        return json.load(path)
    with open(path) as f:
        return json.load(f)


def _date(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def load_people_initials() -> dict[str, str]:
    """Map deterministic initials -> official full name from people.json.

    Ambiguous (duplicated) initials are dropped from the map so resolution
    can never silently pick the wrong person.
    """
    if not PEOPLE_JSON.exists():
        return {}
    people = json.loads(PEOPLE_JSON.read_text())
    seen: dict[str, str] = {}
    dup: set[str] = set()
    for p in people:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        ini = initials_from_name(name)
        if not ini:
            continue
        if ini in seen and seen[ini] != name:
            dup.add(ini)
        seen.setdefault(ini, name)
    return {k: v for k, v in seen.items() if k not in dup}


def adapt_preview(preview: dict, source_id: Optional[str] = None) -> AdaptResult:
    """Map preview JSON records onto the hosted timetable_entries shape."""
    out = AdaptResult()
    src = source_id or preview["source"]["source_id"]
    recs = preview["records"]

    # courses: dedupe by course_code (hosted key)
    for r in recs:
        code = r.get("course_code")
        if not code:
            continue
        if code not in out.courses:
            out.courses[code] = {
                "course_code": code,
                "course_name": r.get("course_name") or code,
                # credits_raw is not in the preview records; hosted schema has
                # nullable `credits` — leave NULL rather than guess.
                "semester": r.get("semester"),
                "programme": r.get("programme"),
                "status": "active",
            }
        else:
            # cross-check consistency; never overwrite names with variants
            if out.courses[code]["course_name"] != (r.get("course_name") or code):
                out.issues.append(
                    f"course name mismatch for {code}: "
                    f"{out.courses[code]['course_name']!r} vs {r.get('course_name')!r}"
                )

    # faculty: initials -> best name (legend names are authoritative;
    # people.json resolves the rest only via an exact unique initials match)
    people_ini = load_people_initials()
    for r in recs:
        initials_list = r.get("faculty_initials") or []
        names_list = r.get("faculty_names") or []
        for i, ini in enumerate(initials_list):
            if not ini or ini in out.faculty:
                continue
            name = names_list[i] if i < len(names_list) else None
            if name:
                out.faculty[ini] = {"initials": ini, "full_name": name, "status": "active"}
            elif ini in people_ini:
                out.faculty[ini] = {
                    "initials": ini,
                    "full_name": people_ini[ini],
                    "status": "active",
                }
                out.issues.append(
                    f"faculty {ini!r} resolved from repository people.json "
                    f"(legend name absent): {people_ini[ini]}"
                )
            else:
                out.issues.append(f"faculty initials {ini!r} has no legend name")

    # periods: per-section period tables, deduped on (slot_index, start_time)
    seen_p: set[tuple] = set()
    timed_slots: set[int] = set()
    for sec in preview["source"]["sections"]:
        for col in sec.get("periods", []):
            if col.get("kind", "teaching") == "teaching" and col.get("start_time"):
                timed_slots.add(col["slot_index"])
    for sec in preview["source"]["sections"]:
        for col in sec.get("periods", []):
            h = col
            si, st = h.get("slot_index"), h.get("start_time")
            kind = h.get("kind", "teaching")
            # A teaching slot that already has a timed definition elsewhere in
            # the document does not get a second, time-less definition from a
            # stray header fragment (Word artifact on some pages).
            if kind == "teaching" and st is None and si in timed_slots:
                out.issues.append(
                    f"period artifact suppressed: slot {si} fragment without "
                    f"times on page {sec.get('page')} (slot already defined)"
                )
                continue
            key = (si, st, kind)
            if key in seen_p:
                continue
            seen_p.add(key)
            out.periods.append({
                "source_id": src,
                "slot_index": si,
                "start_time": st,
                "end_time": h.get("end_time"),
                "kind": kind,
                "is_time_derived": bool(h.get("derived") or h.get("is_time_derived")),
                "source_page": sec.get("page"),
            })

    # entries
    for r in recs:
        day = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
               "Friday": 5, "Saturday": 6, "Sunday": 7}.get(r["day"])
        if day is None:
            out.issues.append(f"unknown day {r['day']!r} in record {r.get('source_uid')}")
            continue
        # Saturday full-grid activities print no times; the hosted schema
        # allows NULL start/end (alignment migration), so keep them.
        out.entries.append({
            "course_id": None,        # resolved later against live courses
            "faculty_id": None,       # resolved later against live faculty
            "room_id": None,          # hosted has no room text column; rooms not imported
            "day_of_week": day,
            "slot_index": r.get("slot_index"),
            "start_time": r.get("start_time"),
            "end_time": r.get("end_time"),
            "semester": r.get("semester"),
            "programme": r.get("programme"),
            "department": r.get("branch"),
            "batch": r.get("batch"),
            "section": r.get("section"),
            "entry_type": r.get("entry_type"),
            "lab_batch": r.get("lab_batch"),
            "valid_from": r.get("valid_from"),
            "valid_until": r.get("valid_until"),
            "status": "active",
        })
    return out
