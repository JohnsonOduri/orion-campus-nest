"""Enrich live `faculty` rows with email/office/research interests from the
institute directory scrape (Data/processed/people.json).

The timetable legend is authoritative for identity (initials, full_name) —
this script never changes those. It only fills currently-NULL email,
office_location, research_interests, matching a faculty row to a
people.json person by:

  1. deterministic initials (model.initials_from_name — same mechanical
     transform already used for hosted timetable import), restricted to
     people.json entries whose main_roles includes "Faculty";
  2. initials must be *unambiguous* in people.json (two different names
     producing the same initials => neither is used, per AGENTS.md §6);
  3. a name-token sanity check (>=50% token overlap) — catches an initials
     collision between two different people that isn't caught by (2)
     because only one of the colliding names carries the "Faculty" role.

Anything that doesn't clear all three stays NULL rather than risk attaching
the wrong person's email/office to a faculty row.

Usage:
    .venv/bin/python scripts/enrich_faculty.py                 # dry run
    .venv/bin/python scripts/enrich_faculty.py --import --approved-by "you@x"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.model import initials_from_name  # noqa: E402

PEOPLE_JSON = Path("Data/processed/people.json")
SOURCE_ID = "Data/processed/people.json"

_STOPWORDS = {"dr", "mr", "ms", "mrs"}


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", name.lower()) if t not in _STOPWORDS}


def _clean_room(room: Optional[str]) -> Optional[str]:
    if not room:
        return None
    text = " ".join(room.split())
    return text or None


def _clean_areas(areas: Optional[list[str]]) -> Optional[str]:
    if not areas:
        return None
    # drop role-ish entries that leak into "areas" for HODs etc.
    cleaned = [a.strip() for a in areas if a.strip() and not a.strip().upper().startswith("HOD")]
    return "; ".join(cleaned) if cleaned else None


def build_people_index() -> dict[str, dict]:
    people = json.loads(PEOPLE_JSON.read_text())
    by_ini: dict[str, list[dict]] = {}
    for p in people:
        name = (p.get("name") or "").strip()
        if not name or "Faculty" not in (p.get("main_roles") or []):
            continue
        ini = initials_from_name(name)
        if ini:
            by_ini.setdefault(ini, []).append(p)
    return {ini: ps[0] for ini, ps in by_ini.items() if len(ps) == 1}


def load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_client() -> Any:
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def plan(client: Any) -> dict:
    people_by_ini = build_people_index()
    faculty = client.table("faculty").select(
        "id,initials,full_name,email,office_location,research_interests"
    ).execute().data

    updates: list[dict] = []
    skipped_no_match: list[str] = []
    skipped_name_mismatch: list[dict] = []
    skipped_already_filled: list[str] = []

    for f in faculty:
        person = people_by_ini.get(f["initials"])
        if person is None:
            skipped_no_match.append(f["initials"])
            continue
        a, b = _name_tokens(f["full_name"]), _name_tokens(person["name"])
        overlap = a & b
        if not a or not b or len(overlap) < min(len(a), len(b)) * 0.5:
            skipped_name_mismatch.append(
                {"db": f["full_name"], "people_json": person["name"], "initials": f["initials"]}
            )
            continue

        patch = {}
        if not f.get("email") and person.get("email"):
            patch["email"] = person["email"]
        if not f.get("office_location"):
            room = _clean_room(person.get("room"))
            if room:
                patch["office_location"] = room
        if not f.get("research_interests"):
            areas = _clean_areas(person.get("areas"))
            if areas:
                patch["research_interests"] = areas

        if patch:
            updates.append({"id": f["id"], "initials": f["initials"], "patch": patch})
        else:
            skipped_already_filled.append(f["initials"])

    return {
        "updates": updates,
        "skipped_no_match": skipped_no_match,
        "skipped_name_mismatch": skipped_name_mismatch,
        "skipped_already_filled": skipped_already_filled,
    }


def apply(client: Any, updates: list[dict], approved_by: str) -> dict:
    for u in updates:
        client.table("faculty").update(u["patch"]).eq("id", u["id"]).execute()
    client.table("ingestion_runs").insert(
        {
            "source_id": SOURCE_ID,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "imported",
            "stats": {"faculty_enriched": len(updates)},
            "validation_errors": 0,
            "validation_warnings": 0,
            "approved_by": approved_by,
        }
    ).execute()
    return {"faculty_enriched": len(updates)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich faculty from Data/processed/people.json.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    args = ap.parse_args()

    load_env()
    client = get_client()
    result = plan(client)

    print(f"faculty to enrich:          {len(result['updates'])}")
    for u in result["updates"]:
        print(f"  [{u['initials']}] {sorted(u['patch'].keys())}")
    print(f"no unambiguous people.json match: {len(result['skipped_no_match'])} {result['skipped_no_match']}")
    print(f"name-mismatch (rejected):   {len(result['skipped_name_mismatch'])}")
    for m in result["skipped_name_mismatch"]:
        print(f"  [{m['initials']}] db={m['db']!r} vs people.json={m['people_json']!r}")
    print(f"already fully populated:    {len(result['skipped_already_filled'])}")

    if not args.do_import:
        print("\ndry run complete — re-run with --import to write to Supabase")
        return 0

    if not args.approved_by:
        print("error: --import requires --approved-by", file=sys.stderr)
        return 2

    stats = apply(client, result["updates"], args.approved_by)
    print("\nfinal stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
