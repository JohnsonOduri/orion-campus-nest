"""Top-level orchestration: raw query -> QueryPlan -> RetrievalResult ->
GroundedContext. No LLM call in this module.

`client` must be a request-scoped Supabase client built from the caller's
own JWT — never service-role (CLAUDE.md §13). `profile` is the caller's own
student profile (orion_student_context), used for cohort-aware document
search and "about me" answers; it is never taken from the request body.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from datetime import date
from typing import Any, Optional

from . import campus, documents, retrieval
from .context import build_context
from .router import classify
from .types import GroundedContext, QueryPlan, RetrievalResult, RouteType, StructuredFact, StructuredIntent

logger = logging.getLogger("orion.service")

_WHO_TEACHES_RE = re.compile(r"\b(who\s+(teaches|takes|handles)|faculty\s+for|teacher|instructor)\b", re.I)


def answer_query(client: Any, query: str, *, profile: Optional[dict] = None, plan: Optional[QueryPlan] = None) -> GroundedContext:
    plan = plan or classify(query)

    if plan.route == RouteType.UNSUPPORTED:
        return build_context(RetrievalResult(plan=plan, warnings=["unsupported or ambiguous query"]))

    if plan.route == RouteType.SMALL_TALK:
        # Answered from the router's own canned reply — never touches
        # Supabase, retrieval or the LLM.
        fact = StructuredFact(claim=plan.topic_text or "", data={}, source="small_talk")
        return build_context(RetrievalResult(plan=plan, facts=[fact]))

    if plan.route == RouteType.SEMANTIC and plan.hints.get("fallback"):
        plan = _link_entities(client, plan)

    try:
        result = _dispatch(client, plan, profile)
    except Exception as exc:  # noqa: BLE001 - a data-source failure must degrade, not 500
        if not retrieval._is_degradable(exc):
            raise
        logger.warning("retrieval failed for %s: %s: %s", plan.structured_intent.value, exc.__class__.__name__, exc)
        result = RetrievalResult(plan=plan, warnings=["campus data is temporarily unavailable — please try again"])

    # Retrieval functions build their own minimal plan; keep the router's
    # richer one (hints, topic, reasoning) for composing and auditing.
    result.plan = plan
    return build_context(result)


def _plan_date(plan: QueryPlan) -> Optional[date]:
    """The date the router already resolved for this question
    (QueryPlan.resolved_date). Retrieval gets this rather than re-parsing
    "tomorrow" for itself, so the date queried and the date the answer
    names are the same date by construction (backend/query/tempo.py)."""
    if not plan.resolved_date:
        return None
    try:
        return date.fromisoformat(plan.resolved_date)
    except ValueError:
        logger.warning("ignoring unparseable QueryPlan.resolved_date %r", plan.resolved_date)
        return None


def _link_entities(client: Any, plan: QueryPlan) -> QueryPlan:
    """A question with no recognised pattern may still name a course or a
    faculty member ("What is IT Workshop III?", "what does Manu Madhavan
    research?") — answer that from the database instead of searching PDFs."""
    try:
        found = campus.link_entities(client, plan.raw_query)
    except Exception as exc:  # noqa: BLE001
        if not retrieval._is_degradable(exc):
            raise
        return plan
    if found.get("course_code"):
        intent = StructuredIntent.FACULTY_FOR_COURSE if _WHO_TEACHES_RE.search(plan.raw_query) else StructuredIntent.COURSE_INFO
        return dataclasses.replace(plan, route=RouteType.STRUCTURED, structured_intent=intent,
                                   course_code=found["course_code"], hints={},
                                   reasoning=f"named course ({found['course_code']}) -> {intent.value}")
    if found.get("faculty_name"):
        name = re.sub(r"^(dr|prof|mr|ms|mrs)\.?\s+", "", found["faculty_name"], flags=re.I)
        return dataclasses.replace(plan, route=RouteType.STRUCTURED, structured_intent=StructuredIntent.FACULTY_LOOKUP,
                                   topic_text=name, hints={},
                                   reasoning=f"named faculty member ({found['faculty_name']}) -> faculty lookup")
    return plan


def _dispatch(client: Any, plan: QueryPlan, profile: Optional[dict]) -> RetrievalResult:
    intent = plan.structured_intent
    family = campus.cohort_family(profile)

    if plan.route == RouteType.SEMANTIC and plan.hints.get("overview"):
        items = documents.overview(client, plan.hints["overview"], family)
        facts = [StructuredFact(claim=label, data={"label": label, "passage": passage}, source=passage.document_title)
                 for label, passage in items]
        return RetrievalResult(plan=plan, facts=facts, warnings=[] if facts else ["no overview passages found"])

    if plan.route == RouteType.SEMANTIC:
        # A question that names a cohort other than the caller's own
        # (router.detect_cohort_reference — CLAUDE.md §20) must not be
        # silently answered with the caller's own-cohort rule. Plain
        # cross-cohort question -> search only the named cohort. Comparison
        # question ("...different from mine?") -> search BOTH cohorts, so
        # compose.py can show them side by side instead of picking just one.
        cohort_ref = plan.hints.get("cohort_ref")
        cohort_compare = plan.hints.get("cohort_compare") == "yes"
        query_text = plan.topic_text or plan.raw_query
        search_kwargs = {"category": plan.hints.get("category"), "document_type": plan.hints.get("document_type")}

        def search(fam: Optional[str]) -> list:
            return documents.search(client, query_text, fam, **search_kwargs)

        if cohort_ref and cohort_compare and family and cohort_ref != family:
            snippets = search(family) + search(cohort_ref)
        elif cohort_ref and not cohort_compare:
            snippets = search(cohort_ref)
        else:
            snippets = search(family)
        return RetrievalResult(plan=plan, snippets=snippets,
                               warnings=[] if snippets else ["no document passages matched"])

    if intent == StructuredIntent.NEXT_CLASS:
        return retrieval.next_class(client)
    if intent == StructuredIntent.CLASS_AT_TIME:
        return retrieval.class_at_time(client, plan.topic_text or "")
    if intent == StructuredIntent.DAY_TIMETABLE:
        return retrieval.day_timetable(client)
    if intent == StructuredIntent.WEEK_TIMETABLE:
        return retrieval.week_timetable(client)
    if intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE:
        return retrieval.day_of_week_timetable(client, plan.topic_text or "", on_date=_plan_date(plan))
    if intent == StructuredIntent.FREE_TIME:
        return campus.free_time(client, plan.topic_text or "today", on_date=_plan_date(plan))
    if intent == StructuredIntent.CLASSROOM:
        return campus.classroom(client, profile)
    if intent == StructuredIntent.FACULTY_FOR_COURSE:
        return campus.faculty_for_course(client, plan.course_code, plan.hints.get("course_name") or plan.topic_text)
    if intent == StructuredIntent.COURSE_INFO:
        result = campus.course_info(client, plan.course_code or "", family, (profile or {}).get("department"))
        if result.facts:
            teachers = retrieval.faculty_for_course(client, result.facts[0].data["course_code"])
            result.facts[0].data["teachers"] = [f.data["full_name"] for f in teachers.facts]
        return result
    if intent == StructuredIntent.FACULTY_LOOKUP:
        if plan.hints.get("focus") == "meet":
            return campus.faculty_meet(client, plan.topic_text or "")
        return retrieval.faculty_lookup(client, plan.topic_text or "")
    if intent == StructuredIntent.FACULTY_RESEARCH:
        return campus.faculty_research(client, plan.topic_text or plan.raw_query, include_schedule=bool(plan.hints.get("meet")))
    if intent == StructuredIntent.FACULTY_ROLE:
        return campus.faculty_by_role(client, plan.hints.get("role", ""), plan.raw_query)
    if intent == StructuredIntent.MESS_TODAY:
        return retrieval.mess_today(client, meal=plan.meal)
    if intent == StructuredIntent.MESS_WEEK:
        return retrieval.mess_week(client, meal=plan.meal)
    if intent == StructuredIntent.MESS_ON_DAY:
        return retrieval.mess_on_day(client, plan.topic_text or "", meal=plan.meal, on_date=_plan_date(plan))
    if intent == StructuredIntent.ACADEMIC_CALENDAR:
        return campus.academic_calendar(client, plan.topic_text or plan.raw_query)
    if intent == StructuredIntent.EXAM_SCHEDULE:
        return campus.exam_schedule(client, plan.raw_query, plan.course_code)
    if intent == StructuredIntent.ANNOUNCEMENTS:
        return campus.announcements(client)
    if intent == StructuredIntent.HOSTEL_WARDENS:
        return campus.hostel_wardens(client, plan.raw_query)
    if intent == StructuredIntent.MY_COURSES:
        return campus.my_courses(client)
    if intent == StructuredIntent.MY_PROFILE:
        return campus.my_profile(client, profile)
    return RetrievalResult(plan=plan, warnings=["structured route with no recognized intent"])
