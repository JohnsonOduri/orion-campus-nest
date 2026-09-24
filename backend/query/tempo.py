"""Temporal reasoning: the one place a relative date reference becomes a
real date.

Why this module exists: "tomorrow" used to travel through the pipeline as
the *string* "tomorrow" and get re-parsed independently by
retrieval.mess_on_day(), retrieval.day_of_week_timetable() and
campus.free_time() — three chances to disagree, and they did ("tomorrow's
breakfast?" was answered with today's menu). Now the router resolves the
reference once (router.day_reference -> resolve_to_date), puts the ISO date
on the QueryPlan, and every layer below reads that.

Pure functions, no I/O, no Supabase, no LLM — so date behaviour can be
tested on its own (tests/test_tempo.py) and frozen against a fixed "today"
instead of whatever day CI happens to run on.

Everything is in IST. The API runs in Oregon and Supabase in ap-south-1, so
using the server's local date put the whole system a day behind between
00:00 and 05:30 IST — a real bug that reached production.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

IST_OFFSET = timedelta(hours=5, minutes=30)

WEEKDAY_TO_NUM = {
    "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
    "Friday": 5, "Saturday": 6, "Sunday": 7,
}
WEEKDAY_NAME = {v: k for k, v in WEEKDAY_TO_NUM.items()}


def now_ist() -> datetime:
    return datetime.now(timezone.utc) + IST_OFFSET


def today_ist() -> date:
    return now_ist().date()


# Ordered longest-phrase-first: "day after tomorrow" must win over the
# "tomorrow" inside it, and "next monday" over a bare "monday".
_DAY_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bday\s+after\s+tomorrow\b", re.I), "day after tomorrow"),
    (re.compile(r"\bday\s+before\s+yesterday\b", re.I), "day before yesterday"),
    (re.compile(r"\bthe\s+next\s+day\b", re.I), "tomorrow"),
    (re.compile(r"\btomorrow\b", re.I), "tomorrow"),
    (re.compile(r"\byesterday\b", re.I), "yesterday"),
    # "tonight"/"this evening"/"this afternoon" are still *today* as far as
    # any date-keyed table (timetable, mess menu) is concerned.
    (re.compile(r"\b(tonight|this\s+(evening|afternoon|morning))\b", re.I), "today"),
    (re.compile(r"\btoday\b", re.I), "today"),
]

_NEXT_WEEKDAY_RE = re.compile(
    r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I
)
_THIS_WEEKDAY_RE = re.compile(
    r"\b(?:this\s+|on\s+|coming\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I
)


# Typed questions misspell these constantly ("tomorow", "tommorow",
# "wendesday"). Getting the day wrong is the worst kind of wrong here,
# because the answer still looks confident — a misspelled "tomorrow" used
# to silently return *today's* menu. Fuzzy-matched per word rather than
# enumerated per misspelling, so unseen typos work too.
_FUZZY_DAY_WORDS = {
    "today", "tomorrow", "yesterday", "tonight",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}
_FUZZY_CUTOFF = 0.82
_WORD_RE = re.compile(r"[a-z]{4,}")


def _fuzzy_day_word(text: str) -> Optional[str]:
    import difflib

    for token in _WORD_RE.findall((text or "").lower()):
        if token in _FUZZY_DAY_WORDS:
            return token
        close = difflib.get_close_matches(token, _FUZZY_DAY_WORDS, n=1, cutoff=_FUZZY_CUTOFF)
        if close:
            return close[0]
    return None


def day_reference(text: str) -> Optional[str]:
    """The relative-date phrase a question uses, normalised — "tomorrow",
    "yesterday", "today", "day after tomorrow", "Monday", "next Monday" —
    or None when the question names no day at all. Recognising the phrase
    is deliberately separate from resolving it to a date so the router can
    record *what the user said* alongside the date it resolved to."""
    q = text or ""
    for pattern, label in _DAY_PHRASES:
        if pattern.search(q):
            return label
    m = _NEXT_WEEKDAY_RE.search(q)
    if m:
        return f"next {m.group(1).capitalize()}"
    m = _THIS_WEEKDAY_RE.search(q)
    if m:
        return m.group(1).capitalize()
    fuzzy = _fuzzy_day_word(q)
    if fuzzy:
        return "today" if fuzzy == "tonight" else fuzzy.capitalize() if fuzzy not in {
            "today", "tomorrow", "yesterday"} else fuzzy
    return None


def resolve_to_date(day_ref: Optional[str], today: Optional[date] = None) -> Optional[date]:
    """A phrase from day_reference() (or a bare weekday name) -> a real
    date. A named weekday means its next occurrence, counting today itself
    ("is there class on Wednesday?" asked on a Wednesday means today).

    "next <weekday>" means the same, except that it never resolves to today
    — "next Monday" on a Monday is a week away. Beyond that one case it is
    genuinely ambiguous in English (on a Thursday, "next Friday" means
    tomorrow to some people and eight days away to others), so it resolves
    to the nearest upcoming occurrence and every answer states the date it
    used ("on Friday (25 September)") rather than silently picking one
    reading."""
    if not day_ref:
        return None
    ref = day_ref.strip().lower()
    base = today or today_ist()
    if ref == "today":
        return base
    if ref == "tomorrow":
        return base + timedelta(days=1)
    if ref == "yesterday":
        return base - timedelta(days=1)
    if ref == "day after tomorrow":
        return base + timedelta(days=2)
    if ref == "day before yesterday":
        return base - timedelta(days=2)
    if ref.startswith("next "):
        target = WEEKDAY_TO_NUM.get(ref[5:].strip().capitalize())
        if target is None:
            return None
        return base + timedelta(days=((target - base.isoweekday()) % 7) or 7)
    target = WEEKDAY_TO_NUM.get(ref.capitalize())
    if target is None:
        return None
    return base + timedelta(days=(target - base.isoweekday()) % 7)


def relative_label(target: date, today: Optional[date] = None) -> Optional[str]:
    """"today"/"tomorrow"/"yesterday" for a date close to now, else None —
    for phrasing an answer about a date the user gave as a weekday name."""
    base = today or today_ist()
    delta = (target - base).days
    return {0: "today", 1: "tomorrow", -1: "yesterday"}.get(delta)
