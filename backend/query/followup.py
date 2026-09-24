"""Resolve follow-up questions against the conversation so far.

The router classifies a single message, so "Who teaches it?" or "And
dinner?" mean nothing on their own. Two mechanisms, in order:

1. `resolve()` rewrites the message into a self-contained question using
   the previous turns — "Who teaches it?" after an answer about ICS 214
   becomes "Who teaches ICS 214?". It only ever copies an entity (course
   code, faculty name, meal, day) that literally appears in the recent
   conversation; it never infers one.

2. `inherit_plan()` handles what rewriting cannot: a follow-up whose slot
   isn't present in the previous sentence at all ("what about Friday?"
   after "What is my next class?"). It takes the previous turn's QueryPlan
   and changes only the dimensions the follow-up actually names — the
   conversational state is the plan itself (domain + meal + date), not the
   raw text. Used only as a fallback, when the rewritten message still
   doesn't classify to anything on its own, so a normal self-contained
   question can never be hijacked by stale context.

Pure functions, no I/O; history is the last few stored messages (oldest
first).
"""

from __future__ import annotations

import dataclasses
import re
from typing import Optional

from . import tempo
from .types import QueryPlan, RouteType, StructuredIntent

_COURSE_CODE_RE = re.compile(r"\b(I[A-Z]{2})\s?(\d{3})\b", re.IGNORECASE)
_FACULTY_RE = re.compile(r"\b(?:Dr|Prof|Professor)\.?\s+([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,3})")
_MEAL_RE = re.compile(r"\b(breakfast|lunch|dinner|snacks?)\b", re.IGNORECASE)
_DAY_RE = re.compile(r"\b(today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|this\s+week)\b", re.IGNORECASE)
_ELLIPSIS_RE = re.compile(r"^\s*(?:and|what\s+about|how\s+about|also|and\s+for)\s+(?P<rest>.+?)\s*\??\s*$", re.IGNORECASE)
_THING_PRONOUN_RE = re.compile(r"\b(it|that\s+course|this\s+course|that\s+subject|that\s+class)\b", re.IGNORECASE)
_PERSON_PRONOUN_RE = re.compile(r"\b(he|she|him|her|his|their|them)\b", re.IGNORECASE)
_ANY_PRONOUN_RE = re.compile(r"\b(it|its|that|this|these|those|they|them|he|she|him|her|his|their)\b", re.IGNORECASE)
_COURSE_TOPIC_RE = re.compile(r"\b(teach|teaches|taught|credit|credits|syllabus|prereq\w*|about|exam|semester|course|subject)\b", re.IGNORECASE)


def _last(history: list[dict], role: str) -> str:
    for m in reversed(history):
        if m.get("role") == role and m.get("content"):
            return m["content"]
    return ""


def _course_code(text: str) -> Optional[str]:
    m = _COURSE_CODE_RE.search(text or "")
    return f"{m.group(1).upper()} {m.group(2)}" if m else None


def _faculty(text: str) -> Optional[str]:
    m = _FACULTY_RE.search(text or "")
    if not m:
        return None
    name = re.sub(r"'s$", "", m.group(1)).strip()
    return re.sub(r"\s+(email|office|cabin|research).*$", "", name, flags=re.IGNORECASE).strip() or None


def resolve(query: str, history: Optional[list[dict]]) -> str:
    q = (query or "").strip()
    if not q or not history:
        return q
    last_user = _last(history, "user")
    last_answer = _last(history, "assistant")

    # "And dinner?" / "what about tomorrow?" — swap that slot in the last question.
    m = _ELLIPSIS_RE.match(q)
    if m and last_user and len(q.split()) <= 7:
        rest = m.group("rest")
        for slot in (_MEAL_RE, _DAY_RE):
            new = slot.search(rest)
            if new and slot.search(last_user):
                return slot.sub(new.group(0), last_user, count=1)
        code = _course_code(rest)
        if code and _course_code(last_user):
            return _COURSE_CODE_RE.sub(code, last_user, count=1)
        if new_meal := _MEAL_RE.search(rest):
            # Last resort: the previous question named no meal to swap, so
            # build a fresh one — but keep the day the conversation is
            # already on. Hardcoding "today" here meant "lunch today?" ->
            # "tomorrow?" -> "what about dinner?" answered with *today's*
            # dinner, silently dropping the day the user had just moved to.
            prev_day = _DAY_RE.search(last_user)
            return f"What's for {new_meal.group(0)} {prev_day.group(0) if prev_day else 'today'}?"

    # A bare day/meal word with no leading cue at all ("tomorrow?",
    # "dinner?", "Monday") — still a follow-up, just terser than "and
    # tomorrow?"; same slot-swap as the ellipsis case above.
    bare = q.rstrip("?").strip()
    if bare and len(q.split()) <= 3 and last_user:
        for slot in (_MEAL_RE, _DAY_RE):
            new = slot.fullmatch(bare)
            if new and slot.search(last_user):
                return slot.sub(new.group(0), last_user, count=1)

    if not _ANY_PRONOUN_RE.search(q) or _course_code(q) or _faculty(q):
        return q

    # A course mentioned in the last question or answer ("Who teaches it?").
    code = _course_code(last_user) or _course_code(last_answer)
    if code and _THING_PRONOUN_RE.search(q) and _COURSE_TOPIC_RE.search(q):
        return _THING_PRONOUN_RE.sub(code, q, count=1)

    # A person mentioned in the last question or answer ("What does he research?").
    name = _faculty(last_user) or _faculty(last_answer)
    if name and _PERSON_PRONOUN_RE.search(q):
        def person(m: re.Match[str]) -> str:
            word = m.group(1).lower()
            return f"Dr. {name}'s" if word in {"his", "her", "their"} else f"Dr. {name}"
        return _PERSON_PRONOUN_RE.sub(person, q, count=1)

    # A rule question ("What if I don't meet it?") — carry the previous topic.
    if last_user and len(q.split()) <= 10:
        return f"{q} ({last_user.rstrip('?')})"
    return q


# ---------------------------------------------------------------- plan-level

# The domains where "same question, different day/meal" is a meaningful
# follow-up. A faculty or document question doesn't carry a date slot, so
# inheriting one would invent meaning the user never expressed.
_MESS_INTENTS = {StructuredIntent.MESS_TODAY, StructuredIntent.MESS_ON_DAY, StructuredIntent.MESS_WEEK}
_DAY_INTENTS = {
    StructuredIntent.DAY_TIMETABLE,
    StructuredIntent.DAY_OF_WEEK_TIMETABLE,
    StructuredIntent.WEEK_TIMETABLE,
    StructuredIntent.NEXT_CLASS,
    StructuredIntent.FREE_TIME,
}
# A follow-up is terse by nature. A longer message is a new question, even
# if it happens to contain a day word.
_MAX_FOLLOWUP_WORDS = 6


def inherit_plan(query: str, previous: Optional[QueryPlan]) -> Optional[QueryPlan]:
    """The previous QueryPlan with only the dimensions this follow-up names
    changed — or None if it isn't a follow-up of the kind we can carry.

    "tomorrow?" after a lunch question keeps domain=mess and meal=lunch and
    moves the date; "what about dinner?" keeps the date and moves the meal.
    Nothing is inherited unless the follow-up actually names a new slot
    value, so an unrelated terse message doesn't silently reuse the old
    question's answer.
    """
    if previous is None or previous.route != RouteType.STRUCTURED:
        return None
    q = (query or "").strip()
    if not q or len(q.split()) > _MAX_FOLLOWUP_WORDS:
        return None

    day_ref = tempo.day_reference(q)
    meal_m = _MEAL_RE.search(q)
    meal = None
    if meal_m:
        raw = meal_m.group(1).lower()
        meal = "snacks" if raw.startswith("snack") else raw
    if not day_ref and not meal:
        return None

    intent = previous.structured_intent
    if intent in _MESS_INTENTS or (meal and intent in _MESS_INTENTS | _DAY_INTENTS):
        return _mess_followup(query, previous, day_ref, meal)
    if intent in _DAY_INTENTS and day_ref:
        return _day_followup(query, previous, day_ref)
    return None


def _mess_followup(query: str, previous: QueryPlan, day_ref: Optional[str], meal: Optional[str]) -> QueryPlan:
    day_ref = day_ref or _previous_day_ref(previous)
    target = tempo.resolve_to_date(day_ref)
    intent = StructuredIntent.MESS_TODAY if day_ref in (None, "today") else StructuredIntent.MESS_ON_DAY
    return dataclasses.replace(
        previous,
        raw_query=query,
        structured_intent=intent,
        topic_text=day_ref if intent is StructuredIntent.MESS_ON_DAY else None,
        meal=meal or previous.meal,
        resolved_date=target.isoformat() if target else None,
        reasoning=f"follow-up: kept mess question, "
                  f"meal={meal or previous.meal}, day={day_ref or 'today'} ({target})",
    )


def _day_followup(query: str, previous: QueryPlan, day_ref: str) -> QueryPlan:
    target = tempo.resolve_to_date(day_ref)
    # "What is my next class?" -> "what about Friday?" is asking for that
    # day's timetable; there is no "next class on Friday" concept.
    intent = previous.structured_intent
    if intent in {StructuredIntent.NEXT_CLASS, StructuredIntent.DAY_TIMETABLE, StructuredIntent.WEEK_TIMETABLE}:
        intent = StructuredIntent.DAY_OF_WEEK_TIMETABLE
    return dataclasses.replace(
        previous,
        raw_query=query,
        structured_intent=intent,
        topic_text=day_ref,
        resolved_date=target.isoformat() if target else None,
        reasoning=f"follow-up: kept {intent.value}, moved the day to {day_ref} ({target})",
    )


def _previous_day_ref(previous: QueryPlan) -> Optional[str]:
    if previous.topic_text:
        ref = tempo.day_reference(previous.topic_text)
        if ref:
            return ref
    if previous.resolved_date:
        return None  # the date itself is carried below; no phrase needed
    return None


def previous_user_query(history: Optional[list[dict]]) -> str:
    """The last user turn, itself resolved against the turns before it — so
    a chain ("What's for lunch today?" -> "tomorrow?" -> "and dinner?")
    still has a self-contained question to inherit from at every hop, not
    just the first."""
    turns = history or []
    indexes = [i for i, m in enumerate(turns) if m.get("role") == "user" and m.get("content")]
    if not indexes:
        return ""
    last = indexes[-1]
    return resolve(turns[last]["content"], turns[:last])
