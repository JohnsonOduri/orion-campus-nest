"""Execute SQL against the hosted Supabase project via the Management API.

Uses SUPABASE_ACCESS_TOKEN (never logged). The project ref is derived from
SUPABASE_URL. Server-side administrative tooling only — never called from
browser/user-facing code (AGENTS.md §9).

Usage:
    .venv/bin/python scripts/supabase_sql.py --file migration.sql
    .venv/bin/python scripts/supabase_sql.py --query "select count(*) from public.timetable_entries"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests


def load_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def project_ref() -> str:
    url = os.environ["SUPABASE_URL"]
    return url.split("://", 1)[1].split(".supabase.co", 1)[0]


def run_sql(sql: str) -> dict:
    token = os.environ["SUPABASE_ACCESS_TOKEN"]
    ref = project_ref()
    api = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    res = requests.post(
        api,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"query": sql},
        timeout=120,
    )
    if res.status_code == 429:
        retry = int(res.headers.get("retry-after", "5"))
        time.sleep(retry)
        res = requests.post(
            api,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": sql},
            timeout=120,
        )
    if res.status_code >= 400:
        raise RuntimeError(f"SQL error {res.status_code}: {res.text[:2000]}")
    return res.json() if res.text else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Run admin SQL on the hosted Supabase project.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="Path to a .sql file")
    src.add_argument("--query", help="Inline SQL string")
    ap.add_argument("--json", action="store_true", help="Print raw JSON result")
    args = ap.parse_args()

    load_env()
    sql = Path(args.file).read_text() if args.file else args.query
    try:
        result = run_sql(sql)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for row in result:
            print(json.dumps(row, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
