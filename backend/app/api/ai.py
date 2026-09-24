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

Conversation persistence (ai_conversations / ai_messages, migration
20260922080000) is added on top of the same request-scoped client — RLS is
the only ownership check, this router never filters by user id itself
(CLAUDE.md §13). History is used to let the LLM resolve "it"/"that" style
follow-ups and keep a consistent tone; it is NOT fed into the router, which
stays a pure function of the current query (backend/query/router.py).
"""

from __future__ import annotations

import hashlib
import logging
import sys

from fastapi import APIRouter, HTTPException, Request

# `query` is a sibling top-level package to `app` (both live directly under
# backend/, the working directory `uvicorn main:app` runs from — backend/
# itself is not a package), so this is an absolute import, not a relative
# one up through `app`.
from query import campus, compose, followup, llm_client
from query import service as query_service
from query.router import classify
from query.types import RouteType

from ..core import config
from ..core.cookies import read_access_token
from ..core.ratelimit import ASK_LIMITER
from .deps import get_current_client
from ..schemas import AskRequest

logger = logging.getLogger("orion.ai")

router = APIRouter(prefix="/ai", tags=["ai"])

# Individual message turns, not user/assistant pairs (a user+assistant
# exchange is 2 messages) — matches the product spec exactly.
HISTORY_WINDOW = 6


def _get_or_create_conversation(client, conversation_id: str | None, first_message: str) -> str:
    if conversation_id:
        existing = (
            client.table("ai_conversations").select("id").eq("id", conversation_id).execute().data
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation_id

    title = first_message.strip()[:80] or "New chat"
    created = client.table("ai_conversations").insert({"title": title}).execute().data
    return created[0]["id"]


def _recent_history(client, conversation_id: str) -> list[dict[str, str]]:
    rows = (
        client.table("ai_messages")
        .select("role,content,created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(HISTORY_WINDOW)
        .execute()
        .data
    )
    rows.reverse()  # oldest first for the prompt
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _save_turn(client, conversation_id: str, question: str, reply: str, route: str | None) -> None:
    """Both messages in one insert, then one conversation touch — four round
    trips became two, which matters because the API and the database are in
    different regions in production."""
    client.table("ai_messages").insert([
        {"conversation_id": conversation_id, "role": "user", "content": question, "route": None},
        {"conversation_id": conversation_id, "role": "assistant", "content": reply, "route": route},
    ]).execute()
    client.table("ai_conversations").update({"updated_at": "now()"}).eq("id", conversation_id).execute()


def answer(client, query: str, history: list[dict[str, str]] | None = None, profile_key: str | None = None) -> dict:
    """The whole answer pipeline for one question — also what
    scripts/run_ai_task.py calls, so tests exercise exactly this path.

    1. resolve a follow-up ("Who teaches it?") against recent turns;
    2. route + retrieve with the caller's own profile (cohort-aware);
    3. write the reply from the retrieved data (compose.py) — works with no
       LLM at all;
    4. only for document answers, and only when Gemini is reachable, let it
       reword the quoted rule; any failure keeps the quote.
    """
    resolved = followup.resolve(query, history or [])
    plan = classify(resolved)
    # Text rewriting can only move a slot that exists in the previous
    # sentence. When the rewritten message still doesn't classify to
    # anything ("what about Friday?" after "What is my next class?"), fall
    # back to carrying the previous turn's QueryPlan and changing only the
    # dimensions this message names (followup.inherit_plan). Deliberately
    # last: a message that classifies on its own is never overridden by
    # stale conversational context.
    if history and _is_unresolved(plan):
        inherited = followup.inherit_plan(query, classify(followup.previous_user_query(history)))
        if inherited is not None:
            plan = inherited

    profile = campus.student_context(client, profile_key)
    context = query_service.answer_query(client, resolved, profile=profile, plan=plan)
    family = campus.cohort_family(profile)

    answer_source = "composer"
    is_cohort_comparison = (context.plan.hints or {}).get("cohort_compare") == "yes"
    if context.route == RouteType.SEMANTIC and context.snippets:
        text, confidence, passages = compose.compose_documents(context, family)
        # A comparison answer quotes two different cohorts' rules side by
        # side (compose._compose_cohort_comparison) — rewording just
        # passages[0] would reword one and silently drop the other.
        if passages and confidence >= 0.34 and llm_client.llm_available() and not is_cohort_comparison:
            try:
                reworded = llm_client.rephrase_passage(resolved, passages[0].text, passages[0].document_title)
                source = text[text.rfind("\n\n*Source:"):] if "*Source:" in text else ""
                lead = compose._cohort_label(passages[0].document_title, passages[0].cohort, family, passages[0].document_type)
                text = f"{reworded}\n\n{lead}:\n\n" + "\n>\n".join(f"> {line}" for line in compose._quote_lines(passages[0].text)) + source
                answer_source = "llm"
            except llm_client.LLMUnavailable as exc:
                print(f"[ai.answer] Gemini skipped ({exc}); using the quoted passage", file=sys.stderr)
    else:
        text = compose.compose(context, family)

    trace = _trace(query, resolved, context, answer_source)
    logger.info("ai.answer %s", trace)
    payload = {
        **context.to_dict(),
        "answer": text,
        "answer_source": answer_source,
        # Kept for older clients: an answer is always produced now.
        "generation_available": True,
        "resolved_query": resolved if resolved != query else None,
    }
    # Developer-only: never sent to normal users (config.DEBUG_TRACE is off
    # in production), so routing internals and document scores can't leak
    # into the UI.
    if config.DEBUG_TRACE:
        payload["trace"] = trace
    return payload


def _is_unresolved(plan) -> bool:
    """The router found nothing specific: either explicitly unsupported, or
    it fell through to "question-shaped, try the documents"."""
    return plan.route == RouteType.UNSUPPORTED or (plan.hints or {}).get("fallback") == "yes"


def _trace(query: str, resolved: str, context, answer_source: str) -> dict:
    """One line per answer naming every stage's decision, so a bad answer
    can be attributed to a layer (router / entity / date / retrieval /
    grounding) instead of guessed at from the reply text."""
    plan = context.plan
    return {
        "query": query,
        "resolved_query": resolved if resolved != query else None,
        "route": plan.route.value,
        "intent": plan.structured_intent.value,
        "entities": {k: v for k, v in
                     (("topic", plan.topic_text), ("course_code", plan.course_code), ("meal", plan.meal))
                     if v},
        "resolved_date": plan.resolved_date,
        "source": "structured" if context.facts else ("documents" if context.snippets else "none"),
        "facts": len(context.facts),
        "snippets": len(context.snippets),
        "warnings": context.warnings,
        "answer_source": answer_source,
        "routing_reason": plan.reasoning,
    }


@router.post("/ask")
def ask(body: AskRequest, request: Request):
    client = get_current_client(request)
    ASK_LIMITER.check_request(request)

    conversation_id = _get_or_create_conversation(client, body.conversation_id, body.query)
    history = _recent_history(client, conversation_id)

    token = read_access_token(request)
    result = answer(client, body.query, history, hashlib.sha256(token.encode()).hexdigest() if token else None)

    _save_turn(client, conversation_id, body.query, result["answer"], result["route"])

    return {**result, "conversation_id": conversation_id}


@router.get("/conversations")
def list_conversations(request: Request):
    client = get_current_client(request)
    rows = (
        client.table("ai_conversations")
        .select("id,title,created_at,updated_at")
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
        .data
    )
    return {"conversations": rows}


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, request: Request):
    client = get_current_client(request)
    existing = (
        client.table("ai_conversations").select("id").eq("id", conversation_id).execute().data
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = (
        client.table("ai_messages")
        .select("id,role,content,route,created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
        .data
    )
    return {"conversation_id": conversation_id, "messages": rows}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request):
    client = get_current_client(request)
    client.table("ai_conversations").delete().eq("id", conversation_id).execute()
    return {"deleted": conversation_id}
