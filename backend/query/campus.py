"""Structured lookups added for AI-task.md (2026-09-22).

Each function reads live Supabase data through the caller's request-scoped
client (RLS applies — CLAUDE.md §13) and returns a RetrievalResult whose
facts carry the raw rows in `data`; backend/query/compose.py turns them into
the reply. Nothing here calls an LLM or an embedding API.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from . import lexicon, retrieval
from .types import QueryPlan, RetrievalResult, RouteType, StructuredFact, StructuredIntent

_IST = timedelta(hours=5, minutes=30)


def today_ist() -> date:
    return (datetime.now(timezone.utc) + _IST).date()


def _plan(intent: StructuredIntent) -> QueryPlan:
    return QueryPlan(raw_query="", route=RouteType.STRUCTURED, structured_intent=intent)


def _stem(word: str) -> str:
    w = word.lower()
    for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)] + repl
    return w


_FILLER = {
    "when", "what", "is", "are", "the", "do", "does", "did", "a", "an", "of", "for", "my", "i", "will", "be",
    "to", "on", "in", "there", "any", "this", "next", "date", "day", "last", "start", "starts", "begin",
    "begins", "end", "ends", "who", "which", "where", "how", "and", "or", "me", "tell", "about", "please",
}


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _FILLER}


# ------------------------------------------------------------ student context

def student_context(client: Any, cache_key: Optional[str] = None) -> Optional[dict]:
    """The caller's own profile. `cache_key` (a hash of their session token)
    caches it briefly — the API is far from the database in production, so
    this is one round trip saved per question. A missing profile is never
    cached, so finishing registration takes effect immediately."""
    if cache_key:
        hit = _profile_cache.get(cache_key)
        if hit and time.monotonic() - hit[0] < _PROFILE_TTL:
            return hit[1]
    try:
        profile = client.rpc("orion_student_context", {}).execute().data or None
    except Exception:  # noqa: BLE001 - a missing profile must not break answering
        return None
    if cache_key and profile:
        if len(_profile_cache) > 2000:
            _profile_cache.clear()
        _profile_cache[cache_key] = (time.monotonic(), profile)
    return profile


_profile_cache: dict[str, tuple[float, dict]] = {}
_PROFILE_TTL = 60.0


def cohort_family(profile: Optional[dict]) -> Optional[str]:
    """Which UG regulations apply. Uses the stored cohort when present,
    otherwise derives the admission year from the current semester (odd
    semester 2026-27: S1 -> 2026 intake, S3 -> 2025, ...)."""
    if not profile:
        return None
    raw = (profile.get("cohort") or "").strip()
    if raw:
        if re.search(r"(20)?21\D+(20)?25", raw):
            return "21-25"
        if re.search(r"(20)?26", raw):
            return "26-onwards"
    semester = profile.get("semester")
    if isinstance(semester, int) and semester > 0:
        term_year = today_ist().year if today_ist().month >= 7 else today_ist().year - 1
        admission_year = term_year - (semester - 1) // 2
        return "26-onwards" if admission_year >= 2026 else "21-25"
    return None


REGULATION_TITLES = {
    "21-25": "UG Regulations (2021-25 batch)",
    "26-onwards": "UG Regulations (2026 admission onwards)",
}


def my_profile(client: Any, profile: Optional[dict]) -> RetrievalResult:
    if not profile:
        return RetrievalResult(plan=_plan(StructuredIntent.MY_PROFILE),
                               warnings=["no student profile on file for this account"])
    family = cohort_family(profile)
    data = {**profile, "cohort_family": family, "regulations": REGULATION_TITLES.get(family or "")}
    claim = (f"Semester {profile.get('semester')}, {profile.get('programme')}, {profile.get('department')}, "
             f"section {profile.get('section')}")
    return RetrievalResult(plan=_plan(StructuredIntent.MY_PROFILE),
                           facts=[StructuredFact(claim=claim, data=data, source="student_profiles (your profile)")])


# ------------------------------------------------------------ calendar / exams

# Everyday phrasings -> the wording the academic calendar uses.
_CAL_PHRASES: list[tuple[str, str]] = [
    (r"last\s+instructional\s+day|last\s+day\s+of\s+(classes|instruction)|last\s+working\s+day|classes\s+(end|over)|class\s+ends?", "class ends"),
    (r"semester\s+(end|ends|over|finish\w*)|end\s+of\s+(the\s+)?semester", "semester ends"),
    (r"even\s+sem\w*\s+(start|starts|begin|begins|classes|reopen\w*)|next\s+semester\s+(start|begin)\w*", "even semester classes begin"),
    (r"\bend[\s-]?sem\w*", "end semester"),
    (r"\bmid[\s-]?sem\w*|\bmidterms?", "mid semester"),
    (r"\bexams?\b|\bexaminations?\b", "examination"),
    (r"results?\s+(be\s+)?(published|declared|out|announced)|result\s+publication|when\b.*\bresults?\b", "result publication"),
    (r"course\s+drop|drop\s+(a\s+)?courses?", "course drop"),
    (r"\bfees?\b", "fee payment"),
    (r"\bsports\b", "sports meet"),
    (r"class\s+committee|committee\s+meeting", "class committee meeting"),
    (r"\bregister\b|\bregistration\b", "registration"),
    (r"\brepeat\s+examination|supplementary", "repeat examination"),
    (r"\bproject\s+review|\bbtp\b", "project review"),
]
_CAL_TOKEN_MAP = {"exam": "examination", "exams": "examination", "sem": "semester", "classes": "class",
                  "starts": "start", "begin": "start", "begins": "start", "commence": "start", "ends": "end",
                  "results": "result", "published": "publication", "day": "", "date": "", "last": "",
                  "when": "", "is": "", "the": "", "do": "", "does": "", "will": "", "be": "", "what": "",
                  "for": "", "of": "", "a": "", "my": "", "are": "", "on": "", "there": "", "any": "", "next": "",
                  "and": "", "online": "", "i": "", "to": "", "in": "", "this": ""}


def _cal_tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        w = _CAL_TOKEN_MAP.get(w, w)
        if w:
            out.add(_stem(w))
    return out


def calendar_events(client: Any) -> list[dict]:
    return (
        client.table("academic_calendar")
        .select("id,event_name,event_date,event_type,applies_to_semester,valid_until,status,source_id")
        .eq("status", "active")
        .order("event_date")
        .execute()
        .data
        or []
    )


def _base_name(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"\s*&\s*semester\s+ends?$", "", n)
    n = re.sub(r"\s+(starts?|begins?|ends?)\s*$", "", n)
    return re.sub(r"\bexam\b", "examination", n)


def _event_score(text: str, e: dict) -> float:
    """How well a phrase ("exams start", "classes end") names event `e`."""
    q = text.lower()
    for pattern, replacement in _CAL_PHRASES:
        q = re.sub(pattern, replacement, q)
    q_tokens = _cal_tokens(q)
    name = e["event_name"]
    score = float(len(q_tokens & _cal_tokens(name)))
    if "start" in q_tokens and re.search(r"\b(starts?|begins?)\b", name, re.I):
        score += 0.6
    if ("end" in q_tokens or "class ends" in q) and re.search(r"\bends?\b", name, re.I):
        score += 0.6
    return score


def _best_event(text: str, events: list[dict], near: Optional[date] = None) -> Optional[dict]:
    """The event a phrase names. Ties go to the event closest to `near`
    (the other event in a "days between" question), so "exams" next to
    "classes end" means the end semester exams, not the mid semester ones."""
    scored = [(_event_score(text, e), e) for e in events]
    best = max((sc for sc, _ in scored), default=0.0)
    if best < 1.0:
        return None
    tied = [e for sc, e in scored if sc == best]
    if near is not None:
        tied.sort(key=lambda e: abs((date.fromisoformat(e["event_date"]) - near).days))
    else:
        today = today_ist()
        tied.sort(key=lambda e: (date.fromisoformat(e["event_date"]) < today, e["event_date"]))
    return tied[0]


_GAP_SPLIT_RE = re.compile(r"\b(?:between|and|before|after|until|till|from|to|do|does|will)\b", re.I)


def _calendar_mode(client: Any, query: str, hints: dict[str, str]) -> Optional[RetrievalResult]:
    """Answers that need reasoning over the calendar rather than one lookup
    (router._calendar_plan sets the mode)."""
    mode = hints.get("cal_mode")
    if not mode:
        return None
    events = calendar_events(client)
    today = today_ist()
    src = lambda e: f"academic_calendar ({e.get('source_id') or 'live'})"  # noqa: E731

    def facts_for(picked: list[dict], **extra: Any) -> list[StructuredFact]:
        return [StructuredFact(claim=f"{e['event_name']}: {e['event_date']}", data={**e, "_mode": mode, **extra},
                               source=src(e)) for e in picked]

    result = lambda facts, warnings=None: RetrievalResult(  # noqa: E731
        plan=_plan(StructuredIntent.ACADEMIC_CALENDAR), facts=facts, warnings=warnings or ([] if facts else ["no matching academic calendar events"]))

    if mode == "on_date":
        target = date.fromisoformat(hints["date"])
        on = [e for e in events if e["event_date"] == target.isoformat()]
        if on:
            return result(facts_for(on, _target=target.isoformat()))
        before = [e for e in events if e["event_date"] < target.isoformat()][-1:]
        after = [e for e in events if e["event_date"] > target.isoformat()][:1]
        return result(facts_for(before + after, _target=target.isoformat(), _nearest=True))

    if mode == "gap":
        # Split the question into the two event phrases and match each one.
        body = re.sub(r"^.*?\bhow\s+many\s+days\b|^.*?\b(gap|difference)\b", " ", query, flags=re.I)
        parts = [p.strip(" ?.,") for p in _GAP_SPLIT_RE.split(body) if p and len(p.strip(" ?.,")) > 2]
        # Filler ("are there") names no event; the first two phrases that do
        # are the two events.
        named = [p for p in parts if _best_event(p, events)]
        first = _best_event(named[0], events) if named else None
        second = None
        for p in named[1:]:
            cand = _best_event(p, [e for e in events if e is not first],
                               near=date.fromisoformat(first["event_date"]) if first else None)
            if cand:
                second = cand
                break
        parts = named or parts
        if first and not second:
            # "How many days until the end sem exams?" — counted from today.
            return result(facts_for([first], _gap_from_today=True))
        if first and second:
            # Re-pick the first with the second as the anchor, so ties resolve
            # consistently in both directions.
            first = _best_event(parts[0], [e for e in events if e is not second],
                                near=date.fromisoformat(second["event_date"])) or first
            a, b = sorted([first, second], key=lambda e: e["event_date"])
            days = (date.fromisoformat(b["event_date"]) - date.fromisoformat(a["event_date"])).days
            return result(facts_for([a, b], _gap_days=days))
        return result([])

    if mode == "after_event":
        anchor = _best_event(hints.get("anchor", ""), events)
        if not anchor:
            return result([], [f"no calendar event matching {hints.get('anchor', '')!r}"])
        base = _base_name(anchor["event_name"])
        last_day = max(e["event_date"] for e in events if _base_name(e["event_name"]) == base or e is anchor)
        nxt = [e for e in events if e["event_date"] > last_day][:1]
        return result(facts_for(nxt, _anchor=anchor["event_name"], _anchor_date=last_day))

    if mode == "exams":
        exams = [e for e in events if e["event_type"] == "exam" or re.search(r"\bexam", e["event_name"], re.I)]
        return result(facts_for(exams))

    if mode == "upcoming":
        return result(facts_for([e for e in events if date.fromisoformat(e["event_date"]) >= today][:8]))

    if mode == "past":
        past = [e for e in events if date.fromisoformat(e["event_date"]) < today]
        return result(facts_for(list(reversed(past[-8:]))))

    if mode == "today":
        on = [e for e in events if e["event_date"] == today.isoformat()]
        nxt = [e for e in events if date.fromisoformat(e["event_date"]) > today][:1]
        facts = facts_for(on, _today=True) + facts_for(nxt, _next=True)
        try:
            classes = retrieval.day_timetable(client).facts
        except Exception:  # noqa: BLE001 - the calendar answer stands on its own
            classes = []
        for f in classes:
            facts.append(StructuredFact(claim=f.claim, data={**f.data, "_mode": mode, "_class": True}, source=f.source))
        return result(facts, [])
    return None


def academic_calendar(client: Any, query: str, hints: Optional[dict[str, str]] = None) -> RetrievalResult:
    """Best-matching calendar event (+ its Starts/Ends partner), or the next
    events for "what's coming up" / "upcoming deadlines" questions. With a
    `cal_mode` hint: events on a date, the gap between two events, the event
    after another, all exams, upcoming/past events, today's overview."""
    moded = _calendar_mode(client, query, hints or {})
    if moded is not None:
        return moded
    events = calendar_events(client)
    today = today_ist()
    q = query.lower()
    for pattern, replacement in _CAL_PHRASES:
        q = re.sub(pattern, replacement, q)
    q_tokens = _cal_tokens(q)
    asks_end = "end" in q_tokens and "semester ends" in q or bool(re.search(r"\b(end|ends|over|finish)\s*\??$", query.strip(), re.I))
    asks_start = "start" in q_tokens
    upcoming_q = bool(re.search(r"\b(upcoming|coming\s+up|deadlines|events?|this\s+month|calendar|important\s+dates)\b", query, re.I))
    wants_deadline = bool(re.search(r"\bdeadlines?\b", query, re.I))
    wants_holiday = bool(re.search(r"\bholiday|vacation", query, re.I))

    scored: list[tuple[float, dict]] = []
    for e in events:
        name = e["event_name"]
        e_tokens = _cal_tokens(name)
        score = float(len(q_tokens & e_tokens))
        if asks_end and re.search(r"\bends?\b", name, re.I) and not re.search(r"^end\b", name.strip(), re.I) or (
                asks_end and re.search(r"semester ends", name, re.I)):
            score += 1
        if asks_start and re.search(r"\b(starts?|begins?)\b", name, re.I):
            score += 0.5
        if date.fromisoformat(e["event_date"]) >= today:
            score += 0.4
        scored.append((score, e))
    scored.sort(key=lambda t: (-t[0], t[1]["event_date"]))
    best_score = scored[0][0] if scored else 0

    if (upcoming_q and best_score < 2.4) or best_score < 1.4 or wants_holiday:
        picked = [e for e in events if date.fromisoformat(e["event_date"]) >= today]
        if wants_deadline:
            picked = [e for e in picked if e["event_type"] == "deadline"] or picked
        picked = picked[:6]
        mode = "upcoming"
    else:
        best = scored[0][1]
        picked = [best]
        base = _base_name(best["event_name"])
        # The same event on more than one day (e.g. a meeting on the 23rd and 24th).
        picked += [e for e in events if e is not best and e["event_name"] == best["event_name"]
                   and date.fromisoformat(e["event_date"]) >= today]
        # Its Starts <-> Ends partner, matched on the full base name only.
        partner = next((e for e in events if e is not best and _base_name(e["event_name"]) == base
                        and e["event_name"] != best["event_name"]), None)
        if partner:
            picked.append(partner)
        mode = "match"
    picked.sort(key=lambda e: e["event_date"])
    facts = [
        StructuredFact(claim=f"{e['event_name']}: {e['event_date']}",
                       data={**e, "_mode": mode, "_holiday_query": wants_holiday, "_asks_end": asks_end},
                       source=f"academic_calendar ({e.get('source_id') or 'live'})")
        for e in picked
    ]
    warnings = [] if facts else ["no matching academic calendar events"]
    if wants_holiday and not any(e["event_type"] in {"holiday", "vacation"} for e in events):
        warnings.append("the academic calendar on file lists no holidays")
    return RetrievalResult(plan=_plan(StructuredIntent.ACADEMIC_CALENDAR), facts=facts, warnings=warnings)


def exam_schedule(client: Any, query: str, course_code: Optional[str]) -> RetrievalResult:
    course = resolve_course(client, code=course_code) if course_code else None
    rows: list[dict] = []
    if course:
        rows = (
            client.table("exams")
            .select("exam_type,exam_date,start_time,end_time,semester,batch,status")
            .eq("course_id", course["id"])
            .eq("status", "active")
            .order("exam_date")
            .execute()
            .data
            or []
        )
    facts = [
        StructuredFact(claim=f"{course['course_code']} {r['exam_type']} on {r['exam_date']}",
                       data={**r, "course": course}, source="exams (live)")
        for r in rows
    ]
    # The per-course exam timetable isn't published in ORION yet; the exam
    # WINDOW from the academic calendar is the honest next-best answer.
    window = [e for e in calendar_events(client) if e["event_type"] == "exam"]
    for e in window:
        facts.append(StructuredFact(claim=f"{e['event_name']}: {e['event_date']}",
                                    data={**e, "_window": True, "course": course},
                                    source=f"academic_calendar ({e.get('source_id') or 'live'})"))
    warnings = [] if rows else ["no per-course exam schedule has been published in ORION"]
    return RetrievalResult(plan=_plan(StructuredIntent.EXAM_SCHEDULE), facts=facts, warnings=warnings)


# ------------------------------------------------------------ working day

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def working_day(client: Any, on: date) -> RetrievalResult:
    """Is <date> a working day / do I have class on <date>: the timetable
    for that date + the calendar's events that day + where the date falls
    in the term (instructional days, exams)."""
    day = retrieval.day_of_week_timetable(client, _WEEKDAY_NAMES[on.isoweekday() - 1], on_date=on)
    events = calendar_events(client)
    todays = [e for e in events if e["event_date"] == on.isoformat()]
    def first(pattern: str) -> Optional[str]:
        return next((e["event_date"] for e in events if re.search(pattern, e["event_name"], re.I)), None)
    meta = {"_working_day": True, "date": on.isoformat(),
            "class_begins": first(r"class\s+begins|1st\s+instructional"),
            "class_ends": first(r"^class\s+ends"),
            "exams_start": first(r"end\s+semester\s+examination\s+starts"),
            "exams_end": first(r"end\s+semester\s+exam\s+ends"),
            "holidays_listed": any(e["event_type"] == "holiday" or "holiday" in e["event_name"].lower() for e in events),
            "events": todays}
    facts = [StructuredFact(claim=f"working day check {on}", data=meta, source="academic_calendar (live)")]
    facts += [f for f in day.facts if f.data.get("start_time")]
    return RetrievalResult(plan=_plan(StructuredIntent.WORKING_DAY), facts=facts)


# ------------------------------------------------------------ mess timings

def mess_timings(client: Any) -> StructuredFact:
    """Serving times per meal (mess_meal_timings, from the published menu)."""
    rows = (client.table("mess_meal_timings").select("meal,start_time,end_time,source_id")
            .eq("status", "active").execute().data or [])
    timings: dict[str, tuple[int, int]] = {}
    source = None
    for r in rows:
        s, e = timeq_minutes(r["start_time"]), timeq_minutes(r["end_time"])
        if s is not None and e is not None:
            timings[r["meal"]] = (s, e)
            source = r.get("source_id")
    label = "published menu" if not source else re.sub(r"[_ ]+", " ", source.replace(".pdf", "")).strip()
    return StructuredFact(claim="mess timings", data={"_timings": True, "timings": timings, "source": label},
                          source="mess_meal_timings")


def timeq_minutes(value: Any) -> Optional[int]:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(value or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


# ------------------------------------------------------------ announcements

ANNOUNCEMENT_FIELDS = ("id,title,content,category,department,batch,section,semester,target_role,created_at,"
                       "published_at,valid_until,event_date,event_time,auto_published")


def announcement_visible_to(row: dict, profile: Optional[dict]) -> bool:
    """Campus-wide notices reach everyone; a class notice (a CR's quiz/exam
    update, scoped by semester/department/section) reaches that class only.
    Admins see all. Not a secrecy boundary — just who it's relevant to."""
    if (profile or {}).get("role") == "ADMIN":
        return True
    p = profile or {}
    for key in ("semester", "department", "batch", "section"):
        want = row.get(key)
        if want is not None and str(want) != str(p.get(key)):
            return False
    return True


def current_announcements(client: Any, profile: Optional[dict], limit: int = 50) -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = (
        client.table("announcements")
        .select(ANNOUNCEMENT_FIELDS)
        .eq("status", "active")
        .or_(f"valid_until.is.null,valid_until.gte.{now_iso}")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    return [r for r in rows if announcement_visible_to(r, profile)]


_NOTICE_WORDS = {"QUIZ": r"quiz|class\s+test", "ASSIGNMENT": r"assignment|homework|record|submission",
                 "CLASS_UPDATE": r"cancel|resched|postpon|extra\s+class|make[\s-]?up|shift"}


def announcements(client: Any, profile: Optional[dict] = None, notice: Optional[str] = None,
                  course_code: Optional[str] = None) -> RetrievalResult:
    """Current announcements the caller should see. With `notice` (QUIZ,
    ASSIGNMENT, CLASS_UPDATE, NOTICE) only the class notices of that kind,
    soonest event first — "when is the quiz?"."""
    rows = current_announcements(client, profile)
    if notice:
        words = _NOTICE_WORDS.get(notice)
        rows = [r for r in rows if (r.get("category") == notice) or (
            words and re.search(words, f"{r.get('title')} {r.get('content')}", re.I)) or (
            notice == "NOTICE" and r.get("section") is not None)]
        if course_code:
            code = re.sub(r"\s+", "", course_code.upper())
            rows = [r for r in rows if code in re.sub(r"\s+", "", f"{r.get('title')} {r.get('content')}".upper())] or rows
        today = datetime.now(timezone.utc).date().isoformat()
        rows.sort(key=lambda r: (r.get("event_date") is None, r.get("event_date") or "", r.get("event_time") or ""))
        rows = [r for r in rows if not r.get("event_date") or r["event_date"] >= today] or rows
    facts = [StructuredFact(claim=r["title"], data={**r, "_notice": notice}, source="announcements") for r in rows[:5]]
    plan = QueryPlan(raw_query="", route=RouteType.STRUCTURED, structured_intent=StructuredIntent.ANNOUNCEMENTS,
                     hints={"notice": notice} if notice else {})
    return RetrievalResult(plan=plan, facts=facts, warnings=[] if facts else ["no current announcements"])


# ------------------------------------------------------------ hostel wardens

_ROLE_ORDER = {"hostel_warden": 0, "assistant_warden": 1, "standby_warden": 2}


def hostel_wardens(client: Any, query: str) -> RetrievalResult:
    rows = (
        client.table("hostel_wardens")
        .select("hall_code,hall_name,role,full_name,phone,email,source_id")
        .eq("status", "active")
        .execute()
        .data
        or []
    )
    q = query.lower()
    halls = {r["hall_name"] for r in rows if r.get("hall_name")}
    matched = {h for h in halls if any(len(w) > 3 and w in q for w in re.findall(r"[a-z]+", h.lower())
                                       if w not in {"hostel", "boys", "girls", "apartment", "residency", "building"})}
    general_roles = [r for r in rows if not r.get("hall_name")]
    if re.search(r"\bchief\s+warden\b", q):
        picked = [r for r in general_roles if r["role"] == "chief_warden"]
        mode = "general"
    elif re.search(r"\b(hostel\s+manager|security\s+officer)\b", q):
        key = "hostel_manager" if "manager" in q else "security_officer"
        picked = [r for r in general_roles if r["role"] == key]
        mode = "general"
    elif matched:
        picked = sorted((r for r in rows if r.get("hall_name") in matched),
                        key=lambda r: (r["hall_name"], _ROLE_ORDER.get(r["role"], 9)))
        mode = "hall"
    else:
        # Which hostel isn't known: the hall wardens + the institute-wide roles.
        picked = sorted((r for r in rows if r["role"] == "hostel_warden"), key=lambda r: r["hall_code"] or "")
        picked += sorted(general_roles, key=lambda r: r["role"])
        mode = "overview"
    facts = [StructuredFact(claim=f"{r['full_name']} — {r['role']} {r.get('hall_name') or ''}".strip(),
                            data={**r, "_mode": mode}, source=f"hostel_wardens ({r.get('source_id') or 'live'})")
             for r in picked]
    return RetrievalResult(plan=_plan(StructuredIntent.HOSTEL_WARDENS), facts=facts,
                           warnings=[] if facts else ["no warden records found"])


# ------------------------------------------------------------ faculty by role

_ROLE_DESIGNATION = {
    "hod": ["HOD"],
    "registrar": ["Registrar"],
    "director": ["Director"],
    "dean": ["Dean"],
    "medical": ["Medical Officer"],
    "nurse": ["Nurse"],
    "psychologist": ["Psychologist"],
    "physical_education": ["Physical Education"],
    "cvo": ["CVO"],
    "nodal": ["Nodal"],
    "placement": ["Career"],
    "librarian": ["Librarian", "Library"],
    "iqac": ["IQAC"],
}
_DEPT_ALIASES = [
    (r"\b(eee|electrical)\b", ["Electronics"]),
    (r"\b(cse|computer\s+science)\b", ["Computer Science"]),
    (r"\b(ece|electronics|communication)\b", ["Electronics"]),
    (r"\b(cyber|security|csy)\b", ["Cyber"]),
    (r"\b(humanities|computational\s+science|maths?|mathematics)\b", ["Computational Science", "Humanities"]),
    (r"\bacademic", ["Academic"]),
    (r"\bhostel|student\s+events\b", ["Hostel"]),
    (r"\bplacements?\b|\bt\s?&\s?p\b|\btnp\b|\bcareer\b", ["Career"]),
    (r"\bstudents?\s+welfare\b", ["Students Welfare", "Career"]),
    (r"\balumni|international\b", ["Alumni"]),
    (r"\bindustr|funding\b", ["Industrial"]),
    (r"\bcontinuing\s+education|training|consultancy\b", ["Continuing Education"]),
]


def faculty_by_role(client: Any, role: str, query: str) -> RetrievalResult:
    rows = (
        client.table("faculty")
        .select("full_name,initials,designation,email,phone,office_location,status")
        .eq("status", "active")
        .not_.is_("designation", "null")
        .execute()
        .data
        or []
    )
    keys = _ROLE_DESIGNATION.get(role, [role])
    picked = [r for r in rows if any(k.lower() in (r["designation"] or "").lower() for k in keys)
              and "former" not in (r["designation"] or "").lower()]
    if role == "director":
        picked = [r for r in picked if "nit" not in r["designation"].lower()] or picked
    q = query.lower()
    note = None
    for pattern, frags in _DEPT_ALIASES:
        if re.search(pattern, q):
            narrowed = [r for r in picked if any(f.lower() in r["designation"].lower() for f in frags)]
            if narrowed:
                picked = narrowed
                if re.search(r"\bplacements?\b|\bt\s?&\s?p\b|\btnp\b|\btraining\b", q):
                    note = ("The directory has no separate placement coordinator; career development and "
                            "placements come under this Associate Dean.")
                if re.search(r"\b(eee|electrical)\b", q):
                    note = ("IIIT Kottayam doesn't have a separate Electrical Engineering department — the "
                            "closest is Electronics & Communication Engineering (ECE).")
                break
    if role == "placement" and not note:
        note = ("The directory has no separate training/placement officer; career development and placements come "
                "under this Associate Dean.")
    facts = [StructuredFact(claim=f"{r['full_name']} — {r['designation']}", data={**r, "_note": note},
                            source="faculty directory (live)")
             for r in picked[:8]]
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_ROLE), facts=facts,
                           warnings=[] if facts else [f"no one with a '{role}' designation found in the faculty directory"])


# ------------------------------------------------------------ faculty directory

# (question pattern, label, test on (designation, categories)). The first
# matching filter narrows the directory; none = the whole directory.
_DIRECTORY_FILTERS: list[tuple[str, str, Any]] = [
    (r"\bassistant\s+professors?\b", "Assistant Professor", lambda d, c: "assistant professor" in d),
    (r"\bassociate\s+professors?\b", "Associate Professor", lambda d, c: "associate professor" in d),
    (r"\blab\s+(faculty|teaching|staff|instructors?)|\blab\s+faculty", "Lab Faculty", lambda d, c: "lab faculty" in d),
    (r"\badjuncts?\b", "Adjunct", lambda d, c: "adjunct" in d),
    (r"\bvisiting\b", "Visiting", lambda d, c: "visiting" in d),
    (r"\bacademic\s+administration\b", "academic administration",
     lambda d, c: "administrative" in c and ("academic" in d or "registrar" in d)),
    (r"\badministrat\w*|\badmin\b|\bacademic\s+and\s+(an\s+)?administrative\b", "administrative",
     lambda d, c: "administrative" in c and "faculty" in c),
    (r"\b(support\s+staff|professional\s+support|medical\s+staff)\b", "professional support",
     lambda d, c: "professional_support" in c),
]


def _designation_group(d: str) -> str:
    low = d.lower()
    if low.startswith("hod"):
        return "Heads of Department"
    if "associate dean" in low:
        return "Associate Deans"
    if "adjunct" in low:
        return "Adjunct Faculty"
    if "assistant professor" in low:
        return "Assistant Professors"
    if "lab faculty" in low:
        return "Lab Faculty"
    return re.sub(r"\s*\(.*$", "", d).strip() or "Other"


def faculty_directory(client: Any, query: str) -> RetrievalResult:
    """The faculty as a group: counts by designation, or everyone with the
    designation/category the question names ("assistant professors",
    "adjunct faculty", "administrative positions")."""
    rows = (
        client.table("faculty")
        .select("full_name,initials,designation,category,email,office_location,status")
        .eq("status", "active")
        .execute()
        .data
        or []
    )
    rows = [r for r in rows if r.get("designation") and "former" not in r["designation"].lower()
            and "nit calicut" not in r["designation"].lower()]
    q = query.lower()
    label, picked = None, rows
    for pattern, name, test in _DIRECTORY_FILTERS:
        if re.search(pattern, q):
            label = name
            picked = [r for r in rows if test((r["designation"] or "").lower(), r.get("category") or [])]
            break
    teaching = [r for r in rows if "faculty" in (r.get("category") or [])]
    groups: dict[str, int] = {}
    for r in (picked if label else teaching):
        g = _designation_group(r["designation"])
        groups[g] = groups.get(g, 0) + 1
    picked.sort(key=lambda r: (_designation_group(r["designation"]), r["full_name"].lower()))
    dept_asked = bool(re.search(r"\b(cse|ece|computer\s+science|electronics|cyber|humanities|department|dept)\b", q))
    summary = {"_filter": label, "_groups": groups, "_total": len(picked if label else teaching),
               "_yes_no": bool(re.match(r"^\s*(are|is|do|does)\b", q)), "_dept_asked": dept_asked}
    facts = [StructuredFact(claim=f"{r['full_name']} — {r['designation']}", data={**r, **summary},
                            source="faculty directory (live)") for r in picked]
    if not facts:
        facts = [StructuredFact(claim=f"no one designated {label}", data={"full_name": None, **summary},
                                source="faculty directory (live)")]
        # The honest near miss for "associate professor": the associate deans.
        if label == "Associate Professor":
            for r in rows:
                if "associate dean" in r["designation"].lower():
                    facts.append(StructuredFact(claim=f"{r['full_name']} — {r['designation']}",
                                                data={**r, **summary, "_near_miss": True},
                                                source="faculty directory (live)"))
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_DIRECTORY), facts=facts)


# ------------------------------------------------------------ faculty by research topic

_TOPIC_ALIASES = {
    "nlp": "natural language processing",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "cv": "computer vision",
    "iot": "internet of things",
    "vlsi": "vlsi",
    "cyber security": "security",
    "cybersecurity": "security",
    "blockchain": "block chain",
    "gnn": "graph neural networks",
    "llm": "large language models",
    "wsn": "wireless sensor networks",
}


def _topic_variants(topic: str) -> list[list[str]]:
    """Token sets to try, best first: the whole topic, then each part of a
    compound one.

    A question like "who works on cryptography and network security?" is
    asking about either area, but `research_interests` stores them as
    separate semicolon-separated phrases ("Cryptography; Network
    Security"), so requiring one phrase to cover every token of the whole
    compound matched nobody — confirmed live against the real directory."""
    raw = topic.strip()
    candidates = [raw]
    parts = [p.strip() for p in re.split(r"\s*(?:,|&|\band\b|\bor\b)\s*", raw) if p.strip()]
    if len(parts) > 1:
        candidates.extend(parts)
    variants: list[list[str]] = []
    for candidate in candidates:
        expanded = _TOPIC_ALIASES.get(candidate.lower(), candidate)
        tokens = [t for t in _tokens(expanded) if len(t) > 1]
        if tokens and tokens not in variants:
            variants.append(tokens)
    return variants


def faculty_research(client: Any, topic: str, include_schedule: bool, top_k: int = 5) -> RetrievalResult:
    """Lexical match on research_interests: every phrase is compared to the
    topic (all topic words present = strong match), so "NLP" and "natural
    language processing" both work without embeddings. A compound topic is
    also tried part by part (_topic_variants)."""
    variants = _topic_variants(topic)
    phrase_tokens = variants[0] if variants else []
    if not phrase_tokens:
        return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_RESEARCH), warnings=[f"no topic found in {topic!r}"])
    rows = (
        client.table("faculty")
        .select("id,full_name,initials,designation,email,office_location,office_hours,research_interests,status")
        .eq("status", "active")
        .not_.is_("research_interests", "null")
        .execute()
        .data
        or []
    )
    scored: list[tuple[float, dict, list[str]]] = []
    for f in rows:
        interests = [p.strip() for p in re.split(r"[;,\n]", f.get("research_interests") or "") if p.strip()]
        best, hits, first_pos = 0.0, [], len(interests)
        for variant in variants:
            threshold = 1.0 if len(variant) <= 2 else 0.66
            for pos, p in enumerate(interests):
                pt = _tokens(p)
                covered = sum(1 for t in variant if t in pt or any(x.startswith(t) for x in pt if len(t) >= 4))
                if not covered:
                    continue
                s = covered / len(variant)
                if s >= 0.99 and p not in hits:
                    hits.append(p)
                    first_pos = min(first_pos, pos)
                if s >= threshold:
                    best = max(best, s)
        if best > 0:
            # A topic listed first is more likely their main area than one listed tenth.
            scored.append((best + 0.3 / (1 + first_pos) + 0.05 * len(hits), f, hits))
    scored.sort(key=lambda t: (-t[0], t[1]["full_name"]))

    facts: list[StructuredFact] = []
    total_matches = len(scored)
    for score, f, hits in scored[:top_k]:
        data = {"faculty": {k: f.get(k) for k in ("full_name", "initials", "designation", "email", "office_location", "office_hours", "research_interests")},
                "matched_interests": hits, "score": round(score, 2), "total_matches": total_matches}
        if include_schedule:
            data["teaching_slots"] = teaching_slots(client, f["id"])
        facts.append(StructuredFact(claim=f"{f['full_name']} — research interests include {', '.join(hits) or topic}",
                                    data=data, source="faculty.research_interests (live)"))
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_RESEARCH), facts=facts,
                           warnings=[] if facts else [f"no faculty list {topic!r} among their research interests"])


def teaching_slots(client: Any, faculty_id: Any) -> list[dict]:
    rows = (
        client.table("timetable_entry_faculty")
        .select("timetable_entries(day_of_week,start_time,end_time,status,courses(course_code))")
        .eq("faculty_id", faculty_id)
        .execute()
        .data
        or []
    )
    slots = {
        (e["day_of_week"], e["start_time"], e["end_time"], (e.get("courses") or {}).get("course_code"))
        for r in rows
        if (e := r.get("timetable_entries")) and e.get("status", "active") == "active"
    }
    return [{"day_of_week": d, "start_time": s, "end_time": en, "course_code": c} for d, s, en, c in sorted(slots)]


def faculty_meet(client: Any, name: str) -> RetrievalResult:
    base = retrieval.faculty_lookup(client, name)
    for fact in base.facts:
        row = (client.table("faculty").select("id").eq("full_name", fact.data["full_name"]).limit(1).execute().data or [])
        if row:
            fact.data["teaching_slots"] = teaching_slots(client, row[0]["id"])
    base.plan = _plan(StructuredIntent.FACULTY_LOOKUP)
    return base


# ------------------------------------------------------------ courses

_catalog_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # courses/faculty are the same for every signed-in user


def _cached(client: Any, key: str, loader) -> list[dict]:
    hit = _catalog_cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1]
    rows = loader(client)
    _catalog_cache[key] = (time.monotonic(), rows)
    return rows


def all_courses(client: Any) -> list[dict]:
    return _cached(client, "courses", lambda c: c.table("courses").select(
        "id,course_code,course_name,credits,programme,specialisation,semester,prerequisites,syllabus_summary,status"
    ).eq("status", "active").execute().data or [])


def all_faculty_names(client: Any) -> list[dict]:
    return _cached(client, "faculty", lambda c: c.table("faculty").select("full_name,initials").eq("status", "active").execute().data or [])


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()


def resolve_course(client: Any, code: Optional[str] = None, name: Optional[str] = None) -> Optional[dict]:
    courses = all_courses(client)
    if code:
        target = code.replace(" ", "").upper()
        for c in courses:
            if c["course_code"].replace(" ", "").upper() == target:
                return c
        return None
    if name:
        n = _norm(name)
        n_tokens = set(n.split()) - {"the", "a", "of", "and", "course", "class", "subject"}
        best, best_score = None, 0.0
        for c in courses:
            cn = _norm(c["course_name"])
            if cn == n or (len(n) > 6 and (n in cn or cn in n)):
                return c
            # "datastructures" / "data structure s": compare without spaces too
            n_flat, cn_flat = n.replace(" ", ""), cn.replace(" ", "")
            if len(n_flat) > 8 and (n_flat == cn_flat or n_flat in cn_flat):
                return c
            ct = set(cn.split())
            if n_tokens and ct:
                score = len(n_tokens & ct) / max(len(n_tokens), len(ct))
                if score > best_score:
                    best, best_score = c, score
        if best_score >= 0.6:
            return best
        # "OS", "DAA", "TOC": the initials of a course name, when exactly one course has them.
        acro = re.sub(r"[^a-z]", "", n)
        if 2 <= len(acro) <= 5 and " " not in n.strip():
            skip = {"and", "of", "for", "the", "in", "to", "with", "a", "an"}
            hits = [c for c in courses
                    if "".join(w[0] for w in re.findall(r"[a-z]+", c["course_name"].lower()) if w not in skip) == acro]
            if len(hits) == 1:
                return hits[0]
        return None
    return None


_TITLE_RE = re.compile(r"^\s*(dr|prof|professor|mr|mrs|ms)\.?\s*", re.I)
_PERSON_CUE_RE = re.compile(r"\b(dr|prof|professor|mr|mrs|ms|sir|madam|ma'?am|named|called|who\s+is|faculty|teacher)\b", re.I)
_NAME_MATCH = 0.85  # "jhon"/"john" = 0.875; "joseph"/"joshi" = 0.5


def name_tokens(full_name: str) -> list[str]:
    """"Dr.John Paul Martin" -> ["john", "paul", "martin"] (titles and bare
    initials dropped — nearly every name here has an initial, so initials
    carry no signal)."""
    return [t for t in _norm(_TITLE_RE.sub("", full_name)).split() if len(t) > 2]


# Words that are about the person, not part of their name.
_NOT_NAME = {
    "sir", "mam", "maam", "madam", "miss", "dr", "prof", "professor", "mr", "mrs", "ms", "email", "mail", "id",
    "office", "cabin", "room", "phone", "mobile", "number", "contact", "details", "research", "area", "areas",
    "interest", "interests", "subject", "subjects", "course", "courses", "teach", "teaches", "teaching", "position",
    "designation", "profile", "find", "whats", "what", "who", "whom", "where", "does", "his", "her", "their",
    "faculty", "teacher", "can", "get", "give", "send", "want", "need", "know", "please", "pls", "today",
}


def query_name_words(query: str) -> list[str]:
    """The words of a question that could be (part of) a name: possessives
    dropped ("Joseph's"), punctuation inside a word removed ("mirotha;;i"),
    question/attribute words and honorifics removed."""
    t = re.sub(r"['’]s\b", "", (query or "").lower())
    # "Dr.Jobin Jose" (as the directory spells it): split the title off first
    t = re.sub(r"\b(dr|prof|mr|mrs|ms|sri|smt)\.", r"\1 ", t)
    t = re.sub(r"(?<=[a-z])[^a-z\s]+(?=[a-z])", "", t)
    return [w for w in re.findall(r"[a-z]+", t)
            if len(w) > 2 and w not in _FILLER and w not in _NOT_NAME and w not in lexicon.DOMAIN_WORDS]


def match_faculty_names(query: str, faculty: list[dict]) -> list[str]:
    """Everyone in the directory the question could be naming, best first —
    typos included ("Jhon Paul Martin", "mirotha;;i chand"), partial names
    ("Christina Joseph" for "Christina Terese Joseph"), and a first name on
    its own when only one person has it ("Amit sir", "Athira mam", "A Balu").

    Rules: two matching name words is a match. One matching word is a match
    only if that word belongs to one person alone (a shared word like
    "Joseph" returns everyone who has it, for the answer to ask which one).
    Never invents a name: the answer is always someone in the directory."""
    q_words = query_name_words(query)
    if not q_words:
        return []
    owners: dict[str, int] = {}
    for f in faculty:
        for t in set(name_tokens(f["full_name"])):
            owners[t] = owners.get(t, 0) + 1
    person_cue = bool(_PERSON_CUE_RE.search(query)) or bool(re.search(r"\b(mam|maam|miss)\b", query, re.I))
    scored: list[tuple[int, float, str]] = []
    for f in faculty:
        toks = name_tokens(f["full_name"])
        if not toks:
            continue
        hits, total, unique = 0, 0.0, False
        for t in toks:
            sim = max(lexicon.similarity(w, t) for w in q_words)
            # a short word must match exactly ("amit", "balu"); longer ones may carry a typo
            if sim >= (1.0 if len(t) <= 4 else _NAME_MATCH):
                hits += 1
                total += sim
                if owners.get(t, 0) == 1:
                    unique = True
        if hits >= 2 or (hits == 1 and (unique or person_cue)):
            scored.append((hits, total, f["full_name"]))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    top_hits = scored[0][0]
    best = [n for h, _, n in scored if h == top_hits]
    # One clear best (more words matched, or a unique word): that person.
    if len(best) == 1 or top_hits >= 2:
        top_total = scored[0][1]
        return [n for h, t, n in scored if h == top_hits and abs(t - top_total) < 1e-9][:3]
    return best[:3] if person_cue else []


def match_faculty_name(query: str, faculty: list[dict]) -> Optional[str]:
    """The single person a question names, or None (none, or ambiguous)."""
    found = match_faculty_names(query, faculty)
    return found[0] if len(found) == 1 else None


def faculty_subjects(client: Any, faculty_id: int) -> list[dict]:
    """What a faculty member teaches, from the live timetable: one row per
    course (with the kinds of sessions and the classes they take)."""
    rows = (
        client.table("timetable_entry_faculty")
        .select("timetable_entries(entry_type,semester,department,section,status,courses(course_code,course_name))")
        .eq("faculty_id", faculty_id)
        .execute()
        .data
        or []
    )
    courses: dict[str, dict] = {}
    for r in rows:
        e = r.get("timetable_entries") or {}
        course = e.get("courses") or {}
        if e.get("status") != "active" or not course.get("course_code"):
            continue
        c = courses.setdefault(course["course_code"], {"course_code": course["course_code"],
                                                       "course_name": course.get("course_name"),
                                                       "types": set(), "classes": set()})
        c["types"].add(e.get("entry_type") or "class")
        c["classes"].add(f"S{e.get('semester')} {e.get('department')} {e.get('section') or ''}".strip())
    return [{**c, "types": sorted(c["types"]), "classes": sorted(c["classes"])}
            for c in sorted(courses.values(), key=lambda c: c["course_code"])]


def link_entities(client: Any, query: str) -> dict[str, str]:
    """Course or faculty names mentioned without a code/title ("What is IT
    Workshop III?", "what does Manu Madhavan research", "who is jhon paul
    martin") — course names exactly, people fuzzily."""
    q = f" {_norm(query)} "
    found: dict[str, str] = {}
    for c in sorted(all_courses(client), key=lambda c: -len(c["course_name"])):
        cn = _norm(c["course_name"])
        if len(cn) > 5 and f" {cn} " in q:
            found["course_code"] = c["course_code"]
            break
    name = match_faculty_name(query, all_faculty_names(client))
    if name:
        found["faculty_name"] = name
    return found


_LTPC_RE = r"\[\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*\]"


_DEPT_CURRICULUM = [("CYBER", "Cyber"), ("ARTIFICIAL", "AI & DS"), ("DATA SCIENCE", "AI & DS"),
                    ("ELECTRONICS", "ECE"), ("MATHEMATICS", "Mathematics"), ("COMPUTER SCIENCE", "CSE Curriculum")]


def credits_from_curriculum(client: Any, course_code: str, family: Optional[str], department: Optional[str] = None) -> Optional[dict]:
    """courses.credits is empty for most rows, but every curriculum prints
    `CODE Name [L-T-P-C]`. Read C from the student's own curriculum."""
    compact = course_code.replace(" ", "")
    res = client.rpc("search_document_chunks", {
        "query_text": f"{compact} {course_code}", "match_count": 12, "cohort_family": family,
        "filter_document_type": "curriculum",
    }).execute().data or []
    code_re = re.escape(course_code).replace(r"\ ", r"\s*")
    pattern = re.compile(rf"{code_re}\s*[:\-–]?\s*([A-Za-z][^\[\]]{{2,90}}?)\s*{_LTPC_RE}")
    table = re.compile(rf"{code_re}\s+[A-Za-z,.&()\s]{{3,80}}?\s(\d)\s(\d)\s(\d)\s(\d{{1,2}})\b")
    dept = (department or "").upper()
    preferred = next((frag for key, frag in _DEPT_CURRICULUM if key in dept), None)
    if preferred:
        res.sort(key=lambda r: preferred.lower() not in r["title"].lower())
    for r in res:
        text = re.sub(r"\s+", " ", r["content"])
        m = pattern.search(text)
        if not m:
            t = table.search(text)
            if t:
                return {"lecture": int(t.group(1)), "tutorial": int(t.group(2)), "practical": int(t.group(3)),
                        "credits": int(t.group(4)), "document_title": r["title"], "page": r.get("page_start")}
        if m:
            return {"lecture": int(m.group(2)), "tutorial": int(m.group(3)), "practical": int(m.group(4)),
                    "credits": int(m.group(5)), "document_title": r["title"], "page": r.get("page_start")}
    return None


def course_info(client: Any, course_code: str, family: Optional[str], department: Optional[str] = None) -> RetrievalResult:
    course = resolve_course(client, code=course_code)
    if not course:
        return RetrievalResult(plan=_plan(StructuredIntent.COURSE_INFO),
                               warnings=[f"course code {course_code!r} not found in the active course catalog"])
    data = dict(course)
    if data.get("credits") is None:
        ltpc = credits_from_curriculum(client, course["course_code"], family, department)
        if ltpc:
            data["curriculum"] = ltpc
    return RetrievalResult(plan=_plan(StructuredIntent.COURSE_INFO),
                           facts=[StructuredFact(claim=f"{course['course_code']} {course['course_name']}", data=data,
                                                 source="courses (live)" + (" + curriculum" if data.get("curriculum") else ""))])


def faculty_for_course(client: Any, course_code: Optional[str], course_name: Optional[str],
                       entry_type: Optional[str] = None) -> RetrievalResult:
    course = resolve_course(client, code=course_code, name=None if course_code else course_name)
    if not course:
        label = course_code or course_name or "that course"
        return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_FOR_COURSE),
                               warnings=[f"couldn't find a course matching {label!r} in the catalog"])
    result = retrieval.faculty_for_course(client, course["course_code"], entry_type)
    for fact in result.facts:
        fact.data["course"] = {"course_code": course["course_code"], "course_name": course["course_name"]}
    if not result.facts:
        result.facts.append(StructuredFact(claim=course["course_code"], data={"course": course, "_no_faculty": True},
                                           source="courses (live)"))
    result.plan = _plan(StructuredIntent.FACULTY_FOR_COURSE)
    return result


# ------------------------------------------------------------ my timetable views

def my_courses(client: Any) -> RetrievalResult:
    week = retrieval.week_timetable(client)
    courses: dict[str, dict] = {}
    for f in week.facts:
        e = f.data
        code = e.get("course_code")
        if not code:
            continue
        c = courses.setdefault(code, {"course_code": code, "course_name": e.get("course_name"),
                                      "faculty": set(), "types": set(), "sessions": 0})
        c["faculty"].update(e.get("faculty_names") or [])
        c["types"].add(e.get("entry_type") or "class")
        c["sessions"] += 1
    facts = [
        StructuredFact(claim=f"{c['course_code']} {c['course_name']}",
                       data={**c, "faculty": sorted(c["faculty"]), "types": sorted(c["types"])},
                       source="orion_week_timetable RPC (live timetable)")
        for c in sorted(courses.values(), key=lambda c: c["course_code"])
    ]
    return RetrievalResult(plan=_plan(StructuredIntent.MY_COURSES), facts=facts,
                           warnings=[] if facts else ["no courses found in your active timetable"])


def free_time(client: Any, day_ref: str, on_date: Optional[date] = None) -> RetrievalResult:
    """Gaps in the caller's own timetable for one day — "when am I free
    today", "do I have a free period tomorrow", "any free classes on
    Friday". `on_date` is the date the router already resolved
    (QueryPlan.resolved_date); it is the date actually queried, so the
    answer can never talk about a different day than it looked up."""
    target = on_date or retrieval._resolve_day_reference(day_ref) or today_ist()
    if target == today_ist():
        result = retrieval.day_timetable(client)
    else:
        result = retrieval.day_of_week_timetable(client, day_ref, on_date=target)
    for f in result.facts:
        f.data["_date"] = target.isoformat()
    result.plan = _plan(StructuredIntent.FREE_TIME)
    if not result.facts:
        result.facts.append(StructuredFact(claim="no classes", data={"_date": target.isoformat(), "_empty": True},
                                           source="orion_day_timetable RPC (live timetable)"))
        result.warnings = []
    return result


_ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5"}
_DEPT_ALLOC = [("ELECTRONICS", "ECE"), ("CYBER", "CSY"), ("ARTIFICIAL", "AI&DS"), ("DATA SCIENCE", "AI&DS")]


def classroom(client: Any, profile: Optional[dict]) -> RetrievalResult:
    nxt = retrieval.next_class(client)
    facts = list(nxt.facts)
    if profile:
        allocations = (
            client.table("room_allocations")
            .select("semester,batch,department,section,valid_until,status,source_id,rooms(room_no,room_type)")
            .eq("status", "active")
            .eq("semester", profile.get("semester"))
            .execute()
            .data
            or []
        )
        dept = (profile.get("department") or "").upper()
        dept_code = next((code for key, code in _DEPT_ALLOC if key in dept), None)
        batch = _ROMAN.get((profile.get("batch") or "").strip().upper(), (profile.get("batch") or "").strip())
        match = None
        if dept_code:
            match = next((a for a in allocations if a.get("department") == dept_code), None)
        if not match:
            match = next((a for a in allocations if a.get("batch") == batch and not a.get("department")), None)
        if match and match.get("rooms"):
            facts.append(StructuredFact(
                claim=f"Section classroom: {match['rooms']['room_no']}",
                data={"_classroom": True, "room_no": match["rooms"]["room_no"], "room_type": match["rooms"].get("room_type"),
                      "valid_until": match.get("valid_until")},
                source=f"room_allocations ({match.get('source_id') or 'live'})"))
    return RetrievalResult(plan=_plan(StructuredIntent.CLASSROOM), facts=facts, warnings=nxt.warnings)
