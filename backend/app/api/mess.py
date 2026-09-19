"""Mess menu — read-only.

124 real rows exist (31 days x 4 meals) but only for August 2026 as of this
writing. Confirmed the real data follows a fixed weekly rotation (Aug 1
Saturday's menu is byte-identical to Aug 8 Saturday's, etc. — a genuine
hostel mess practice, not a data artifact), so instead of showing "no menu"
once the calendar runs past the uploaded month, each day falls back to the
most recent uploaded menu for that same weekday. Every row is tagged
`is_actual` (an exact menu_date match) so the frontend can note when it's
showing a repeated cycle rather than a freshly uploaded one — never
presented as if it were newly published, just honestly reused.

`items` is stored as a single comma-separated string; split server-side
into a clean list.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request

from .deps import get_current_client

router = APIRouter(prefix="/mess", tags=["mess"])


def _split_items(rows: list[dict]) -> list[dict]:
    for row in rows:
        raw = row.get("items")
        row["items"] = [s.strip() for s in raw.split(",")] if raw else []
    return rows


def _all_active_rows(client) -> list[dict]:
    return (
        client.table("mess_menus")
        .select("id,menu_date,meal,items,status")
        .eq("status", "active")
        .execute()
        .data
        or []
    )


def _menu_for_day(all_rows: list[dict], target: date) -> list[dict]:
    """Rows for `target`, exact date first, else the most recent upload for
    the same weekday. Each returned row gets display_date (the calendar day
    being shown), source_date (the day the data actually came from), and
    is_actual (whether those two match)."""
    exact = [r for r in all_rows if r["menu_date"] == target.isoformat()]
    if exact:
        return [{**r, "display_date": target.isoformat(), "source_date": r["menu_date"], "is_actual": True} for r in exact]

    candidates = [r for r in all_rows if date.fromisoformat(r["menu_date"]).weekday() == target.weekday()]
    if not candidates:
        return []
    latest_date = max(c["menu_date"] for c in candidates)
    return [
        {**r, "display_date": target.isoformat(), "source_date": r["menu_date"], "is_actual": False}
        for r in candidates
        if r["menu_date"] == latest_date
    ]


@router.get("/today")
def today_menu(request: Request):
    client = get_current_client(request)
    all_rows = _all_active_rows(client)
    rows = _menu_for_day(all_rows, date.today())
    return _split_items(sorted(rows, key=lambda r: r["meal"]))


@router.get("/week")
def week_menu(request: Request):
    client = get_current_client(request)
    all_rows = _all_active_rows(client)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    result: list[dict] = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        result.extend(_menu_for_day(all_rows, day))

    result.sort(key=lambda r: (r["display_date"], r["meal"]))
    return _split_items(result)
