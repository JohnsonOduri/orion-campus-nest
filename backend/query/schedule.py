"""One-off class changes applied to a day's timetable.

A CR announces "OS class cancelled tomorrow", "DBMS moved to Saturday 10
AM", "extra DAA class Friday 4 PM" (backend/app/api/cr.py → the
post_class_update RPC → public.class_changes). The weekly timetable doesn't
change — these rows apply to one date only, and every schedule answer
(today / tomorrow / a day / free time / next class / the /timetable page)
applies them through `apply()` so it never shows a cancelled class as on,
or misses an extra one.

Permanent changes are not handled here: they are timetable proposals an
admin approves (review_cr_timetable).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Optional

from . import tempo

_FIELDS = ("id,semester,department,batch,section,change_type,change_date,course_code,course_name,original_start,"
           "original_end,new_date,new_start,new_end,note,announcement_id")


def _norm_code(code: Optional[str]) -> str:
    return re.sub(r"\s+", "", (code or "").upper())


def _hhmm(t: Optional[str]) -> Optional[str]:
    return str(t)[:5] if t else None


def for_class(rows: list[dict], ctx: Optional[dict]) -> list[dict]:
    """Changes that apply to the caller's class."""
    if not ctx:
        return []
    out = []
    for r in rows:
        if r.get("semester") != ctx.get("semester") or r.get("department") != ctx.get("department"):
            continue
        if r.get("section") and ctx.get("section") and str(r["section"]) != str(ctx["section"]):
            continue
        out.append(r)
    return out


def fetch(client: Any, start: date, end: date, ctx: Optional[dict] = None) -> list[dict]:
    """Active changes touching [start, end] (as the original date or the new
    date) for the caller's class. `ctx` is orion_student_context; fetched
    when not given. Never raises: a failure means "no changes known"."""
    try:
        if ctx is None:
            ctx = client.rpc("orion_student_context").execute().data
        if not ctx:
            return []
        rows = (client.table("class_changes").select(_FIELDS).eq("status", "active")
                .eq("semester", ctx.get("semester")).eq("department", ctx.get("department"))
                .or_(f"and(change_date.gte.{start.isoformat()},change_date.lte.{end.isoformat()}),"
                     f"and(new_date.gte.{start.isoformat()},new_date.lte.{end.isoformat()})")
                .execute().data or [])
    except Exception:  # noqa: BLE001 - a schedule answer must not fail because of this
        return []
    return for_class(rows, ctx)


def _matches(entry: dict, change: dict) -> bool:
    if change.get("course_code") and _norm_code(entry.get("course_code")) != _norm_code(change["course_code"]):
        return False
    if change.get("original_start") and _hhmm(entry.get("start_time")) != _hhmm(change["original_start"]):
        return False
    return bool(change.get("course_code") or change.get("original_start"))


def apply(entries: list[dict], changes: list[dict], on: date) -> list[dict]:
    """The day's entries with that date's changes applied:
      - cancelled (or moved-away) periods stay in the list, marked
        `_cancelled` with the reason, so answers can say "cancelled";
      - moved-in and extra classes are added, marked `_moved_from` / `_extra`.
    Sorted by start time."""
    day = on.isoformat()
    out = [dict(e) for e in entries]
    for c in changes:
        if c.get("change_type") in ("cancel", "reschedule") and str(c.get("change_date")) == day:
            for e in out:
                if _matches(e, c) and not e.get("_cancelled"):
                    e["_cancelled"] = True
                    e["_change_note"] = (c.get("note") or ("cancelled" if c["change_type"] == "cancel" else
                                          f"moved to {tempo.WEEKDAY_NAME.get(date.fromisoformat(str(c['new_date'])).isoweekday(), '')} "
                                          f"{str(c['new_date'])} {_hhmm(c.get('new_start'))}"))
        target = str(c.get("new_date") or c.get("change_date"))
        if c.get("change_type") in ("reschedule", "extra") and target == day and c.get("new_start"):
            template = next((e for e in entries if _norm_code(e.get("course_code")) == _norm_code(c.get("course_code"))), {})
            out.append({
                **{k: template.get(k) for k in ("course_code", "course_name", "faculty_names", "room", "entry_type")},
                "course_code": c.get("course_code") or template.get("course_code"),
                "course_name": template.get("course_name") or c.get("course_name"),
                "entry_type": template.get("entry_type") or "class",
                "id": -int(c.get("id") or 0),  # the page keys rows by id; negative = a change
                "slot_index": None,
                "day_of_week": on.isoweekday(),
                "start_time": f"{_hhmm(c['new_start'])}:00", "end_time": f"{_hhmm(c['new_end'])}:00",
                "_extra": c["change_type"] == "extra",
                "_moved_from": (f"{c['change_date']} {_hhmm(c.get('original_start')) or ''}".strip()
                                if c["change_type"] == "reschedule" else None),
                "_change_note": c.get("note"),
                "source_text": c.get("course_name") if not (c.get("course_code") or template) else None,
            })
    return sorted(out, key=lambda e: (e.get("start_time") or "", e.get("_cancelled", False)))


def active(entries: list[dict]) -> list[dict]:
    """What actually happens that day (cancelled periods dropped)."""
    return [e for e in entries if not e.get("_cancelled")]


def week_dates(on: Optional[date] = None) -> tuple[date, date]:
    today = on or tempo.today_ist()
    start = today - timedelta(days=today.isoweekday() - 1)
    return start, start + timedelta(days=6)
