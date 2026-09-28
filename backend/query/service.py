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

from . import campus, documents, retrieval, tempo
from .context import build_context
from .router import classify
from .types import GroundedContext, QueryPlan, RetrievalResult, RouteType, StructuredFact, StructuredIntent

logger = logging.getLogger("orion.service")

_PERSON_ASK_RE = re.compile(r"\b(contact|e-?mail|phone|number|office|cabin|sir|mam|ma'?am|madam|research|teach\w*|subjects?)\b", re.I)
_WHO_TEACHES_RE = re.compile(r"\b(who\s+(teaches|takes|handles)|faculty\s+for|teacher|instructor)\b", re.I)


def answer_query(client: Any, query: str, *, profile: Optional[dict] = None, plan: Optional[QueryPlan] = None) -> GroundedContext:
    plan = plan or classify(query)

    # "mirothali chand contact": no rule matched, but it asks for something
    # about a person — try the directory before giving up.
    if (plan.route == RouteType.UNSUPPORTED and plan.structured_intent != StructuredIntent.OUT_OF_SCOPE
            and _PERSON_ASK_RE.search(plan.raw_query)):
        plan = _link_entities(client, plan)
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
    # richer one (hints, topic, reasoning) for composing and auditing — plus
    # any hint dispatch itself added about how it answered.
    added = {k: v for k, v in ((result.plan.hints or {}) if result.plan else {}).items() if k in _DISPATCH_HINTS}
    result.plan = dataclasses.replace(plan, hints={**plan.hints, **added}) if added else plan
    return build_context(result)


# Hints set during dispatch, not by the router ("answered from the other
# cohort's regulations") that the composer needs to see.
_DISPATCH_HINTS = {"cross_cohort"}


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


def _other_cohort(family: Optional[str]) -> Optional[str]:
    return {"21-25": "26-onwards", "26-onwards": "21-25"}.get(family or "")


def _is_rule_question(plan: QueryPlan) -> bool:
    hints = plan.hints or {}
    return hints.get("document_type") == "regulations" or hints.get("semantic") == "documents" or (
        not hints.get("category") and not hints.get("fallback"))


def _answers(query: str, snippets: list) -> bool:
    """Would these snippets answer the question well enough to quote?"""
    from . import compose  # noqa: PLC0415 - compose imports this module's callers

    passages, confidence = documents.best_passages(query, snippets)
    if not passages:
        return False
    verdict = compose.semantic_verdict(passages[0], snippets)
    return verdict != "reject" and (confidence >= compose._QUOTE_CONFIDENCE or verdict == "accept")


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
        name = re.sub(r"^(dr|prof|mr|ms|mrs)\.?\s*", "", found["faculty_name"], flags=re.I)
        subjects = re.search(r"\b(subjects?|courses?|teach(es|ing)?)\b", plan.raw_query, re.I)
        return dataclasses.replace(plan, route=RouteType.STRUCTURED, structured_intent=StructuredIntent.FACULTY_LOOKUP,
                                   topic_text=name, hints={"focus": "subjects"} if subjects else {},
                                   reasoning=f"named faculty member ({found['faculty_name']}) -> faculty lookup")
    return plan


def _faculty_lookup(client: Any, plan: QueryPlan) -> RetrievalResult:
    """Resolve the person against the directory — typos, first names with
    sir/ma'am, possessives, stray punctuation — before the substring match.
    `topic_text` may be a bare name or (sir/ma'am, subjects questions) the
    whole question; the resolver ignores the non-name words either way."""
    people = campus.all_faculty_names(client)
    names = campus.match_faculty_names(plan.topic_text or plan.raw_query, people)
    if not names and plan.topic_text and plan.topic_text != plan.raw_query:
        names = campus.match_faculty_names(plan.raw_query, people)
    result = retrieval.faculty_by_names(client, names) if names else retrieval.faculty_lookup(client, plan.topic_text or "")
    focus = plan.hints.get("focus")
    if len(result.facts) == 1 and result.facts[0].data.get("id"):
        data = result.facts[0].data
        if focus == "subjects":
            data["subjects"] = campus.faculty_subjects(client, data["id"])
            if re.search(r"\bmy\s+(courses?|subjects?|classes)\b", plan.raw_query, re.I):
                data["_my_courses"] = {f.data["course_code"] for f in campus.my_courses(client).facts}
        elif focus == "availability":
            data["teaching_slots"] = campus.teaching_slots(client, data["id"])
    return result


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
            other = _other_cohort(family)
            if other and not _answers(query_text, snippets) and _is_rule_question(plan):
                # The student's own regulations are silent on this (e.g. the
                # 2021-25 regulations have no examination-hall section; the
                # 2026 ones do). Show the other cohort's rule — labelled as
                # not theirs (compose, "cross_cohort") — rather than nothing,
                # and never presented as applying to them (CLAUDE.md §20).
                theirs = documents.search(client, query_text, other, document_type="regulations")
                if _answers(query_text, theirs):
                    snippets = theirs
                    plan = dataclasses.replace(plan, hints={**plan.hints, "cross_cohort": "yes"})
        return RetrievalResult(plan=plan, snippets=snippets,
                               warnings=[] if snippets else ["no document passages matched"])

    if intent == StructuredIntent.NEXT_CLASS:
        result = retrieval.next_class(client)
        if plan.hints.get("with_event"):
            # A bare "what's next?" could mean the next class or the next
            # thing on campus — answer both rather than guessing one.
            upcoming = campus.academic_calendar(client, "upcoming", {"cal_mode": "upcoming"}).facts[:1]
            for f in upcoming:
                f.data["_next_event"] = True
            result.facts.extend(upcoming)
        return result
    if intent == StructuredIntent.CLASS_AT_TIME:
        return retrieval.class_at_time(client, plan.topic_text or "")
    if intent == StructuredIntent.DAY_TIMETABLE:
        return retrieval.day_timetable(client)
    if intent == StructuredIntent.WEEK_TIMETABLE:
        return retrieval.week_timetable(client)
    if intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE:
        return retrieval.day_of_week_timetable(client, plan.topic_text or "", on_date=_plan_date(plan))
    if intent == StructuredIntent.WORKING_DAY:
        return campus.working_day(client, _plan_date(plan) or tempo.today_ist())
    if intent == StructuredIntent.FREE_TIME:
        return campus.free_time(client, plan.topic_text or "today", on_date=_plan_date(plan))
    if intent == StructuredIntent.CLASSROOM:
        result = campus.classroom(client, profile)
        if plan.hints.get("lab"):
            week = retrieval.week_timetable(client)
            result.facts += [StructuredFact(claim=f.claim, data={**f.data, "_lab": True}, source=f.source)
                             for f in week.facts if f.data.get("entry_type") == "lab"]
        return result
    if intent == StructuredIntent.FACULTY_FOR_COURSE:
        return campus.faculty_for_course(client, plan.course_code, plan.hints.get("course_name") or plan.topic_text,
                                         plan.hints.get("entry_type"))
    if intent == StructuredIntent.COURSE_INFO and not plan.course_code and plan.hints.get("course_name"):
        found = campus.resolve_course(client, name=plan.hints["course_name"])
        if not found:
            return RetrievalResult(plan=plan, warnings=[f"couldn't find a course matching {plan.hints['course_name']!r}"])
        plan = dataclasses.replace(plan, course_code=found["course_code"])
    if intent == StructuredIntent.COURSE_INFO:
        result = campus.course_info(client, plan.course_code or "", family, (profile or {}).get("department"))
        if result.facts:
            teachers = retrieval.faculty_for_course(client, result.facts[0].data["course_code"])
            result.facts[0].data["teachers"] = [f.data["full_name"] for f in teachers.facts]
        return result
    if intent == StructuredIntent.FACULTY_LOOKUP:
        if plan.hints.get("focus") == "meet":
            return campus.faculty_meet(client, plan.topic_text or "")
        return _faculty_lookup(client, plan)
    if intent == StructuredIntent.FACULTY_RESEARCH:
        return campus.faculty_research(client, plan.topic_text or plan.raw_query, include_schedule=bool(plan.hints.get("meet")))
    if intent == StructuredIntent.FACULTY_ROLE:
        return campus.faculty_by_role(client, plan.hints.get("role", ""), plan.raw_query)
    if intent in (StructuredIntent.MESS_TODAY, StructuredIntent.MESS_ON_DAY, StructuredIntent.MESS_WEEK) \
            and plan.hints.get("mess_time"):
        return RetrievalResult(plan=plan, facts=[campus.mess_timings(client)])
    if intent == StructuredIntent.MESS_TODAY:
        return retrieval.mess_today(client, meal=plan.meal)
    if intent == StructuredIntent.MESS_WEEK:
        return retrieval.mess_week(client, meal=plan.meal)
    if intent == StructuredIntent.MESS_ON_DAY:
        return retrieval.mess_on_day(client, plan.topic_text or "", meal=plan.meal, on_date=_plan_date(plan))
    if intent == StructuredIntent.ACADEMIC_CALENDAR:
        return campus.academic_calendar(client, plan.topic_text or plan.raw_query, plan.hints)
    if intent == StructuredIntent.FACULTY_DIRECTORY:
        return campus.faculty_directory(client, plan.topic_text or plan.raw_query)
    if intent == StructuredIntent.CONVERSATION:
        # Answered from the conversation in backend/app/api/ai.py; there is
        # nothing to retrieve from campus data.
        return RetrievalResult(plan=plan, warnings=["conversation question"])
    if intent == StructuredIntent.EXAM_SCHEDULE:
        return campus.exam_schedule(client, plan.raw_query, plan.course_code, profile)
    if intent == StructuredIntent.ANNOUNCEMENTS:
        return campus.announcements(client, profile, (plan.hints or {}).get("notice"), plan.course_code)
    if intent == StructuredIntent.HOSTEL_WARDENS:
        return campus.hostel_wardens(client, plan.raw_query)
    if intent == StructuredIntent.MY_COURSES:
        result = campus.my_courses(client)
        if plan.hints.get("credits") and result.facts:
            # courses.credits is mostly empty; read each from the curriculum, in parallel.
            codes = [f.data["course_code"] for f in result.facts]
            futures = {code: documents._POOL.submit(campus.credits_from_curriculum, client, code, family,
                                                    (profile or {}).get("department")) for code in codes}
            for f in result.facts:
                try:
                    f.data["curriculum"] = futures[f.data["course_code"]].result(timeout=8)
                except Exception:  # noqa: BLE001 - a missing credit is shown as unknown, not an error
                    f.data["curriculum"] = None
        return result
    if intent == StructuredIntent.MY_PROFILE:
        return campus.my_profile(client, profile)
    return RetrievalResult(plan=plan, warnings=["structured route with no recognized intent"])
