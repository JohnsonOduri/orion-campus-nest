"""Read-only probe of the LIVE hosted Supabase project.

Checks which expected tables exist and their current row counts. Never writes.

Usage: .venv/bin/python scripts/probe_supabase.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env (name=value lines) without exposing values.
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from supabase import create_client  # noqa: E402

url = os.environ["SUPABASE_URL"]
key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
client = create_client(url, key)

TABLES = [
    "faculty",
    "courses",
    "rooms",
    "timetable_periods",
    "timetable_entries",
    "student_profiles",
    "ingestion_runs",
]

print(f"project: {url}")
for t in TABLES:
    try:
        res = client.table(t).select("*", count="exact").limit(0).execute()
        print(f"  {t:<20} exists, rows={res.count}")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0][:120]
        print(f"  {t:<20} ERROR: {msg}")

# Also check the timetable RPCs are deployed.
for fn in ("orion_student_context", "orion_next_class"):
    try:
        client.rpc(fn, {}).execute()
        print(f"  rpc {fn}(...) callable")
    except Exception as exc:  # noqa: BLE001
        print(f"  rpc {fn}(...) ERROR: {str(exc).splitlines()[0][:120]}")
