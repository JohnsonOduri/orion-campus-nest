"""Top-level orchestration: raw query -> QueryPlan -> RetrievalResult ->
GroundedContext. No LLM call in this module (see llm_client.py docstring).

`client` must be a request-scoped Supabase client built from the caller's
own JWT — see backend/query/README or tests/test_query_router.py for the
construction pattern (anon key + `client.postgrest.auth(jwt)`), matching
src/lib/supabase-server.ts exactly. Passing a service-role client here would
defeat RLS and is never correct for answering a user's own question
(CLAUDE.md §13).
"""

from __future__ import annotations

from typing import Any

from . import retrieval
from .context import build_context
from .router import classify
from .types import GroundedContext, RouteType, StructuredIntent


def answer_query(client: Any, query: str) -> GroundedContext:
    plan = classify(query)

    if plan.route == RouteType.UNSUPPORTED:
        from .types import RetrievalResult

        return build_context(RetrievalResult(plan=plan, warnings=["unsupported or ambiguous query"]))

    if plan.route == RouteType.SMALL_TALK:
        from .types import RetrievalResult, StructuredFact

        # Answered directly from the router's own canned reply — never
        # touches Supabase or retrieval.py, so this never reaches the LLM
        # either (ai.py uses this fact as the answer verbatim).
        fact = StructuredFact(claim=plan.topic_text or "", data={}, source="small_talk")
        return build_context(RetrievalResult(plan=plan, facts=[fact]))

    if plan.route == RouteType.STRUCTURED:
        result = _dispatch_structured(client, plan)
    elif plan.route == RouteType.SEMANTIC:
        result = retrieval.semantic_search(client, plan.topic_text or plan.raw_query)
    elif plan.route == RouteType.HYBRID:
        result = retrieval.faculty_topic_and_schedule(client, plan.topic_text or plan.raw_query)
    else:  # pragma: no cover - exhaustive RouteType
        raise ValueError(f"unhandled route: {plan.route}")

    # retrieval functions build their own minimal plan; attach the
    # router's richer one (reasoning, raw_query) for the caller/audit trail
    result.plan = plan
    return build_context(result)


def _dispatch_structured(client: Any, plan) -> Any:
    if plan.structured_intent == StructuredIntent.NEXT_CLASS:
        return retrieval.next_class(client)
    if plan.structured_intent == StructuredIntent.DAY_TIMETABLE:
        return retrieval.day_timetable(client)
    if plan.structured_intent == StructuredIntent.WEEK_TIMETABLE:
        return retrieval.week_timetable(client)
    if plan.structured_intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE:
        return retrieval.day_of_week_timetable(client, plan.topic_text or "")
    if plan.structured_intent == StructuredIntent.CLASS_AT_TIME:
        return retrieval.class_at_time(client, plan.topic_text or "")
    if plan.structured_intent == StructuredIntent.FACULTY_FOR_COURSE:
        return retrieval.faculty_for_course(client, plan.course_code)
    if plan.structured_intent == StructuredIntent.COURSE_INFO:
        return retrieval.course_info(client, plan.course_code)
    if plan.structured_intent == StructuredIntent.FACULTY_LOOKUP:
        return retrieval.faculty_lookup(client, plan.topic_text or "")
    if plan.structured_intent == StructuredIntent.MESS_TODAY:
        return retrieval.mess_today(client, meal=plan.meal)
    if plan.structured_intent == StructuredIntent.MESS_WEEK:
        return retrieval.mess_week(client, meal=plan.meal)
    if plan.structured_intent == StructuredIntent.MESS_ON_DAY:
        return retrieval.mess_on_day(client, plan.topic_text or "", meal=plan.meal)
    from .types import RetrievalResult

    return RetrievalResult(plan=plan, warnings=["structured route with no recognized intent"])
