"""Inspect a timetable PDF without touching the database.

Prints per-page structure: section title, period columns with resolved times,
day rows, legend size, and extraction warnings. Read-only diagnostic tool.

Usage:
    .venv/bin/python scripts/inspect_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"
    .venv/bin/python scripts/inspect_timetable.py --json <pdf>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.extractor import extract_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a timetable PDF (read-only).")
    parser.add_argument("pdf", help="Path to the timetable PDF")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    path = Path(args.pdf)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    doc = extract_document(path)

    pages = []
    for section in doc.sections:
        pages.append(
            {
                "page": section.page,
                "title": section.title,
                "metadata": (
                    {
                        "semester": section.metadata.semester,
                        "branch": section.metadata.branch,
                        "batch": section.metadata.batch,
                        "valid_from": section.metadata.valid_from,
                        "valid_until": section.metadata.valid_until,
                    }
                    if section.metadata
                    else None
                ),
                "periods": [
                    {
                        "slot": c.header.slot_index,
                        "start": c.header.start,
                        "end": c.header.end,
                        "kind": c.header.kind,
                        "derived": "[derived]" in c.header.raw,
                    }
                    for c in section.periods
                ],
                "legend_entries": len(section.legend.entries),
                "cells": len(section.records_raw),
                "warnings": section.warnings,
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "source_id": doc.source_id,
                    "pages_processed": doc.pages_processed,
                    "sections": pages,
                    "warnings": doc.warnings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"source: {doc.source_id}  ({doc.pages_processed} pages, {len(doc.sections)} grids)")
    for p in pages:
        print(f"\n page {p['page']}: {p['title']}")
        meta = p["metadata"]
        if meta:
            print(
                f"   sem={meta['semester']} branch={meta['branch']!r} batch={meta['batch']!r} "
                f"valid {meta['valid_from']}..{meta['valid_until']}"
            )
        periods = ", ".join(
            f"{c['slot']}:{c['start'] or c['kind']}{'*' if c['derived'] else ''}"
            for c in p["periods"]
        )
        print(f"   periods: {periods}")
        print(f"   legend: {p['legend_entries']} courses | cells: {p['cells']}")
        for w in p["warnings"]:
            print(f"   warning: {w}")
    for w in doc.warnings:
        print(f"document warning: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
