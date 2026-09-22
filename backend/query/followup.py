"""Resolve follow-up questions against the conversation so far.

The router classifies a single message, so "Who teaches it?" or "And
dinner?" mean nothing on their own. This rewrites such a message into a
self-contained question using the previous turns — e.g. "Who teaches it?"
after an answer about ICS 214 becomes "Who teaches ICS 214?". Pure function,
no I/O; history is the last few stored messages (oldest first).

It only ever copies an entity (course code, faculty name, meal, day) that
literally appears in the recent conversation — it never infers one.
"""

from __future__ import annotations

import re
from typing import Optional

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
            return f"What's for {new_meal.group(0)} today?"

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
