"""Mess Menu ingestion: PDF weekly menu table -> mess_menus.

Source: Data/Structured/august_menu .pdf (1 page, one clean pdfplumber
table: DAY | BREAKFAST | LUNCH | SNACKS | DINNER, one row per weekday name).

The menu is printed per weekday (a recurring weekly pattern for the whole
month), but `mess_menus.menu_date` is a specific NOT NULL date with no
day-of-week/recurrence column — so each weekday's menu is materialized onto
every calendar date in August 2026 that falls on that weekday (mechanical
calendar arithmetic from the doc's own title "MESS MENU-AUGUST 2026", not an
invented mapping). Produces one row per (date, meal): 31 days x 4 meals.

Usage:
    .venv/bin/python scripts/ingest_mess_menu.py                 # dry run
    .venv/bin/python scripts/ingest_mess_menu.py --import --approved-by "you@x"
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pdfplumber

SOURCE_PDF = Path("Data/Structured/august_menu .pdf")
SOURCE_ID = SOURCE_PDF.name

YEAR = 2026
MONTH = 8
MEAL_COLUMNS = ["breakfast", "lunch", "snacks", "dinner"]


def _clean(s: Optional[str]) -> str:
    text = " ".join((s or "").split())
    return re.sub(r"\s*,\s*", ", ", text).strip(", ")


def extract() -> dict:
    warnings: list[str] = []
    menu_by_weekday: dict[str, dict[str, str]] = {}

    with pdfplumber.open(SOURCE_PDF) as pdf:
        table = max(
            pdf.pages[0].find_tables(),
            key=lambda t: (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1]),
        )
        data = table.extract()

    header = [_clean(c).upper() for c in data[0]]
    if header[0] != "DAY" or len(header) < 5:
        warnings.append(f"unexpected header row: {data[0]!r}")

    for row in data[1:]:
        if not row or not row[0]:
            continue
        weekday = _clean(row[0]).upper()
        if weekday not in calendar.day_name.__class__.__dict__ and weekday not in {
            "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY",
        }:
            warnings.append(f"row not a weekday, skipped: {row[0]!r}")
            continue
        menu_by_weekday[weekday] = {
            meal: _clean(row[i + 1]) for i, meal in enumerate(MEAL_COLUMNS) if i + 1 < len(row)
        }

    days_in_month = calendar.monthrange(YEAR, MONTH)[1]
    entries: list[dict] = []
    for day_num in range(1, days_in_month + 1):
        d = date(YEAR, MONTH, day_num)
        weekday = d.strftime("%A").upper()
        menu = menu_by_weekday.get(weekday)
        if menu is None:
            warnings.append(f"no menu row for weekday {weekday} ({d.isoformat()})")
            continue
        for meal in MEAL_COLUMNS:
            items = menu.get(meal, "")
            if not items:
                warnings.append(f"empty {meal} on {d.isoformat()} ({weekday})")
                continue
            entries.append(
                {
                    "menu_date": d.isoformat(),
                    "meal": meal,
                    "items": items,
                    "valid_from": f"{YEAR}-{MONTH:02d}-01",
                    "valid_until": d.replace(day=days_in_month).isoformat(),
                    "status": "active",
                    "source_id": SOURCE_ID,
                }
            )

    return {"source_id": SOURCE_ID, "entries": entries, "warnings": warnings}


def validate(preview: dict) -> list[str]:
    issues: list[str] = []
    if not preview["entries"]:
        issues.append("no mess-menu entries extracted")
    seen = set()
    for e in preview["entries"]:
        key = (e["menu_date"], e["meal"])
        if key in seen:
            issues.append(f"duplicate menu entry: {key!r}")
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
        "mess_menus",
        "id,menu_date,meal,items,valid_from,valid_until,status,source_id",
        filters={"source_id": SOURCE_ID},
    )
    existing_by_key = {(e["menu_date"], e["meal"]): e for e in existing}

    ins: list[dict] = []
    upd: list[tuple] = []
    unch = 0
    for e in preview["entries"]:
        key = (e["menu_date"], e["meal"])
        cur = existing_by_key.get(key)
        if cur is None:
            ins.append(e)
            continue
        patch = {
            c: e[c] for c in ("items", "valid_from", "valid_until", "status") if str(cur.get(c)) != str(e.get(c))
        }
        if patch:
            upd.append((cur["id"], patch))
        else:
            unch += 1

    for chunk_start in range(0, len(ins), 200):
        client.table("mess_menus").insert(ins[chunk_start : chunk_start + 200]).execute()
    for mid, patch in upd:
        client.table("mess_menus").update(patch).eq("id", mid).execute()
    print(f"mess_menus              insert={len(ins):<4} update={len(upd):<4} unchanged={unch}")

    stats = {"entries": {"inserted": len(ins), "updated": len(upd), "unchanged": unch}}
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
    ap = argparse.ArgumentParser(description="Ingest the August 2026 mess menu into ORION.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--out-dir", default="Data/processed")
    args = ap.parse_args()

    preview = extract()
    issues = validate(preview)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    preview_path = out / "mess_menu_august_2026_preview.json"
    preview_path.write_text(json.dumps({**preview, "validation_issues": issues}, indent=2))

    print(f"source:       {SOURCE_ID}")
    print(f"entries:      {len(preview['entries'])}")
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
