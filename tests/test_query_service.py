"""Pure, offline tests for backend/query/service.py's answer_query dispatch.

Only covers the SMALL_TALK short-circuit here: it's the one path that must
provably never touch Supabase (so it also never risks reaching the LLM via
a slow/failed retrieval) — passing client=None and confirming no exception
is the cheapest possible proof no client method was ever called.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query.router import _THANKS_REPLIES  # noqa: E402
from backend.query.service import answer_query  # noqa: E402
from backend.query.types import RouteType  # noqa: E402


def test_small_talk_never_touches_the_client():
    ctx = answer_query(None, "hi")
    assert ctx.route == RouteType.SMALL_TALK
    assert ctx.has_answer is True
    assert ctx.facts and ctx.facts[0].claim


def test_small_talk_reply_is_the_routers_canned_text():
    """Thanks has multiple reply variants (B2: reply variety) — the fact's
    claim must be one of the router's known variants, not one fixed string."""
    ctx = answer_query(None, "thanks!")
    assert ctx.route == RouteType.SMALL_TALK
    assert ctx.facts[0].claim in _THANKS_REPLIES


def test_unsupported_still_has_no_answer():
    ctx = answer_query(None, "asdkfj qwer")
    assert ctx.route == RouteType.UNSUPPORTED
    assert ctx.has_answer is False
