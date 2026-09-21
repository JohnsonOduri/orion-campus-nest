"""Full faculty rebuild from Data/iiit_kottayam_people.csv, keeping the
timetable's real dependencies intact.

The source CSV changed mid-task (the old iiit_kottayam_faculty.csv was
replaced with iiit_kottayam_people.csv, a richer, differently-shaped file):
  - it has a UTF-8 BOM — must open with encoding="utf-8-sig" or the first
    column reads as "﻿category", not "category";
  - it already carries a `category` column with almost exactly the values
    the user asked for: Administration, Head of Department, Faculty,
    Professional Support Staff;
  - it is one row per (person, ROLE), not one row per person — a person
    with multiple roles (e.g. "Dr. Ananth A" is both HOD and a teaching
    Assistant Professor) appears as multiple separate rows with the same
    name. These must be consolidated into one faculty record per person
    before anything else, or the same person would be inserted multiple
    times.
  - `research_interests` is only non-empty on Administration/Head of
    Department rows, where it's just a verbatim duplicate of that row's
    `designation` — not real research data. The real subject-matter list
    lives in `areas_of_work`, populated on the Faculty-category row
    instead. `specialization` is empty for all 204 rows — unused.

Context (do not re-derive — this was all verified live before writing this
script): the faculty table currently has 177 rows. Exactly 70 of those IDs
are referenced by timetable_entries.faculty_id / timetable_entry_faculty —
real class-schedule data from this session's timetable work. The other 107
were created by scripts/import_faculty_csv.py's earlier run and have ZERO
references anywhere. A literal "delete all, reinsert" would either violate
the foreign key on the 70 referenced rows or (if forced) orphan real
timetable data — neither is acceptable.

What this script actually does instead, to reach the same end state (a
faculty table that fully, cleanly matches the CSV) without that risk:

  1. Match every one of the 70 timetable-referenced rows to its CSV
     counterpart using three matching tiers, strongest first:
       a. name-token-set overlap >= 0.8
       b. positional abbreviation match (NEW — catches "Vineeth P" ==
          "Vineeth Palliyembil": same tokens in the same order, where a
          single-letter token abbreviates a fuller word in the other name)
       c. fuzzy string similarity >= 0.85 (NEW — catches spelling variants
          like "Dhakshyani K J" == "Dhakshayani J")
     All three were needed: (a) alone is what import_faculty_csv.py used
     and it silently created 5 duplicate rows for people it should have
     matched (found and fixed by hand in the previous session turn) —
     (b) and (c) close those exact gaps.
  2. UPDATE each matched referenced row IN PLACE (same id, so every
     timetable foreign key stays valid) with the CSV's full_name/email/
     phone/designation/office_location/profile_url/category. A referenced
     row with no confident CSV match (there are 2: "Ms. Priyamol" and the
     composite slot "RT/SP/NPG") is left untouched — there's nothing to
     safely change it to.
  3. DELETE every one of the 107 unreferenced rows, then INSERT a fresh
     row for every CSV person not consumed by step 1 — this is the actual
     "delete + reinsert" the user asked for, applied only to rows that
     were never safe to touch in the first place, err on the side of the
     side with zero blast radius.

Category classification (from the CSV's `designation` text, confirmed with
the user): "HOD" -> hod; Dean/Director/In-charge/Chairperson -> administrative;
any Professor title -> faculty; blank designation + non-Dr./Prof. title
(Ms./Mr./Mrs./Sr.) -> professional_support; blank designation + Dr./Prof.
title, OR a referenced (real teaching) row with no CSV match at all ->
faculty (being referenced by a real class in the timetable is itself
sufficient evidence of being teaching faculty, regardless of what the CSV
does or doesn't say).

Requires the category column (see
supabase/migrations/20260921000002_add_faculty_category.sql).

Usage:
    .venv/bin/python scripts/rebuild_faculty.py                 # dry run
    .venv/bin/python scripts/rebuild_faculty.py --apply
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.timetable.model import initials_from_name  # noqa: E402

CSV_PATH = Path("Data/iiit_kottayam_people.csv")
SOURCE_ID = "Data/iiit_kottayam_people.csv"

STOPWORDS = {"dr", "mr", "ms", "mrs", "prof", "professor", "sr"}
_FORMER_RE = re.compile(r"\b(former|retd\.?|retired)\b", re.IGNORECASE)
# The scrape emits this exact placeholder for anyone with no real profile
# page (an empty personalized path segment) — treat it as "no profile".
_PLACEHOLDER_PROFILE = "https://www.iiitkottayam.ac.in/#!pdf/faculty//"


def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = " ".join(text.split())
    return text or None


def _decode_email(raw: Optional[str]) -> Optional[str]:
    raw = _clean(raw)
    if not raw:
        return None
    email = re.sub(r"\s+at\s+", "@", raw, flags=re.IGNORECASE)
    email = re.sub(r"\s+dot\s+", ".", email, flags=re.IGNORECASE)
    return email if "@" in email else None


def _clean_profile(raw: Optional[str]) -> Optional[str]:
    raw = _clean(raw)
    if not raw or raw == _PLACEHOLDER_PROFILE:
        return None
    return raw

# The CSV's own category values, normalized to the 4 the user asked for.
_CATEGORY_MAP = {
    "head of department": "hod",
    "administration": "administrative",
    "faculty": "faculty",
    "professional support staff": "professional_support",
}
# When one person holds multiple roles (e.g. HOD + teaching faculty), the
# single stored category is the most senior/specific one.
_CATEGORY_PRIORITY = ["hod", "administrative", "faculty", "professional_support"]


def _status_from_designation(designation: Optional[str]) -> str:
    if designation and _FORMER_RE.search(designation):
        return "inactive"
    return "active"


def load_people_csv() -> list[dict]:
    """One row per (person, role) in the source -> one merged record per
    person here. A person's `category` is the highest-priority role they
    hold; `designation` prefers that same role's text (falling back to any
    non-empty designation across their rows); the research-interests text
    comes from `areas_of_work` on their Faculty-category row (that column,
    not `research_interests`, carries the real subject list — see module
    docstring) with the CSV's own `research_interests` as a fallback only
    when it isn't just a duplicate of the designation text."""
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        raw_rows = list(csv.DictReader(f))

    by_name: dict[str, list[dict]] = {}
    for r in raw_rows:
        name = _clean(r.get("name"))
        if not name:
            continue
        category = _CATEGORY_MAP.get((r.get("category") or "").strip().lower())
        designation = _clean(r.get("designation"))
        research_interests = _clean(r.get("research_interests"))
        areas_of_work = _clean(r.get("areas_of_work"))
        research_text = areas_of_work or (
            research_interests if research_interests and research_interests != designation else None
        )
        by_name.setdefault(name, []).append(
            {
                "category": category,
                "designation": designation,
                "research_text": research_text,
                "phone": _clean(r.get("phone")),
                "room": _clean(r.get("room")),
                "email": _decode_email(r.get("email")),
                "profile_url": _clean_profile(r.get("profile")),
            }
        )

    merged: list[dict] = []
    for name, rows in by_name.items():
        categories_seen = {r["category"] for r in rows if r["category"]}
        # Full set, most senior first — a person holding multiple roles
        # (e.g. HOD + teaching faculty) keeps every one of them, not just
        # the top-priority one; the priority order still decides which
        # role's row supplies the single-value fields below (designation,
        # research text, contact info), since those aren't arrays.
        categories = [c for c in _CATEGORY_PRIORITY if c in categories_seen] or ["faculty"]
        primary_row = next((r for r in rows if r["category"] == categories[0]), rows[0])

        def first_of(field: str, prefer=primary_row) -> Optional[str]:
            if prefer.get(field):
                return prefer[field]
            for r in rows:
                if r.get(field):
                    return r[field]
            return None

        designation = first_of("designation")
        research_text = first_of("research_text")
        merged.append(
            {
                "name": name,
                "categories": categories,
                "designation": designation,
                "research_text": research_text,
                "phone": first_of("phone"),
                "room": first_of("room"),
                "email": first_of("email"),
                "profile_url": first_of("profile_url"),
            }
        )
    return merged


def name_tokens_ordered(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", name.lower()) if t not in STOPWORDS]


def name_tokens_set(name: str) -> set[str]:
    return set(name_tokens_ordered(name))


def set_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def positional_abbrev_match(short: list[str], long: list[str]) -> bool:
    if len(short) < 2 or len(short) > len(long):
        return False
    exact_hits = 0
    for s, l in zip(short, long):
        if s == l:
            exact_hits += 1
            continue
        if len(s) == 1 and l.startswith(s):
            continue
        if len(l) == 1 and s.startswith(l):
            continue
        return False
    return exact_hits >= 1


def norm(name: str) -> str:
    return " ".join(name.lower().replace(".", " ").split())


def fuzzy_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_client() -> Any:
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def match_csv_row(db_name: str, csv_rows: list[dict], used_names: set[str]) -> Optional[dict]:
    """Best CSV match for a single referenced DB row, trying each tier in
    order of confidence. Returns None if nothing clears any tier."""
    candidates = [r for r in csv_rows if r["name"] not in used_names]
    db_tokens_set = name_tokens_set(db_name)
    db_tokens_ordered = name_tokens_ordered(db_name)

    # tier a: token-set overlap >= 0.8 — deliberately strict on its own
    # (tiers b/c below exist specifically to catch what this floor misses:
    # single-letter abbreviations and spelling variants, found live in the
    # previous session turn — a lower floor here would just reintroduce
    # the false-positive risk that made those two tiers necessary).
    scored = [(r, set_overlap(db_tokens_set, r["tokens_set"])) for r in candidates]
    scored = [(r, s) for r, s in scored if s >= 0.8]
    if scored:
        scored.sort(key=lambda rs: -rs[1])
        return scored[0][0]

    # tier b: positional abbreviation match, either direction
    for r in candidates:
        if positional_abbrev_match(db_tokens_ordered, r["tokens_ordered"]) or positional_abbrev_match(
            r["tokens_ordered"], db_tokens_ordered
        ):
            return r

    # tier c: fuzzy string similarity
    fuzzy_scored = [(r, fuzzy_ratio(db_name, r["name"])) for r in candidates]
    fuzzy_scored = [(r, s) for r, s in fuzzy_scored if s >= 0.85]
    if fuzzy_scored:
        fuzzy_scored.sort(key=lambda rs: -rs[1])
        return fuzzy_scored[0][0]

    return None


def build_patch(csv_row: dict) -> dict:
    return {
        k: v
        for k, v in {
            "full_name": csv_row["name"],
            "email": csv_row["email"],
            "office_location": csv_row["room"],
            "phone": csv_row["phone"],
            "designation": csv_row["designation"],
            "research_interests": csv_row["research_text"],
            "profile_url": csv_row["profile_url"],
            "category": csv_row["categories"],
        }.items()
        if v is not None
    }


def plan(client: Any) -> dict:
    csv_rows = load_people_csv()
    for row in csv_rows:
        row["tokens_set"] = name_tokens_set(row["name"])
        row["tokens_ordered"] = name_tokens_ordered(row["name"])

    all_rows = client.table("faculty").select("*").order("id").execute().data
    junction = client.table("timetable_entry_faculty").select("faculty_id").execute().data
    direct = client.table("timetable_entries").select("faculty_id").execute().data
    ref_ids = {r["faculty_id"] for r in junction} | {r["faculty_id"] for r in direct if r.get("faculty_id")}

    referenced = [r for r in all_rows if r["id"] in ref_ids]
    unreferenced = [r for r in all_rows if r["id"] not in ref_ids]
    assert len(referenced) + len(unreferenced) == len(all_rows)

    used_csv_names: set[str] = set()
    updates: list[dict] = []
    unmatched_referenced: list[str] = []

    for db_row in referenced:
        match = match_csv_row(db_row["full_name"], csv_rows, used_csv_names)
        if match is None:
            unmatched_referenced.append(db_row["full_name"])
            # Still referenced by real classes -> genuinely teaching
            # faculty, regardless of the CSV having nothing on them.
            if db_row.get("category") != ["faculty"]:
                updates.append({"id": db_row["id"], "full_name": db_row["full_name"], "csv_name": None, "patch": {"category": ["faculty"]}})
            continue
        used_csv_names.add(match["name"])
        patch = build_patch(match)
        updates.append({"id": db_row["id"], "full_name": db_row["full_name"], "csv_name": match["name"], "patch": patch})

    remaining_csv = [r for r in csv_rows if r["name"] not in used_csv_names]
    inserts = []
    for row in remaining_csv:
        inserts.append(
            {
                "full_name": row["name"],
                "initials": initials_from_name(row["name"]),
                "email": row["email"],
                "office_location": row["room"],
                "phone": row["phone"],
                "designation": row["designation"],
                "research_interests": row["research_text"],
                "profile_url": row["profile_url"],
                "category": row["categories"],
                "status": _status_from_designation(row["designation"]),
            }
        )

    # initials must stay unique against: the (unchanged) referenced rows'
    # initials, plus every other fresh insert in this same batch (the
    # unreferenced rows are all being deleted, so their initials free up).
    taken_initials = {r["initials"] for r in referenced}
    deduped_notes = []
    for row in inserts:
        base = row["initials"]
        if base not in taken_initials:
            taken_initials.add(base)
            continue
        n = 2
        while f"{base}{n}" in taken_initials:
            n += 1
        deduped_notes.append({"full_name": row["full_name"], "from": base, "to": f"{base}{n}"})
        row["initials"] = f"{base}{n}"
        taken_initials.add(row["initials"])

    return {
        "csv_total": len(csv_rows),
        "referenced_total": len(referenced),
        "unreferenced_total": len(unreferenced),
        "unreferenced_ids": [r["id"] for r in unreferenced],
        "updates": updates,
        "unmatched_referenced": unmatched_referenced,
        "inserts": inserts,
        "initials_deduped": deduped_notes,
    }


def apply(client: Any, result: dict, approved_by: str) -> dict:
    for u in result["updates"]:
        if u["patch"]:
            client.table("faculty").update(u["patch"]).eq("id", u["id"]).execute()

    if result["unreferenced_ids"]:
        client.table("faculty").delete().in_("id", result["unreferenced_ids"]).execute()

    inserted = 0
    if result["inserts"]:
        res = client.table("faculty").insert(result["inserts"]).execute()
        inserted = len(res.data or [])

    client.table("ingestion_runs").insert(
        {
            "source_id": SOURCE_ID,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "imported",
            "stats": {
                "faculty_updated": len(result["updates"]),
                "faculty_deleted": len(result["unreferenced_ids"]),
                "faculty_inserted": inserted,
            },
            "validation_errors": 0,
            "validation_warnings": len(result["unmatched_referenced"]),
            "approved_by": approved_by,
        }
    ).execute()
    return {"updated": len(result["updates"]), "deleted": len(result["unreferenced_ids"]), "inserted": inserted}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--approved-by", default=None)
    args = ap.parse_args()

    load_env()
    client = get_client()
    result = plan(client)

    print(f"CSV rows (deduplicated): {result['csv_total']}")
    print(f"timetable-referenced faculty rows (never deleted): {result['referenced_total']}")
    print(f"unreferenced faculty rows (will be deleted + rebuilt from CSV): {result['unreferenced_total']}")
    print()
    print(f"updates to referenced rows: {len(result['updates'])}")
    for u in result["updates"]:
        print(f"  [{u['id']}] {u['full_name']!r} <- csv {u['csv_name']!r}: {u['patch']}")
    print()
    print(f"referenced rows with NO CSV match (left as-is except category): {len(result['unmatched_referenced'])}")
    for n in result["unmatched_referenced"]:
        print(f"  {n!r}")
    print()
    print(f"fresh inserts: {len(result['inserts'])}")
    by_cat: dict[str, int] = {}
    for i in result["inserts"]:
        for c in i["category"]:
            by_cat[c] = by_cat.get(c, 0) + 1
    print(f"  by category (a person with multiple roles counts in each): {by_cat}")
    for i in result["inserts"][:8]:
        print(f"  {i['full_name']!r} [{i['initials']}] category={i['category']} status={i['status']}")
    if len(result["inserts"]) > 8:
        print(f"  ... and {len(result['inserts']) - 8} more")
    print()
    print(f"initials disambiguated: {len(result['initials_deduped'])}")
    for d in result["initials_deduped"]:
        print(f"  {d['full_name']!r}: {d['from']} -> {d['to']}")

    if not args.apply:
        print("\ndry run complete — re-run with --apply to write to Supabase")
        return 0

    if not args.approved_by:
        print("error: --apply requires --approved-by", file=sys.stderr)
        return 2

    stats = apply(client, result, args.approved_by)
    print("\nfinal stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
