"""Class changes from a CR's notice: what, when, one-off or permanent.

"OS class cancelled tomorrow", "CSE 311 moved to Saturday 10 AM", "extra
DAA class on Friday at 4 PM" become structured one-off changes the CR
confirms before posting (public.class_changes via post_class_update). They
apply to that date only — every schedule answer honours them
(backend/query/schedule.py).

"From now on the lab is on Tuesdays" is a permanent change: it is NOT a
class change. The CR is sent to the timetable editor, and an admin approves
the new weekly timetable.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from . import rules, timetable_draft as td

PERMANENT_RE = re.compile(
    r"\b(from\s+now\s+on|henceforth|hereafter|permanent(ly)?|with\s+immediate\s+effect|revised\s+time\s*table|"
    r"new\s+time\s*table|till\s+the\s+end\s+of\s+(the\s+)?semester|for\s+the\s+rest\s+of\s+(the\s+)?semester|"
    r"every\s+(week|monday|tuesday|wednesday|thursday|friday|saturday)|all\s+(mondays|tuesdays|wednesdays|thursdays|"
    r"fridays|saturdays)|onwards)\b", re.I)
_CANCEL_RE = re.compile(r"\b(cancel+ed|cancel+ation|called\s+off|no\s+(class|lecture|lab)|will\s+not\s+be\s+(held|conducted)|"
                        r"won'?t\s+be\s+(held|there)|suspended)\b", re.I)
_RESCHEDULE_RE = re.compile(r"\b(resched\w*|moved|shifted|postponed|preponed|instead|changed\s+to|will\s+be\s+(held|conducted)\s+on)\b", re.I)
_EXTRA_RE = re.compile(r"\b(extra|additional|make[\s-]?up|compensat\w*|special)\s+(\S+\s+){0,3}(class|lecture|lab|session|tutorial)\b", re.I)
_CODE_RE = re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)|\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", re.I)
_TO_RE = re.compile(r"\b(to|on|at|instead\s+on)\b", re.I)


def is_permanent(text: str) -> bool:
    return bool(PERMANENT_RE.search(text or ""))


def change_type(text: str) -> Optional[str]:
    t = text or ""
    if _EXTRA_RE.search(t):
        return "extra"
    if _RESCHEDULE_RE.search(t):
        return "reschedule"
    if _CANCEL_RE.search(t):
        return "cancel"
    return None


def _times(text: str) -> list[str]:
    out = []
    for m in _TIME_RE.finditer(text or ""):
        if m.group(3):
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            pm = m.group(3).lower().startswith("p")
            h = (h % 12) + (12 if pm else 0)
        else:
            h, mi = int(m.group(4)), int(m.group(5))
            if 1 <= h <= 7:
                h += 12
        out.append(f"{h:02d}:{mi:02d}")
    return out


def _dates(text: str, today: date) -> list[date]:
    """Every date the text names, in order (split on "to"/"on" so "moved
    from Monday to Saturday" yields both)."""
    parts = re.split(r"\b(?:to|instead\s+on|shifted\s+to|moved\s+to)\b", text or "", flags=re.I)
    out = []
    for part in parts:
        d = rules.extract_date(part, today)
        if d and d not in out:
            out.append(d)
    return out


def find_course(text: str, courses: list[dict]) -> Optional[dict]:
    """The class's course the notice is about: by code, else by (a unique
    part of) its name or its initials ("OS", "DAA")."""
    m = _CODE_RE.search((text or "").upper())
    if m:
        code = f"{m.group(1)} {m.group(2)}"
        hit = next((c for c in courses if td.norm_code(c["course_code"]) == td.norm_code(code)), None)
        return hit or {"course_code": code, "course_name": None}
    low = (text or "").lower()
    skip = {"and", "of", "for", "the", "in", "to", "with", "a", "an", "&"}
    named = [c for c in courses if c.get("course_name") and c["course_name"].lower() in low]
    if len(named) == 1:
        return named[0]
    for c in courses:
        all_words = re.findall(r"[a-z]+", (c.get("course_name") or "").lower())
        # "DAA" (Design and Analysis of Algorithms) skips "and"/"of"; "TOC" keeps "of"
        for acro in ("".join(w[0] for w in all_words if w not in skip), "".join(w[0] for w in all_words if w != "and")):
            if len(acro) >= 2 and re.search(rf"\b{acro}\b", low):
                return c
    return None


def _class_periods(entries: list[dict], course_code: Optional[str], on: date) -> list[dict]:
    return [e for e in entries if e.get("day_of_week") == on.isoweekday()
            and (not course_code or td.norm_code(e.get("course_code")) == td.norm_code(course_code))]


def _add(hhmm: str, minutes: int) -> str:
    t = datetime.strptime(hhmm, "%H:%M") + timedelta(minutes=minutes)
    return t.strftime("%H:%M")


def extract(text: str, today: date, week: list[dict], courses: list[dict]) -> dict:
    """{"permanent": bool, "changes": [draft change], "notes": [...]} from a
    notice. `week` = the class's weekly timetable (current entries), used to
    fill in the original period and a sensible duration."""
    notes: list[str] = []
    if is_permanent(text):
        return {"permanent": True, "changes": [], "notes": [
            "This reads like a permanent change to the weekly timetable. Permanent changes are made in the "
            "timetable editor and approved by an admin."]}
    kind = change_type(text)
    if not kind:
        return {"permanent": False, "changes": [], "notes": []}
    course = find_course(text, courses)
    dates = _dates(text, today)
    times = _times(text)
    code = (course or {}).get("course_code")
    change = {"change_type": kind, "change_date": None, "course_code": code,
              "course_name": (course or {}).get("course_name"), "original_start": None, "original_end": None,
              "new_date": None, "new_start": None, "new_end": None, "note": None}
    if kind == "extra":
        on = dates[0] if dates else None
        change["change_date"] = on.isoformat() if on else None
        change["new_date"] = change["change_date"]
        if times:
            change["new_start"] = times[0]
            change["new_end"] = times[1] if len(times) > 1 else _add(times[0], 55)
        return {"permanent": False, "changes": [change], "notes": notes}
    on = dates[0] if dates else None
    change["change_date"] = on.isoformat() if on else None
    if on:
        periods = _class_periods(week, code, on)
        if len(periods) == 1:
            change["original_start"] = (periods[0].get("start_time") or "")[:5] or None
            change["original_end"] = (periods[0].get("end_time") or "")[:5] or None
        elif code and not periods:
            notes.append(f"Your timetable has no {code} on {on.strftime('%A %-d %B')} — check the date.")
    if kind == "reschedule":
        new_on = dates[1] if len(dates) > 1 else on
        change["new_date"] = new_on.isoformat() if new_on else None
        new_times = times[1:] if len(times) > 1 and change["original_start"] == times[0] else times
        if new_times:
            dur = 55
            if change["original_start"] and change["original_end"]:
                a = datetime.strptime(change["original_start"], "%H:%M")
                b = datetime.strptime(change["original_end"], "%H:%M")
                dur = int((b - a).total_seconds() // 60)
            change["new_start"] = new_times[0]
            change["new_end"] = new_times[1] if len(new_times) > 1 else _add(new_times[0], dur)
    return {"permanent": False, "changes": [change], "notes": notes}


def check(changes: list[dict], week: list[dict], today: date) -> list[td.Issue]:
    """Problems that block posting (errors) or are worth a look."""
    issues: list[td.Issue] = []
    if not changes:
        issues.append(td.Issue(-1, "changes", "Add at least one class change."))
    for i, c in enumerate(changes):
        kind = c.get("change_type")
        if kind not in ("cancel", "reschedule", "extra"):
            issues.append(td.Issue(i, "change_type", "Pick cancelled, rescheduled or extra class."))
            continue
        try:
            on = date.fromisoformat(str(c.get("change_date")))
        except ValueError:
            issues.append(td.Issue(i, "change_date", "Pick the date of the class."))
            continue
        if on < today - timedelta(days=1) or on > today + timedelta(days=90):
            issues.append(td.Issue(i, "change_date", "The date must be within the next 90 days."))
        if kind in ("cancel", "reschedule"):
            if not c.get("course_code"):
                issues.append(td.Issue(i, "course_code", "Which class is it? Pick the course."))
            elif not _class_periods(week, c["course_code"], on):
                issues.append(td.Issue(i, "course_code", f"Your timetable has no {c['course_code']} on "
                                                         f"{on.strftime('%A %-d %B')}."))
        if kind in ("reschedule", "extra"):
            start, end = td.norm_time(c.get("new_start")), td.norm_time(c.get("new_end"))
            if not start or not end:
                issues.append(td.Issue(i, "new_start", "Give the new start and end time."))
            elif start >= end:
                issues.append(td.Issue(i, "new_start", "The new class must end after it starts."))
            if kind == "reschedule" and not c.get("new_date"):
                issues.append(td.Issue(i, "new_date", "Pick the new date."))
            if kind == "extra" and not c.get("course_code") and not c.get("course_name"):
                issues.append(td.Issue(i, "course_code", "Which course is the extra class for?"))
    return issues


def storable(changes: list[dict]) -> list[dict]:
    keys = ("change_type", "change_date", "course_code", "course_name", "original_start", "original_end",
            "new_date", "new_start", "new_end", "note")
    out = []
    for c in changes:
        row = {k: c.get(k) for k in keys}
        for k in ("original_start", "original_end", "new_start", "new_end"):
            row[k] = td.norm_time(row[k]) if row.get(k) else None
        if row["change_type"] == "extra":
            row["new_date"] = row.get("new_date") or row.get("change_date")
        out.append(row)
    return out
