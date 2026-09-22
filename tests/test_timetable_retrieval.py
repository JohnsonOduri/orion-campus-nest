"""Regression test for AI-test.md's most significant finding (2026-09-22):
`day_timetable`/`week_timetable` silently returned zero entries for the
default "today"/"this week" case — confirmed live against a real student
with an ongoing class ("What classes do I have today?" answered "no
classes"). Root cause: `client.rpc(name, {"p_on_date": None, ...})` sends a
literal JSON `null`, which defeats the RPC's SQL `default` (a default only
applies when the parameter is OMITTED, not when it's explicitly null) —
`orion_active_entries`'s WHERE clause then compares every row against a
NULL date, matching nothing.

This test's whole point is to fail if `on_date=None` is ever sent as an
explicit key again — it inspects the literal params dict handed to
`.rpc()`, not just the return value, since a fake client that "does the
right thing anyway" would hide exactly this bug the way the real
supabase-py client didn't.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import retrieval  # noqa: E402


class FakeSupabase:
    """Records the exact params dict every .rpc() call receives."""

    def __init__(self, data=None):
        self.data = data if data is not None else []
        self.rpc_calls: list[tuple[str, dict]] = []

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.data))


def test_day_timetable_default_omits_p_on_date_key():
    sb = FakeSupabase()
    retrieval.day_timetable(sb)  # on_date not supplied — the "today" case
    name, params = sb.rpc_calls[0]
    assert name == "orion_day_timetable"
    assert "p_on_date" not in params, (
        "p_on_date must be OMITTED (not sent as null) so the RPC's own "
        "DEFAULT (today, IST) actually applies — see this file's docstring"
    )


def test_week_timetable_default_omits_p_on_date_key():
    sb = FakeSupabase()
    retrieval.week_timetable(sb)
    name, params = sb.rpc_calls[0]
    assert name == "orion_week_timetable"
    assert "p_on_date" not in params


def test_day_timetable_explicit_date_is_still_passed_through():
    sb = FakeSupabase()
    retrieval.day_timetable(sb, on_date="2026-09-22")
    _, params = sb.rpc_calls[0]
    assert params["p_on_date"] == "2026-09-22"


def test_week_timetable_explicit_date_is_still_passed_through():
    sb = FakeSupabase()
    retrieval.week_timetable(sb, on_date="2026-09-22")
    _, params = sb.rpc_calls[0]
    assert params["p_on_date"] == "2026-09-22"


def test_day_timetable_with_entries_has_no_answer_when_empty():
    sb = FakeSupabase(data=[])
    result = retrieval.day_timetable(sb)
    assert result.facts == []
    assert result.warnings == ["no active, valid entries for this day"]


def test_day_timetable_returns_facts_when_rpc_has_data():
    entry = {"course_code": "ICS 213", "course_name": "DBMS", "start_time": "09:30:00", "end_time": "10:25:00"}
    sb = FakeSupabase(data=[entry])
    result = retrieval.day_timetable(sb)
    assert len(result.facts) == 1
    assert result.warnings == []
