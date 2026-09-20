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

The actual row-fetching/fallback logic lives in backend/query/retrieval.py
(mess_all_active_rows/mess_menu_for_day/split_mess_items) — shared with the
AI chat's query router so both surfaces answer from one implementation.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request

from query.retrieval import mess_all_active_rows, mess_menu_for_day, split_mess_items

from .deps import get_current_client

router = APIRouter(prefix="/mess", tags=["mess"])


@router.get("/today")
def today_menu(request: Request):
    client = get_current_client(request)
    all_rows = mess_all_active_rows(client)
    rows = mess_menu_for_day(all_rows, date.today())
    return split_mess_items(sorted(rows, key=lambda r: r["meal"]))


@router.get("/week")
def week_menu(request: Request):
    client = get_current_client(request)
    all_rows = mess_all_active_rows(client)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    result: list[dict] = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        result.extend(mess_menu_for_day(all_rows, day))

    result.sort(key=lambda r: (r["display_date"], r["meal"]))
    return split_mess_items(result)
