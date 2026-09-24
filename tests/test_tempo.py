"""Offline tests for backend/query/tempo.py — relative-date resolution.

Every case pins "today" explicitly instead of using the real clock, so
these assert behaviour rather than whatever day CI happens to run on.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import tempo  # noqa: E402

# A Thursday, so "next Monday"/"this Friday" have unambiguous answers.
THURSDAY = date(2026, 9, 24)


@pytest.mark.parametrize("text,expected", [
    ("What's for lunch today?", "today"),
    ("Tomorrow's breakfast?", "tomorrow"),
    ("what did I have yesterday?", "yesterday"),
    ("classes on Monday", "Monday"),
    ("my timetable for next Friday", "next Friday"),
    ("the day after tomorrow", "day after tomorrow"),
    ("what about the next day?", "tomorrow"),
    ("anything on tonight?", "today"),
    ("What is the attendance requirement?", None),
    ("is the event free", None),
])
def test_day_reference_vocabulary(text, expected):
    assert tempo.day_reference(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("whats for lunch tomorow", "tomorrow"),
    ("tommorow breakfast", "tomorrow"),
    ("wendesday classes", "Wednesday"),
    ("yesterdy dinner", "yesterday"),
])
def test_day_reference_tolerates_misspellings(text, expected):
    """A misspelled day used to be ignored entirely, and the question then
    answered for *today* with no sign anything was missed — the worst kind
    of wrong, because the answer still looks confident."""
    assert tempo.day_reference(text) == expected


@pytest.mark.parametrize("text", ["money matters", "tomato curry", "free period", "greetings"])
def test_day_reference_does_not_invent_a_day(text):
    assert tempo.day_reference(text) is None


@pytest.mark.parametrize("ref,expected", [
    ("today", date(2026, 9, 24)),
    ("tomorrow", date(2026, 9, 25)),
    ("yesterday", date(2026, 9, 23)),
    ("day after tomorrow", date(2026, 9, 26)),
    ("day before yesterday", date(2026, 9, 22)),
    ("Friday", date(2026, 9, 25)),
    ("Thursday", date(2026, 9, 24)),   # today itself counts
    ("Wednesday", date(2026, 9, 30)),  # already past this week -> next one
    ("next Thursday", date(2026, 10, 1)),  # "next <today's weekday>" is never today
])
def test_resolve_to_date(ref, expected):
    assert tempo.resolve_to_date(ref, THURSDAY) == expected


def test_resolve_to_date_rejects_nonsense():
    assert tempo.resolve_to_date(None, THURSDAY) is None
    assert tempo.resolve_to_date("someday", THURSDAY) is None


def test_relative_label():
    assert tempo.relative_label(date(2026, 9, 25), THURSDAY) == "tomorrow"
    assert tempo.relative_label(date(2026, 9, 24), THURSDAY) == "today"
    assert tempo.relative_label(date(2026, 10, 5), THURSDAY) is None
