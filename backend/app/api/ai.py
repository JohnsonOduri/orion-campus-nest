"""Real AI answers on top of the existing query-router/retrieval/context
layer (backend/query/, see docs/query-router.md).

Consolidates onto the Python reference implementation now that a real
FastAPI backend exists to call it from — the TypeScript port under
src/lib/query/ existed only because the frontend couldn't call into Python
at request time before this service existed; that's no longer true.

Identity comes from the same cookie-derived, request-scoped client every
other router uses (deps.py) — no more of the old chat path's fallback to a
hardcoded test-student identity when a bearer token was missing (that
fallback fired for every real user, since sessions are httpOnly cookies
now, never an Authorization header).
"""

from __future__ import annotations

import sys
import urllib.error

from fastapi import APIRouter, Request

# `query` is a sibling top-level package to `app` (both live directly under
# backend/, the working directory `uvicorn main:app` runs from — backend/
# itself is not a package), so this is an absolute import, not a relative
# one up through `app`.
from query import service as query_service
from query.llm_client import GeminiNotConfigured, generate
from query.types import RouteType

from .deps import get_current_client
from ..schemas import AskRequest

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/ask")
def ask(body: AskRequest, request: Request):
    client = get_current_client(request)
    context = query_service.answer_query(client, body.query)

    answer: str | None = None
    generation_available = True

    if context.route == RouteType.SMALL_TALK and context.facts:
        # Router-authored canned reply — never call the LLM for this, by
        # design (small talk costs zero tokens, same principle already
        # applied to "no answer" queries in llm_client.generate()).
        answer = context.facts[0].claim
    else:
        try:
            answer = generate(context)
        except GeminiNotConfigured:
            generation_available = False
        except (urllib.error.URLError, ValueError) as exc:
            # Gemini being unreachable/erroring (bad model name, quota, network)
            # must never break retrieval — the facts/snippets already computed
            # above are still a real, useful answer on their own.
            print(f"[ai.ask] Gemini generation failed, falling back to retrieval only: {exc}", file=sys.stderr)
            generation_available = False

    return {**context.to_dict(), "answer": answer, "generation_available": generation_available}
