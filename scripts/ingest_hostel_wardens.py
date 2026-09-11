"""Hostel Wardens ingestion: PDF warden-team tables -> hostel_wardens.

Source: "Data/Structured/Wardens Team July 2026 - Students Copy.pdf" (3
pages). pdfplumber finds one clean table per warden team:

    ['Halls of Residence (Girls|Boys)', None, None]
    ['H1 ANAMUDI HOSTEL (GIRLS)\nH2 SAHYADRI HOSTEL (GIRLS)', None, None]
    ['HOSTEL WARDEN', 'STANDBY WARDEN', 'ASSISTANT WARDEN']
    ['Dr X\nphone\nmobile\nemail', 'Dr Y\n...', 'Dr Z\n...']
    ['', None, 'Dr W\n...']   # overflow rows: extra people under one role

plus one final table on page 3 for roles with no hall (Chief Warden,
Associate Dean, Hostel Manager, Security Officer) — parsed the same way but
without a hall association. The page's plain "Important E-Mail address"
block (IT Support / Outpass — addresses with no named person) is skipped:
it doesn't fit a person-shaped row and isn't guessed into one.

One row is emitted per (person, hall) pair since a warden team commonly
covers 2-4 halls — keeps "who is the warden for hall X" a plain lookup.

Usage:
    .venv/bin/python scripts/ingest_hostel_wardens.py                 # dry run
    .venv/bin/python scripts/ingest_hostel_wardens.py --import --approved-by "you@x"
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

SOURCE_PDF = Path("Data/Structured/Wardens Team July 2026 - Students Copy.pdf")
SOURCE_ID = SOURCE_PDF.name

_HALL_RE = re.compile(r"^(H\d+)\s+(.+)$")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")

# The non-hall roles table (page 3) prints exactly these four role labels —
# "Associate Dean" wraps onto a second line before the name starts. Matched
# by the literal printed text, not inferred.
_KNOWN_ROLE_PREFIXES: list[list[str]] = [
    ["Chief Warden"],
    ["Associate Dean (Hostel Affairs &", "Student Events)"],
    ["Hostel Manager"],
    ["Security Officer"],
]


def _clean(s: Optional[str]) -> str:
    return " ".join((s or "").split())


def _parse_person_block(cell: str) -> Optional[dict]:
    lines = [_clean(l) for l in (cell or "").split("\n") if _clean(l)]
    if not lines:
        return None
    name = lines[0]
    if _EMAIL_RE.fullmatch(name):
        # e.g. "IT Support" / "Outpass" blocks: an address with no named
        # person behind it — not a warden row, skip rather than fabricate one.
        return None
    email = None
    phones = []
    for line in lines[1:]:
        m = _EMAIL_RE.search(line)
        if m:
            email = m.group(0)
            rest = (line[: m.start()] + line[m.end() :]).strip(" ,")
            if rest:
                phones.append(rest)
        else:
            phones.append(line)
    return {"full_name": name, "phone": ", ".join(phones) if phones else None, "email": email}


def _parse_hall_block(text: str) -> list[tuple[str, str]]:
    halls = []
    for line in (text or "").split("\n"):
        line = _clean(line)
        m = _HALL_RE.match(line)
        if m:
            halls.append((m.group(1), m.group(2)))
    return halls


def extract() -> dict:
    wardens: list[dict] = []
    warnings: list[str] = []

    with pdfplumber.open(SOURCE_PDF) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.find_tables():
                data = table.extract()
                if not data:
                    continue
                first_cell = _clean(data[0][0]) if data[0] else ""

                if first_cell.startswith("Halls of Residence"):
                    if len(data) < 3:
                        warnings.append(f"page {page_no}: hall table too short: {data!r}")
                        continue
                    halls = _parse_hall_block(data[1][0] or "")
                    role_headers = [_clean(c).lower().replace(" ", "_") for c in data[2]]
                    if not halls:
                        warnings.append(f"page {page_no}: no halls parsed from {data[1]!r}")
                        continue
                    for row in data[3:]:
                        for col_idx, cell in enumerate(row):
                            if col_idx >= len(role_headers) or not cell:
                                continue
                            person = _parse_person_block(cell)
                            if person is None:
                                continue
                            role = role_headers[col_idx]
                            for hall_code, hall_name in halls:
                                wardens.append(
                                    {
                                        "hall_code": hall_code,
                                        "hall_name": hall_name,
                                        "role": role,
                                        "full_name": person["full_name"],
                                        "phone": person["phone"],
                                        "email": person["email"],
                                        "status": "active",
                                        "source_id": SOURCE_ID,
                                    }
                                )
                    continue

                if first_cell.startswith("Chief Warden"):
                    for row in data:
                        for cell in row:
                            if not cell:
                                continue
                            lines = [_clean(l) for l in cell.split("\n") if _clean(l)]
                            if len(lines) < 2 or not _EMAIL_RE.search(cell):
                                continue  # e.g. the "Important E-Mail address" block
                            prefix = next(
                                (p for p in _KNOWN_ROLE_PREFIXES if lines[: len(p)] == p), None
                            )
                            if prefix is None:
                                warnings.append(f"page {page_no}: unrecognized role block: {cell!r}")
                                continue
                            role = " ".join(prefix)
                            person = _parse_person_block("\n".join(lines[len(prefix) :]))
                            if person is None:
                                continue
                            wardens.append(
                                {
                                    "hall_code": None,
                                    "hall_name": None,
                                    "role": role.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("&", "and"),
                                    "full_name": person["full_name"],
                                    "phone": person["phone"],
                                    "email": person["email"],
                                    "status": "active",
                                    "source_id": SOURCE_ID,
                                }
                            )

    return {"source_id": SOURCE_ID, "wardens": wardens, "warnings": warnings}


def validate(preview: dict) -> list[str]:
    issues: list[str] = []
    if not preview["wardens"]:
        issues.append("no warden rows extracted")
    for w in preview["wardens"]:
        if not w["full_name"]:
            issues.append(f"warden row without a name: {w!r}")
        if not w["email"] and not w["phone"]:
            issues.append(f"warden row with no contact info at all: {w!r}")
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
        "hostel_wardens",
        "id,hall_code,hall_name,role,full_name,phone,email,status,source_id",
        filters={"source_id": SOURCE_ID},
    )

    def key(w: dict) -> tuple:
        return (w.get("hall_code"), w["role"], w["full_name"])

    existing_by_key = {key(e): e for e in existing}
    ins: list[dict] = []
    upd: list[tuple] = []
    unch = 0
    for w in preview["wardens"]:
        cur = existing_by_key.get(key(w))
        if cur is None:
            ins.append(w)
            continue
        patch = {c: w[c] for c in ("hall_name", "phone", "email", "status") if str(cur.get(c)) != str(w.get(c))}
        if patch:
            upd.append((cur["id"], patch))
        else:
            unch += 1

    if ins:
        client.table("hostel_wardens").insert(ins).execute()
    for wid, patch in upd:
        client.table("hostel_wardens").update(patch).eq("id", wid).execute()
    print(f"hostel_wardens          insert={len(ins):<4} update={len(upd):<4} unchanged={unch}")

    stats = {"wardens": {"inserted": len(ins), "updated": len(upd), "unchanged": unch}}
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
    ap = argparse.ArgumentParser(description="Ingest Hostel Wardens into ORION.")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--out-dir", default="Data/processed")
    args = ap.parse_args()

    preview = extract()
    issues = validate(preview)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    preview_path = out / "hostel_wardens_preview.json"
    preview_path.write_text(json.dumps({**preview, "validation_issues": issues}, indent=2))

    print(f"source:       {SOURCE_ID}")
    print(f"wardens:      {len(preview['wardens'])}")
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
