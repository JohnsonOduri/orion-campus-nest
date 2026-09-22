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

import sys

from fastapi import APIRouter, HTTPException, Request

# `query` is a sibling top-level package to `app` (both live directly under
# backend/, the working directory `uvicorn main:app` runs from — backend/
# itself is not a package), so this is an absolute import, not a relative
# one up through `app`.
from query import campus, compose, followup, llm_client
from query import service as query_service
from query.types import RouteType

from ..core.ratelimit import ASK_LIMITER
from .deps import get_current_client
from ..schemas import AskRequest

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


def _save_message(client, conversation_id: str, role: str, content: str, route: str | None = None) -> None:
    client.table("ai_messages").insert(
        {"conversation_id": conversation_id, "role": role, "content": content, "route": route}
    ).execute()
    client.table("ai_conversations").update({"updated_at": "now()"}).eq("id", conversation_id).execute()


def answer(client, query: str, history: list[dict[str, str]] | None = None) -> dict:
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
    profile = campus.student_context(client)
    context = query_service.answer_query(client, resolved, profile=profile)
    family = campus.cohort_family(profile)

    answer_source = "composer"
    if context.route == RouteType.SEMANTIC and context.snippets:
        text, confidence, passages = compose.compose_documents(context, family)
        if passages and confidence >= 0.34 and llm_client.llm_available():
            try:
                reworded = llm_client.rephrase_passage(resolved, passages[0].text, passages[0].document_title)
                source = text[text.rfind("\n\n*Source:"):] if "*Source:" in text else ""
                lead = compose._cohort_label(passages[0].document_title, family, passages[0].document_type)
                text = f"{reworded}\n\n{lead}:\n\n" + "\n>\n".join(f"> {line}" for line in compose._quote_lines(passages[0].text)) + source
                answer_source = "llm"
            except llm_client.LLMUnavailable as exc:
                print(f"[ai.answer] Gemini skipped ({exc}); using the quoted passage", file=sys.stderr)
    else:
        text = compose.compose(context, family)

    return {
        **context.to_dict(),
        "answer": text,
        "answer_source": answer_source,
        # Kept for older clients: an answer is always produced now.
        "generation_available": True,
        "resolved_query": resolved if resolved != query else None,
    }


@router.post("/ask")
def ask(body: AskRequest, request: Request):
    client = get_current_client(request)
    ASK_LIMITER.check_request(request)

    conversation_id = _get_or_create_conversation(client, body.conversation_id, body.query)
    history = _recent_history(client, conversation_id)

    result = answer(client, body.query, history)

    _save_message(client, conversation_id, "user", body.query)
    _save_message(client, conversation_id, "assistant", result["answer"], result["route"])

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
