"""Introspect the LIVE Supabase schema via PostgREST OpenAPI definitions.

Prints column names/types for the timetable-related tables so the importer can
adapt to the ACTUAL hosted schema (never assumed). Read-only.

Usage: .venv/bin/python scripts/probe_schema.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import requests  # noqa: E402

url = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

res = requests.get(f"{url}/rest/v1/", headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=30)
res.raise_for_status()
spec = res.json()

tables = [
    "faculty", "courses", "rooms", "timetable_periods",
    "timetable_entries", "student_profiles", "ingestion_runs",
]
defs = spec.get("definitions", {})
for t in tables:
    d = defs.get(t)
    if not d:
        print(f"[{t}] NOT PRESENT in schema")
        continue
    print(f"[{t}]")
    for col, meta in d.get("properties", {}).items():
        fmt = meta.get("format") or meta.get("type")
        req = " NOT NULL" if col in d.get("required", []) else ""
        desc = (meta.get("description") or "").split(".")[0][:60]
        print(f"  {col:<22} {fmt}{req}  {desc}")
