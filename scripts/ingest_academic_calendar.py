"""Academic Calendar ingestion: PDF "Academic Highlights" table -> academic_calendar.

Source: Data/Structured/Odd 2026-27_academic_calendar.pdf (1 page).
pdfplumber finds one 57-row table for the whole page: rows 0-39 are the
month-by-month day grid (Jul-Dec 2026, merged cells, ambiguous multi-event
cells — not used, too error-prone to parse reliably), rows 41-56 are a clean
two-column "Sl No | Academic Highlights | ... | Dates" summary with exact
DD-MM-YYYY dates already spelled out. That summary is the source of truth
here: unambiguous, authoritative, and evidenced directly (AGENTS.md §6) —
never inferred from the day-grid's cell positions.

A highlight naming two dates ("Second Class Committee Meeting ... \n
23-09-2026\n24-09-2026") becomes one academic_calendar row per date — the
schema has no end_date column (CLAUDE.md §11: "academic_calendar Uses
event_date; do not assume end_date").

`applies_to_semester` is left NULL: the calendar's own title says it covers
three semesters at once ("Sem III,V,VII"), and the column can only hold one
integer — picking one would misrepresent scope, so it's left unset rather
than guessed.

Usage:
    .venv/bin/python scripts/ingest_academic_calendar.py                 # dry run
    .venv/bin/python scripts/ingest_academic_calendar.py --import --approved-by "you@x"
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

SOURCE_PDF = Path("Data/Structured/Odd 2026-27_academic_calendar.pdf")
SOURCE_ID = SOURCE_PDF.name

_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")

# Mechanical keyword classification of the printed highlight name — never a
# guess about facts, just a label for UI filtering. First match wins.
_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("exam", "exam"),
    ("registration", "registration"),
    ("class committee meeting", "meeting"),
    ("class begin", "term_milestone"),
    ("classes begin", "term_milestone"),
    ("class ends", "term_milestone"),
    ("semester ends", "term_milestone"),
    ("result", "result"),
    ("fee payment", "deadline"),
    ("last day", "deadline"),
    ("last date", "deadline"),
    ("submission", "deadline"),
    ("review", "review"),
    ("evaluation", "evaluation"),
    ("sports meet", "event"),
    ("hostel", "administrative"),
]


def _clean(s: Optional[str]) -> str:
    return " ".join((s or "").split())


def _classify(name: str) -> Optional[str]:
    lowered = name.lower()
    for needle, etype in _TYPE_KEYWORDS:
        if needle in lowered:
            return etype
    return None


def _iso(d: str, m: str, y: str) -> str:
    return f"{y}-{m}-{d}"


def _parse_highlight_group(sl_no_cell: str, name_cell: str, dates_cell: str, warnings: list[str]) -> list[dict]:
    sl_no_cell = _clean(sl_no_cell)
    name_cell = _clean(name_cell)
    if not sl_no_cell or not name_cell:
        return []
    dates = _DATE_RE.findall(dates_cell or "")
    if not dates:
        warnings.append(f"highlight #{sl_no_cell} {name_cell!r} has no parseable date: {dates_cell!r}")
        return []
    out = []
    for d, m, y in dates:
        out.append(
            {
                "event_name": name_cell,
                "event_date": _iso(d, m, y),
                "event_type": _classify(name_cell),
                "applies_to_semester": None,
                "status": "active",
                "source_id": SOURCE_ID,
            }
        )
    return out


def extract() -> dict:
    events: list[dict] = []
    warnings: list[str] = []

    with pdfplumber.open(SOURCE_PDF) as pdf:
        table = max(
            pdf.pages[0].find_tables(),
            key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]),
        )
        data = table.extract()

    header_idx = next(
        (i for i, row in enumerate(data) if row and _clean(row[0]) == "Sl No"), None
    )
    if header_idx is None:
        warnings.append("'Sl No' highlights header not found — no events extracted")
        return {"source_id": SOURCE_ID, "events": [], "warnings": warnings}

    for row in data[header_idx + 1 :]:
        if row is None:
            continue
        events.extend(_parse_highlight_group(row[0], row[1], row[7], warnings))
        if len(row) > 13:
            events.extend(_parse_highlight_group(row[8], row[9], row[13], warnings))

    events.sort(key=lambda e: e["event_date"])
    if events:
        valid_from = "2026-07-01"
        valid_until = events[-1]["event_date"]
        for e in events:
            e["valid_from"] = valid_from
            e["valid_until"] = valid_until

    return {"source_id": SOURCE_ID, "events": events, "warnings": warnings}


def validate(preview: dict) -> list[str]:
    issues: list[str] = []
    if not preview["events"]:
        issues.append("no academic-calendar events extracted")
    seen = set()
    for e in preview["events"]:
        try:
            datetime.strptime(e["event_date"], "%Y-%m-%d")
        except ValueError:
            issues.append(f"malformed event_date: {e!r}")
        key = (e["event_name"], e["event_date"])
        if key in seen:
            issues.append(f"duplicate event: {key!r}")
        seen.add(key)
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

    existing = _fetch_all(
        client,
        "academic_calendar",
        "id,event_name,event_date,event_type,applies_to_semester,valid_from,valid_until,status,source_id",
        filters={"source_id": SOURCE_ID},
    )
    existing_by_key = {(e["event_name"], e["event_date"]): e for e in existing}

    ins: list[dict] = []
    upd: list[tuple] = []
    unch = 0
    for e in preview["events"]:
        key = (e["event_name"], e["event_date"])
        cur = existing_by_key.get(key)
        if cur is None:
            ins.append(e)
            continue
        patch = {
            c: e[c]
            for c in ("event_type", "applies_to_semester", "valid_from", "valid_until", "status")
            if str(cur.get(c)) != str(e.get(c))
        }
        if patch:
            upd.append((cur["id"], patch))
        else:
            unch += 1

    if ins:
        client.table("academic_calendar").insert(ins).execute()
    for eid, patch in upd:
        client.table("academic_calendar").update(patch).eq("id", eid).execute()
    print(f"academic_calendar      insert={len(ins):<4} update={len(upd):<4} unchanged={unch}")

    stats = {"events": {"inserted": len(ins), "updated": len(upd), "unchanged": unch}}
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
    ap = argparse.ArgumentParser(description="Ingest Academic Calendar into ORION.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--out-dir", default="Data/processed")
    args = ap.parse_args()

    preview = extract()
    issues = validate(preview)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    preview_path = out / "academic_calendar_odd_2026_preview.json"
    preview_path.write_text(json.dumps({**preview, "validation_issues": issues}, indent=2))

    print(f"source:       {SOURCE_ID}")
    print(f"events:       {len(preview['events'])}")
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
