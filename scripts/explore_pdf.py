"""One-off exploration of the S3 timetable PDF's table geometry.

Usage: .venv/bin/python scripts/explore_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

PDF = Path("Data/Structured/Semester 3_TimeTable_Odd_2026.pdf")


def main() -> None:
    with pdfplumber.open(PDF) as pdf:
        print(f"pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages):
            print(f"\n=== PAGE {i + 1} ===")
            print(f"size: {page.width:.0f} x {page.height:.0f}")
            tables = page.find_tables()
            print(f"tables found: {len(tables)}")
            for t_idx, table in enumerate(tables):
                print(f"\n--- table {t_idx} bbox={table.bbox} rows={len(table.rows)} ---")
                data = table.extract()
                for row in data[:30]:
                    print([c if c is None else (c.replace("\n", "\\n") or "") for c in row])
                if len(data) > 30:
                    print(f"... ({len(data)} rows total)")


if __name__ == "__main__":
    main()
