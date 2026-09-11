"""Classroom Details ingestion: PDF table -> rooms + room_allocations.

Source: Data/Structured/Classroom Details_ODD_Sem _July_Nov_2026.pdf (1 page,
one pdfplumber table). Structure (verified via find_tables(), not a naive
text dump):

    "<batch-year> Batch- <ordinal> Semester Students"   section header
    "<N> Large/Small classroom(s)"  "<n>. <room_no>"  "Batch <n>" | "<dept>"
    ...
    "Lab arrangements"
    "<Lab family>"  "<lab name> (<room_no>)"

Large-classroom rows are allocated per numeric batch ("Batch 1".."Batch 5") —
printed as Arabic numerals in THIS document, unlike the Roman-numeral batch
field the timetable PDFs print ("BATCH-I"). Never assumed to be the same
identifier; stored exactly as printed (AGENTS.md §6/§34 — no guessing).
Small-classroom rows are allocated per department (ECE/CSY/AI&DS), no batch
number given. Lab rows have no batch/department context printed — imported
as rooms only, no room_allocations row.

Validity window: the filename states the term explicitly ("July_Nov_2026");
same window as the ODD-2026 timetables it accompanies.

Usage:
    .venv/bin/python scripts/ingest_classroom_details.py                 # dry run
    .venv/bin/python scripts/ingest_classroom_details.py --import --approved-by "you@x"
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

import pdfplumber

SOURCE_PDF = Path("Data/Structured/Classroom Details_ODD_Sem _July_Nov_2026.pdf")
SOURCE_ID = SOURCE_PDF.name
VALID_FROM = "2026-07-01"
VALID_UNTIL = "2026-11-30"

_SECTION_RE = re.compile(
    r"(?P<year>\d{4})\s*Batch\s*-\s*(?P<ord>\d+)\w{2}\s*Semester", re.IGNORECASE
)
_SIZE_RE = re.compile(r"(\d+)\s*(Large|Small)\s*Classroom", re.IGNORECASE)
_ROOM_RE = re.compile(r"^\d+\.\s*(.+)$")


def _clean(s: Optional[str]) -> str:
    return " ".join((s or "").split())


# The same department is printed "AI & DS" on one page and "AI&DS" on
# another (whitespace-only variance, same source document) — normalize to
# one spelling so room_allocations.department is queryable consistently.
_DEPT_ALIASES = {"AI & DS": "AI&DS"}


def _norm_department(s: str) -> str:
    return _DEPT_ALIASES.get(s, s)


def extract() -> dict:
    """Parse the PDF table into rooms + room_allocations, PDF-evidence only."""
    rooms: dict[str, dict] = {}
    allocations: list[dict] = []
    warnings: list[str] = []

    with pdfplumber.open(SOURCE_PDF) as pdf:
        table = max(
            pdf.pages[0].find_tables(),
            key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]),
        )
        data = table.extract()

    semester: Optional[int] = None
    room_type: Optional[str] = None
    in_labs = False
    lab_family: Optional[str] = None

    for row in data:
        c0, c1, c2 = (_clean(row[0]) if len(row) > 0 else "", _clean(row[1]) if len(row) > 1 else "", _clean(row[2]) if len(row) > 2 else "")

        if not c0 and not c1 and not c2:
            continue

        sm = _SECTION_RE.search(c0)
        if sm:
            semester = int(sm.group("ord"))
            in_labs = False
            continue

        if c0.lower() == "lab arrangements":
            in_labs = True
            room_type = None
            continue

        if in_labs:
            if c0.lower() == "lab":
                continue  # sub-header row ("Lab", "Room No")
            if c0:
                lab_family = c0
            m = re.match(r"^(.*)\((.+)\)\s*$", c1)
            if not m:
                warnings.append(f"lab row not understood: {row!r}")
                continue
            room_no = _clean(m.group(2))
            rooms[room_no] = {
                "room_no": room_no,
                "room_type": "lab",
                "capacity": None,
                "status": "active",
            }
            continue

        size_m = _SIZE_RE.search(c0) if c0 else None
        if size_m:
            room_type = f"{size_m.group(2).lower()}_classroom"

        room_m = _ROOM_RE.match(c1) if c1 else None
        if not room_m:
            continue
        raw_room = _clean(room_m.group(1))
        # "(Temporary)"-style annotations qualify an allocation, not the room
        # identity — stripping keeps the same physical room's rows merged
        # under one room_no instead of fabricating a duplicate room.
        annot_m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw_room)
        room_no = _clean(annot_m.group(1)) if annot_m else raw_room
        if annot_m:
            warnings.append(
                f"room {room_no!r}: dropped annotation {annot_m.group(2)!r} "
                f"(no schema field to record it; see source PDF)"
            )
        if room_type is None or semester is None:
            warnings.append(f"row without known context: {row!r}")
            continue

        rooms.setdefault(
            room_no,
            {"room_no": room_no, "room_type": room_type, "capacity": None, "status": "active"},
        )

        batch_m = re.match(r"^Batch\s*(\d+)$", c2, re.IGNORECASE)
        allocations.append(
            {
                "room_no": room_no,
                "semester": semester,
                "batch": batch_m.group(1) if batch_m else None,
                "department": None if batch_m else _norm_department(c2),
                "section": None,
                "valid_from": VALID_FROM,
                "valid_until": VALID_UNTIL,
                "status": "active",
                "source_id": SOURCE_ID,
            }
        )

    return {
        "source_id": SOURCE_ID,
        "rooms": sorted(rooms.values(), key=lambda r: r["room_no"]),
        "allocations": allocations,
        "warnings": warnings,
    }


def validate(preview: dict) -> list[str]:
    """Minimal but real checks — reject rather than silently repair."""
    issues: list[str] = []
    room_nos = {r["room_no"] for r in preview["rooms"]}
    for a in preview["allocations"]:
        if a["room_no"] not in room_nos:
            issues.append(f"allocation references unknown room {a['room_no']!r}")
        if a["semester"] not in {1, 3, 5, 7}:
            issues.append(f"unexpected semester {a['semester']!r} for room {a['room_no']!r}")
        if not a["batch"] and not a["department"]:
            issues.append(f"allocation for {a['room_no']!r} has neither batch nor department")
    if not preview["rooms"]:
        issues.append("no rooms extracted")
    return issues


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


def _fetch_all(client: Any, table: str, columns: str, filters: Optional[dict] = None) -> list[dict]:
    q = client.table(table).select(columns)
    for col, val in (filters or {}).items():
        q = q.eq(col, val)
    out: list[dict] = []
    offset = 0
    while True:
        page = q.range(offset, offset + 999).execute().data
        out.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    return out


def import_preview(preview: dict, approved_by: str) -> dict:
    client = get_client()

    # ---- rooms (natural key: room_no) -------------------------------------
    existing_rooms = {r["room_no"]: r for r in _fetch_all(client, "rooms", "id,room_no,room_type,capacity,status")}
    to_insert = [r for r in preview["rooms"] if r["room_no"] not in existing_rooms]
    to_update = []
    unchanged = 0
    for r in preview["rooms"]:
        cur = existing_rooms.get(r["room_no"])
        if cur is None:
            continue
        patch = {k: v for k, v in r.items() if k != "room_no" and cur.get(k) != v}
        if patch:
            to_update.append((cur["id"], patch))
        else:
            unchanged += 1
    if to_insert:
        client.table("rooms").insert(to_insert).execute()
    for rid, patch in to_update:
        client.table("rooms").update(patch).eq("id", rid).execute()
    print(f"rooms                  insert={len(to_insert):<4} update={len(to_update):<4} unchanged={unchanged}")

    room_id_by_no = {r["room_no"]: r["id"] for r in _fetch_all(client, "rooms", "id,room_no")}

    # ---- room_allocations (natural key: room_id+semester+batch+department+source_id)
    existing_allocs = _fetch_all(
        client,
        "room_allocations",
        "id,room_id,semester,batch,department,section,valid_from,valid_until,status,source_id",
        filters={"source_id": SOURCE_ID},
    )

    def key(a: dict) -> tuple:
        return (a["room_id"], a["semester"], a.get("batch"), a.get("department"), a["source_id"])

    existing_by_key = {key(a): a for a in existing_allocs}
    ins: list[dict] = []
    upd: list[tuple] = []
    unch = 0
    for a in preview["allocations"]:
        row = dict(a)
        row["room_id"] = room_id_by_no[row.pop("room_no")]
        k = key(row)
        cur = existing_by_key.get(k)
        if cur is None:
            ins.append(row)
            continue
        patch = {
            c: row[c]
            for c in ("section", "valid_from", "valid_until", "status")
            if str(cur.get(c)) != str(row.get(c))
        }
        if patch:
            upd.append((cur["id"], patch))
        else:
            unch += 1
    if ins:
        client.table("room_allocations").insert(ins).execute()
    for aid, patch in upd:
        client.table("room_allocations").update(patch).eq("id", aid).execute()
    print(f"room_allocations        insert={len(ins):<4} update={len(upd):<4} unchanged={unch}")

    stats = {
        "rooms": {"inserted": len(to_insert), "updated": len(to_update), "unchanged": unchanged},
        "allocations": {"inserted": len(ins), "updated": len(upd), "unchanged": unch},
    }
    client.table("ingestion_runs").insert(
        {
            "source_id": SOURCE_ID,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "imported",
            "stats": stats,
            "validation_errors": 0,
            "validation_warnings": len(preview["warnings"]),
            "approved_by": approved_by,
        }
    ).execute()
    print(f"\naudit: ingestion_runs recorded (approved_by={approved_by})")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest Classroom Details into ORION.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--out-dir", default="Data/processed")
    args = ap.parse_args()

    preview = extract()
    issues = validate(preview)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    preview_path = out / "classroom_details_odd_2026_preview.json"
    preview_path.write_text(json.dumps({**preview, "validation_issues": issues}, indent=2))

    print(f"source:       {SOURCE_ID}")
    print(f"rooms:        {len(preview['rooms'])}")
    print(f"allocations:  {len(preview['allocations'])}")
    print(f"warnings:     {len(preview['warnings'])}")
    for w in preview["warnings"]:
        print(f"  [warn] {w}")
    print(f"preview:      {preview_path}")

    if issues:
        print(f"\nVALIDATION FAILED for {len(issues)} issue(s). Nothing was imported.", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 1

    if not args.do_import:
        print("\ndry run complete — re-run with --import to write to Supabase")
        return 0

    if not args.approved_by:
        print("error: --import requires --approved-by", file=sys.stderr)
        return 2

    load_env()
    try:
        stats = import_preview(preview, args.approved_by)
    except Exception as exc:  # noqa: BLE001
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        return 1
    print("\nfinal stats:", json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
