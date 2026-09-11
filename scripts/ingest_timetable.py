"""Timetable ingestion CLI: extract → normalize → validate → preview → import.

Implements the ORION CR/Admin approval flow for trusted structured sources
(AGENTS.md §8): the default mode is a SAFE DRY RUN producing preview and
validation JSON under Data/processed/. Nothing touches Supabase unless
--import is passed explicitly, and even then only fully valid records are
imported (fail-safe stop on validation errors).

Usage:
    # dry run (extract + validate + reports, no DB writes)
    .venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"

    # import into Supabase (requires SUPABASE_URL + SUPABASE_SECRET_KEY)
    .venv/bin/python scripts/ingest_timetable.py "Data/Structured/..." --import --approved-by "admin@iiitkottayam.ac.in"

Exit codes: 0 ok, 1 validation failed (dry run) or import refused, 2 runtime error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.timetable.service import run_pipeline, write_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a timetable PDF into ORION.")
    parser.add_argument("pdf", help="Path to the timetable PDF")
    parser.add_argument(
        "--source-id",
        default=None,
        help="Override the source identifier (defaults to the file name)",
    )
    parser.add_argument(
        "--import",
        dest="do_import",
        action="store_true",
        help="Import validated records into Supabase (default: dry run)",
    )
    parser.add_argument(
        "--approved-by",
        default=None,
        help="Identity recorded in the audit log for this import",
    )
    parser.add_argument(
        "--out-dir",
        default="Data/processed",
        help="Directory for preview/validation JSON (default: Data/processed)",
    )
    args = parser.parse_args()

    path = Path(args.pdf)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    repo = None
    if args.do_import:
        try:
            from backend.timetable.repository import load_repository

            repo = load_repository()
        except Exception as exc:  # noqa: BLE001
            print(f"error: cannot initialize Supabase repository: {exc}", file=sys.stderr)
            return 2

    result = run_pipeline(
        path,
        source_id=args.source_id,
        import_to_supabase=args.do_import,
        approved_by=args.approved_by,
        repo=repo,
    )

    reports = write_reports(result, args.out_dir)

    stats = result.preview["stats"]
    print(f"source:          {result.source_id}")
    print(f"pages:           {stats['pages_processed']}")
    print(f"records:         {stats['records_extracted']}")
    print(f"valid:           {stats['records_valid']}")
    print(f"rejected:        {stats['records_rejected']}")
    print(f"courses:         {len(stats['courses_discovered'])}")
    print(f"faculty:         {len(stats['faculty_discovered'])}")
    print(f"duplicates:      {stats['duplicate_records']}")
    print(f"warnings:        {len(stats['warnings'])}")
    print(f"preview report:  {reports['preview']}")
    print(f"validation:      {reports['validation']}")

    if not result.ok:
        print(
            f"\nVALIDATION FAILED for {len(result.validation_report.failed)} record(s). "
            "Nothing was imported.",
            file=sys.stderr,
        )
        for rec, issues in result.validation_report.failed[:10]:
            print(f"  - {rec.source_uid}: {[i.message for i in issues]}", file=sys.stderr)
        return 1

    if args.do_import:
        if result.import_error:
            print(f"\nIMPORT REFUSED: {result.import_error}", file=sys.stderr)
            return 1
        imp = result.preview.get("import", {})
        print(
            f"\nimported: courses={imp.get('courses_upserted', 0)} "
            f"faculty={imp.get('faculty_upserted', 0)} "
            f"periods={imp.get('periods_upserted', 0)} "
            f"entries={imp.get('entries_upserted', 0)} (idempotent upserts)"
        )
    else:
        print("\ndry run complete — re-run with --import to write to Supabase")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
