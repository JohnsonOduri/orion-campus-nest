"""Retrieval layer: executes a QueryPlan against Supabase.

Every function here takes a *request-scoped* Supabase client — one built
from the caller's own JWT (anon key + `Authorization: Bearer <jwt>`), the
same pattern src/lib/supabase-server.ts uses for the timetable API
(CLAUDE.md §13/§15). Never service-role. RLS policies already enforce
`status='active'` and validity windows on every table this module touches
(timetable_entries, documents, document_chunks, faculty, courses) — this
module does not duplicate that filtering, it relies on it, the same way the
existing orion_* RPCs do.

Structured retrieval wraps the existing orion_* RPCs (docs/timetable.md) —
nothing about the timetable security model or RPC contracts changes here.
Semantic retrieval wraps the existing pgvector `document_chunks` corpus
(scripts/ingest_documents.py) via a new `match_document_chunks` RPC
(security invoker, so RLS still applies) — this *wraps* pgvector search, it
does not replace it or start a new ingestion pipeline.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any, Optional

from .types import QueryPlan, RetrievalResult, SemanticSnippet, StructuredFact, StructuredIntent

_EMBED_MODEL = None

# The institute's real local time (Asia/Kolkata, IST, UTC+5:30) — every
# "today"/"is this already over" comparison in this module must be done
# against THIS, not raw UTC and not the server process's own OS timezone.
# Found live: at 07:04 UTC (12:34 PM IST), a class that had already ended
# almost two hours earlier was still shown as "next", because 07:04 is
# numerically before the stored "09:30" start time — the printed
# timetable's times are IST wall-clock, not UTC. The orion_next_class/
# orion_day_timetable/orion_week_timetable RPCs do the equivalent
# conversion server-side (see supabase/migrations/
# 20260921000004_timetable_ist_timezone_fix.sql); these two helpers keep
# the Python-side phrasing (today/tomorrow, gap notes, which weekday
# "today" resolves to) consistent with that, not silently drifted from it.
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _now_ist() -> datetime:
    return datetime.now(timezone.utc) + _IST_OFFSET


def _today_ist() -> date:
    return _now_ist().date()


def _embed(text: str) -> list[float]:
    """Local embeddings (sentence-transformers/all-MiniLM-L6-v2, 384-dim) —
    same model used at ingestion time (scripts/ingest_documents.py), so
    query and corpus vectors live in the same space. Loaded lazily and
    cached: the model is ~90MB and this module may be imported without ever
    needing it (a pure STRUCTURED query never touches this)."""
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _EMBED_MODEL.encode([text], normalize_embeddings=True)[0].tolist()


# ------------------------------------------------------------ structured


def _entry_label(data: dict) -> str:
    """A human-readable name for a timetable entry that might not be a
    real course — entry_type='other'/'club_activity'/'sports' rows carry
    no course_code/course_name at all. Falls back to the PDF's own
    descriptive text, then a formatted entry_type, rather than ever
    interpolating a literal "None" into a claim — found live: this exact
    gap produced the claim "Next class: None  today (Monday),
    15:30:00-16:25:00" for an "Interaction with faculty" session, and that
    literal "None" was confusing enough that generation produced a
    self-contradictory answer ("no more classes today" in the same breath
    as stating today's time range)."""
    course_code = data.get("course_code")
    if course_code:
        return f"{course_code} {data.get('course_name') or ''}".strip()
    source_text = data.get("source_text")
    if source_text:
        return source_text
    entry_type = data.get("entry_type") or "class"
    return entry_type.replace("_", " ").title()


def _fetch_next_class_raw(client: Any, at: datetime, include_activities: bool) -> Optional[dict]:
    res = client.rpc(
        "orion_next_class",
        {"p_user_id": None, "p_at": at.isoformat(), "p_include_activities": include_activities},
    ).execute()
    return res.data


def _phrase_for_entry(data: dict, at_ist: datetime, ongoing_label: str) -> tuple[bool, str, str]:
    """(is_ongoing, when_phrase, gap_note) for `data` relative to `at_ist`
    (an IST-shifted/naive-IST reference instant with isoweekday()/strftime())."""
    entry_day = data.get("day_of_week")
    weekday_name = _day_name(entry_day)
    start_time = data.get("start_time") or ""
    end_time = data.get("end_time") or ""
    now_str = at_ist.strftime("%H:%M:%S")
    is_today = entry_day == at_ist.isoweekday() and end_time > now_str
    is_ongoing = is_today and start_time <= now_str
    if is_ongoing:
        return True, ongoing_label, ""
    if is_today:
        return False, f"today ({weekday_name})", ""
    days_until = ((entry_day - at_ist.isoweekday() + 6) % 7) + 1 if entry_day is not None else None
    if days_until == 1:
        return False, f"tomorrow ({weekday_name})", " (you have no more classes today)"
    # This is genuinely the chronologically nearest class the RPC found
    # (that's what "next class" ordering guarantees), so it's always true
    # that nothing is scheduled in the gap — surfacing that explicitly is
    # what stops a multi-day jump from reading as random.
    gap_note = f" (no classes are scheduled between now and then — {days_until} days away)" if days_until else ""
    return False, weekday_name, gap_note


def next_class(
    client: Any,
    at: Optional[datetime] = None,
    include_activities: bool = False,
    ongoing_label: str = "right now",
) -> RetrievalResult:
    """`ongoing_label` names the reference instant when the returned entry
    is ongoing at it — "right now" for a live "what's my next class"
    query, but callers evaluating a hypothetical time (class_at_time, e.g.
    "what class do I have at 3pm?") pass a label naming that time instead,
    since it isn't actually the current moment."""
    at = at or datetime.now(timezone.utc)
    data = _fetch_next_class_raw(client, at, include_activities)
    if not data:
        return RetrievalResult(
            plan=_plan(StructuredIntent.NEXT_CLASS),
            warnings=["no upcoming class found in the resolved student's active, valid timetable"],
        )
    at_ist = at + _IST_OFFSET
    # The RPC deliberately still returns an in-progress session as the
    # "next" occurrence (its own comment: "ongoing classes count") rather
    # than skipping ahead — that selection is intentional and stays as-is.
    # But phrasing it as "next class" for something already under way reads
    # as self-contradictory, and simply saying "no info about what comes
    # after" is also wrong — that information does exist, it just requires
    # a second lookup because the RPC only ever returns one occurrence. So
    # when the current result is ongoing, look ahead from its end_time to
    # find the class that genuinely comes after it and fold both into the
    # answer, instead of pretending we can't say.
    is_ongoing, when_phrase, gap_note = _phrase_for_entry(data, at_ist, ongoing_label)
    if is_ongoing:
        end_time = data.get("end_time") or "23:59:59"
        followup_ist = datetime.combine(at_ist.date(), dt_time.fromisoformat(end_time))
        followup_at = (followup_ist - _IST_OFFSET).replace(tzinfo=timezone.utc)
        followup_data = _fetch_next_class_raw(client, followup_at, include_activities)
        claim = (
            f"Currently ongoing: {_entry_label(data)} {when_phrase} "
            f"({data.get('start_time')}-{data.get('end_time')})."
        )
        if followup_data and followup_data != data:
            f_when_phrase, f_gap_note = _phrase_for_entry(followup_data, followup_ist, ongoing_label)[1:]
            claim += (
                f" After that, next class: {_entry_label(followup_data)} "
                f"{f_when_phrase}, {followup_data.get('start_time')}-{followup_data.get('end_time')}{f_gap_note}"
            )
        else:
            claim += " You have no more classes scheduled for the rest of today."
    else:
        claim = (
            f"Next class: {_entry_label(data)} "
            f"{when_phrase}, {data.get('start_time')}-{data.get('end_time')}{gap_note}"
        )
    fact = StructuredFact(
        claim=claim.strip(),
        data=data,
        source="orion_next_class RPC (live timetable)",
        source_id=data.get("source_id"),
    )
    return RetrievalResult(plan=_plan(StructuredIntent.NEXT_CLASS), facts=[fact])


_TIME_TEXT_RE = re.compile(
    r"^(?:([01]?\d|2[0-3]):([0-5]\d)|(1[0-2]|0?[1-9]))\s*(am|pm)?$", re.IGNORECASE
)


def _parse_time_text(text: str) -> Optional[dt_time]:
    """"10:30", "3pm", "14:00", "9 am" -> a time-of-day. Returns None for
    anything unrecognized rather than guessing."""
    m = _TIME_TEXT_RE.match(text.strip())
    if not m:
        return None
    meridiem = (m.group(4) or "").lower()
    if m.group(1) is not None:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        hour, minute = int(m.group(3)), 0
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23:
        return None
    return dt_time(hour, minute)


def class_at_time(client: Any, time_text: str) -> RetrievalResult:
    """"What is my class from 10:30?", "what class do I have at 3pm?" —
    evaluates next_class() as of that specific time today instead of the
    actual current time, so a class covering (or the next one after) that
    moment is picked up the same way NEXT_CLASS already picks up an
    ongoing-right-now class. Reuses next_class() entirely rather than a
    second RPC-calling/claim-building implementation."""
    parsed = _parse_time_text(time_text)
    if parsed is None:
        return RetrievalResult(
            plan=_plan(StructuredIntent.CLASS_AT_TIME),
            warnings=[f"unrecognized time: {time_text!r}"],
        )
    # The caller means this time-of-day in IST (today, institute-local) —
    # build the naive "IST wall-clock" instant, then convert to the
    # equivalent UTC instant next_class()/the RPC actually expect.
    ist_dt = datetime.combine(_today_ist(), parsed)
    at = (ist_dt - _IST_OFFSET).replace(tzinfo=timezone.utc)
    result = next_class(client, at=at, ongoing_label=f"at {parsed.strftime('%H:%M')}")
    result.plan = _plan(StructuredIntent.CLASS_AT_TIME)
    return result


def day_timetable(client: Any, on_date: Optional[str] = None) -> RetrievalResult:
    args = {"p_user_id": None, "p_on_date": on_date}
    res = client.rpc("orion_day_timetable", args).execute()
    entries = res.data or []
    facts = [
        StructuredFact(
            claim=f"{_entry_label(e)} {e.get('start_time')}-{e.get('end_time')}",
            data=e,
            source="orion_day_timetable RPC (live timetable)",
            source_id=e.get("source_id"),
        )
        for e in entries
    ]
    warnings = [] if entries else ["no active, valid entries for this day"]
    return RetrievalResult(plan=_plan(StructuredIntent.DAY_TIMETABLE), facts=facts, warnings=warnings)


def week_timetable(client: Any, on_date: Optional[str] = None) -> RetrievalResult:
    args = {"p_user_id": None, "p_on_date": on_date}
    res = client.rpc("orion_week_timetable", args).execute()
    entries = res.data or []
    facts = [
        StructuredFact(
            claim=f"{_entry_label(e)} {_day_name(e.get('day_of_week'))} "
            f"{e.get('start_time')}-{e.get('end_time')}",
            data=e,
            source="orion_week_timetable RPC (live timetable)",
            source_id=e.get("source_id"),
        )
        for e in entries
    ]
    warnings = [] if entries else ["no active, valid entries for this week"]
    return RetrievalResult(plan=_plan(StructuredIntent.WEEK_TIMETABLE), facts=facts, warnings=warnings)


_WEEKDAY_TO_NUM = {
    "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
    "Friday": 5, "Saturday": 6, "Sunday": 7,
}
_WEEKDAY_NAME = {v: k for k, v in _WEEKDAY_TO_NUM.items()}


def _day_name(day_of_week: Optional[int]) -> str:
    return _WEEKDAY_NAME.get(day_of_week, f"day {day_of_week}")


def _resolve_day_reference(day_ref: str) -> Optional[date]:
    """"yesterday" / "tomorrow" / a named weekday -> an actual date. Shared
    by both timetable (day_of_week_timetable) and mess (mess_on_day) — one
    implementation instead of two near-identical ones."""
    ref = day_ref.strip().lower()
    today = _today_ist()
    if ref == "yesterday":
        return today - timedelta(days=1)
    if ref == "tomorrow":
        return today + timedelta(days=1)
    target_num = _WEEKDAY_TO_NUM.get(day_ref.strip().capitalize())
    if target_num is not None:
        offset = (target_num - today.isoweekday()) % 7
        return today + timedelta(days=offset)
    return None


def day_of_week_timetable(client: Any, day_ref: str) -> RetrievalResult:
    """"What classes do I have on Monday?", "what are my classes
    tomorrow?", "what did I have yesterday?" — resolves the actual
    referenced date (nearest upcoming occurrence for a named weekday,
    today counts if today already is that weekday) then calls
    orion_day_timetable for that specific date — same RPC and validity/
    status filtering as every other timetable query, just with the date
    computed from the reference instead of always "today"."""
    target = _resolve_day_reference(day_ref)
    if target is None:
        return RetrievalResult(
            plan=_plan(StructuredIntent.DAY_OF_WEEK_TIMETABLE),
            warnings=[f"unrecognized day reference: {day_ref!r}"],
        )
    target_date = target.isoformat()

    res = client.rpc("orion_day_timetable", {"p_user_id": None, "p_on_date": target_date}).execute()
    entries = res.data or []
    facts = [
        StructuredFact(
            claim=f"{_entry_label(e)} {e.get('start_time')}-{e.get('end_time')} "
            f"({day_ref} {target_date})",
            data=e,
            source="orion_day_timetable RPC (live timetable)",
            source_id=e.get("source_id"),
        )
        for e in entries
    ]
    warnings = [] if entries else [f"no active, valid entries for {day_ref} ({target_date})"]
    return RetrievalResult(plan=_plan(StructuredIntent.DAY_OF_WEEK_TIMETABLE), facts=facts, warnings=warnings)


def faculty_for_course(client: Any, course_code: str) -> RetrievalResult:
    """RLS-scoped direct table query (no RPC needed): courses + timetable
    join, respecting the same `status='active'` policies as the RPCs."""
    course_res = (
        client.table("courses")
        .select("id,course_code,course_name")
        .ilike("course_code", course_code.replace(" ", "%"))
        .limit(1)
        .execute()
    )
    if not course_res.data:
        return RetrievalResult(
            plan=_plan(StructuredIntent.FACULTY_FOR_COURSE),
            warnings=[f"course code {course_code!r} not found in the active course catalog"],
        )
    course = course_res.data[0]
    entries = (
        client.table("timetable_entries")
        .select("id,faculty_id")
        .eq("course_id", course["id"])
        .execute()
        .data
    )
    faculty_ids = sorted({e["faculty_id"] for e in entries if e.get("faculty_id")})
    facts: list[StructuredFact] = []
    if faculty_ids:
        fac_rows = (
            client.table("faculty").select("id,full_name,initials,email").in_("id", faculty_ids).execute().data
        )
        for f in fac_rows:
            facts.append(
                StructuredFact(
                    claim=f"{f['full_name']} ({f['initials']}) teaches {course['course_code']}",
                    data={**f, "course": course},
                    source="timetable_entries + faculty (live timetable)",
                )
            )
    warnings = [] if facts else [f"no active faculty link found for {course['course_code']}"]
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_FOR_COURSE), facts=facts, warnings=warnings)


def course_info(client: Any, course_code: str) -> RetrievalResult:
    """"What is ICS 211 about?", "How many credits is CSE 311?", "syllabus
    for IEG 311" — direct RLS-scoped lookup, no RPC needed. States
    course_name/programme/semester always (never null in practice);
    credits/prerequisites/syllabus_summary are stated only when present —
    confirmed live this session that coverage is inconsistent across the
    catalog (e.g. some Sem 5 electives have null credits), so this never
    prints a false "not available" for a field that might just not be
    fetched yet vs. genuinely never populated; it simply omits what's null."""
    res = (
        client.table("courses")
        .select("course_code,course_name,credits,programme,specialisation,semester,prerequisites,syllabus_summary")
        .ilike("course_code", course_code.replace(" ", "%"))
        .limit(1)
        .execute()
    )
    if not res.data:
        return RetrievalResult(
            plan=_plan(StructuredIntent.COURSE_INFO),
            warnings=[f"course code {course_code!r} not found in the active course catalog"],
        )
    c = res.data[0]
    parts = [f"{c['course_code']} {c['course_name']}"]
    if c.get("credits") is not None:
        parts.append(f"{c['credits']} credits")
    if c.get("programme"):
        parts.append(f"{c['programme']}")
    if c.get("semester") is not None:
        parts.append(f"semester {c['semester']}")
    if c.get("prerequisites"):
        parts.append(f"prerequisites: {c['prerequisites']}")
    if c.get("syllabus_summary"):
        parts.append(f"syllabus: {c['syllabus_summary']}")
    claim = ", ".join(parts)
    fact = StructuredFact(claim=claim, data=c, source="courses (live)", source_id=None)
    return RetrievalResult(plan=_plan(StructuredIntent.COURSE_INFO), facts=[fact])


def faculty_lookup(client: Any, name_text: str) -> RetrievalResult:
    """"Tell me about Dr. X", "What is Dr. X's email?" — fuzzy ILIKE match
    on full_name (limit 3, not 1: common names/initials could plausibly
    match more than one row, so ambiguous matches are surfaced as multiple
    facts for generation to disambiguate rather than silently guessing).
    Confirmed live this session: 70 faculty rows, only 28 with real email/
    office_location — a fact still states whatever IS known (full_name,
    initials, status) rather than producing nothing at all when the
    enrichment fields happen to be null."""
    cleaned = name_text.strip()
    rows = (
        client.table("faculty")
        .select("full_name,initials,email,office_location,office_hours,research_interests,status")
        .ilike("full_name", f"%{cleaned}%")
        .eq("status", "active")
        .limit(3)
        .execute()
        .data
        or []
    )
    if not rows:
        return RetrievalResult(
            plan=_plan(StructuredIntent.FACULTY_LOOKUP),
            warnings=[f"no faculty found matching {name_text!r}"],
        )
    facts = []
    for f in rows:
        parts = [f"{f['full_name']} ({f['initials']})"]
        if f.get("email"):
            parts.append(f"email: {f['email']}")
        if f.get("office_location"):
            parts.append(f"office: {f['office_location']}")
        if f.get("office_hours"):
            parts.append(f"office hours: {f['office_hours']}")
        if f.get("research_interests"):
            parts.append(f"research interests: {f['research_interests']}")
        facts.append(StructuredFact(claim=", ".join(parts), data=f, source="faculty (live)", source_id=None))
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_LOOKUP), facts=facts)


# ------------------------------------------------------------- mess menu
#
# Shared with backend/app/api/mess.py's GET /mess/today and /mess/week —
# this module is the one implementation, the REST endpoints import from
# here rather than keeping their own copy. The live mess_menus table only
# has August 2026 data; each day falls back to the most recent upload for
# that same weekday (a real weekly-rotation hostel practice, confirmed
# byte-identical week to week), tagged is_actual=False so callers can be
# honest that it's a repeated cycle, not a freshly published menu.


def split_mess_items(rows: list[dict]) -> list[dict]:
    for row in rows:
        raw = row.get("items")
        row["items"] = [s.strip() for s in raw.split(",")] if raw else []
    return rows


def mess_all_active_rows(client: Any) -> list[dict]:
    return (
        client.table("mess_menus")
        .select("id,menu_date,meal,items,status")
        .eq("status", "active")
        .execute()
        .data
        or []
    )


def mess_menu_for_day(all_rows: list[dict], target: date) -> list[dict]:
    exact = [r for r in all_rows if r["menu_date"] == target.isoformat()]
    if exact:
        return [
            {**r, "display_date": target.isoformat(), "source_date": r["menu_date"], "is_actual": True}
            for r in exact
        ]
    candidates = [r for r in all_rows if date.fromisoformat(r["menu_date"]).weekday() == target.weekday()]
    if not candidates:
        return []
    latest_date = max(c["menu_date"] for c in candidates)
    return [
        {**r, "display_date": target.isoformat(), "source_date": r["menu_date"], "is_actual": False}
        for r in candidates
        if r["menu_date"] == latest_date
    ]


def _mess_fact(row: dict) -> StructuredFact:
    items = ", ".join(row["items"]) if row["items"] else "no items listed"
    claim = f"{row['meal'].capitalize()} on {row['display_date']}: {items}"
    if not row["is_actual"]:
        weekday_name = date.fromisoformat(row["source_date"]).strftime("%A")
        claim += f" (most recent {weekday_name} menu on file, from {row['source_date']} — not confirmed for this date)"
    return StructuredFact(claim=claim, data=row, source="mess_menus (live)", source_id=str(row.get("id")))


def _filter_meal(rows: list[dict], meal: Optional[str]) -> list[dict]:
    return [r for r in rows if r["meal"] == meal] if meal else rows


def mess_today(client: Any, meal: Optional[str] = None) -> RetrievalResult:
    all_rows = mess_all_active_rows(client)
    rows = split_mess_items(sorted(mess_menu_for_day(all_rows, _today_ist()), key=lambda r: r["meal"]))
    facts = [_mess_fact(r) for r in _filter_meal(rows, meal)]
    warnings = [] if facts else ["no active mess menu found for today or the most recent matching weekday"]
    return RetrievalResult(plan=_plan(StructuredIntent.MESS_TODAY), facts=facts, warnings=warnings)


def mess_week(client: Any, meal: Optional[str] = None) -> RetrievalResult:
    all_rows = mess_all_active_rows(client)
    today = _today_ist()
    week_start = today - timedelta(days=today.weekday())
    rows: list[dict] = []
    for i in range(7):
        rows.extend(mess_menu_for_day(all_rows, week_start + timedelta(days=i)))
    rows.sort(key=lambda r: (r["display_date"], r["meal"]))
    facts = [_mess_fact(r) for r in _filter_meal(split_mess_items(rows), meal)]
    warnings = [] if facts else ["no active mess menu found for this week or the most recent matching weekdays"]
    return RetrievalResult(plan=_plan(StructuredIntent.MESS_WEEK), facts=facts, warnings=warnings)


def mess_on_day(client: Any, day_ref: str, meal: Optional[str] = None) -> RetrievalResult:
    """"Yesterday's dinner", "what's for lunch tomorrow", "mess menu on
    Monday" — resolves the actual referenced date (never silently falling
    back to today's menu, the bug found live: mess_today() always used
    date.today() regardless of what the query asked for) and reuses the
    same weekly-rotation fallback every other mess lookup uses."""
    target = _resolve_day_reference(day_ref)
    if target is None:
        return RetrievalResult(
            plan=_plan(StructuredIntent.MESS_ON_DAY),
            warnings=[f"unrecognized day reference: {day_ref!r}"],
        )
    all_rows = mess_all_active_rows(client)
    rows = split_mess_items(sorted(mess_menu_for_day(all_rows, target), key=lambda r: r["meal"]))
    facts = [_mess_fact(r) for r in _filter_meal(rows, meal)]
    warnings = [] if facts else [f"no active mess menu found for {target.isoformat()} or the most recent matching weekday"]
    return RetrievalResult(plan=_plan(StructuredIntent.MESS_ON_DAY), facts=facts, warnings=warnings)


def _plan(intent: StructuredIntent) -> QueryPlan:
    from .types import RouteType

    return QueryPlan(raw_query="", route=RouteType.STRUCTURED, structured_intent=intent)


# --------------------------------------------------------------- semantic


def semantic_search(
    client: Any,
    query_text: str,
    top_k: int = 5,
    cohort: Optional[str] = None,
    category: Optional[str] = None,
    document_type: Optional[str] = None,
) -> RetrievalResult:
    """Wraps the existing pgvector `document_chunks` corpus via
    `match_document_chunks` (security invoker — RLS still applies to the
    caller's role). Cohort/category/document_type filters are optional and,
    when the caller is a student, should come from their authenticated
    academic context (cohort), never parsed from free query text
    (AGENTS.md §17) — the router intentionally never sets `semantic_filters`
    for a plain SEMANTIC query; a caller (e.g. the future API layer) can
    pass the student's own cohort in explicitly.
    """
    from .types import RouteType

    embedding = _embed(query_text)
    res = client.rpc(
        "match_document_chunks",
        {
            "query_embedding": embedding,
            "match_count": top_k,
            "filter_cohort": cohort,
            "filter_category": category,
            "filter_document_type": document_type,
        },
    ).execute()
    rows = res.data or []
    snippets = [
        SemanticSnippet(
            content=r["content"],
            document_title=r["title"],
            section_title=r.get("section_title"),
            page_start=r.get("page_start"),
            page_end=r.get("page_end"),
            similarity=r["similarity"],
            cohort=r.get("cohort"),
            category=r.get("category"),
            document_type=r.get("document_type"),
            valid_from=str(r["valid_from"]) if r.get("valid_from") else None,
            valid_until=str(r["valid_until"]) if r.get("valid_until") else None,
        )
        for r in rows
    ]
    warnings = [] if snippets else ["no document chunks matched — say so, never invent an answer"]
    plan = QueryPlan(raw_query=query_text, route=RouteType.SEMANTIC, topic_text=query_text)
    return RetrievalResult(plan=plan, snippets=snippets, warnings=warnings)


# ----------------------------------------------------------------- hybrid


def faculty_topic_and_schedule(client: Any, topic: str, top_k: int = 5, min_similarity: float = 0.19) -> RetrievalResult:
    """Hybrid: faculty.research_interests semantic match (small in-memory
    set — no vector index needed for ~60 rows) + their live teaching
    schedule as the closest evidenced proxy for "when can I meet them".

    Never claims office-hours availability that isn't on file — AGENTS.md
    §18: "if the data cannot establish availability, say so." Faculty
    availability here is teaching-schedule-derived, explicitly labeled as
    such, never presented as confirmed office hours.

    `min_similarity=0.19` is tuned against this corpus for short
    acronym-style topics ("NLP"): a small local model (MiniLM, 384-dim)
    scores an acronym against a full research-interest phrase lower than a
    spelled-out query would (verified: "Natural Language Processing" as a
    literal first-listed interest scores 0.20-0.30 for the query "NLP", not
    0.5+). The threshold is set below that band, not at a theoretically
    "clean" cosine cutoff — retuning the corpus or swapping the embedding
    model should revisit this constant.
    """
    from .types import RouteType

    fac_rows = (
        client.table("faculty")
        .select("id,full_name,initials,email,office_location,office_hours,research_interests")
        .not_.is_("research_interests", "null")
        .execute()
        .data
    )
    if not fac_rows:
        return RetrievalResult(
            plan=QueryPlan(raw_query=topic, route=RouteType.HYBRID, topic_text=topic),
            warnings=["no faculty rows have research_interests on file"],
        )

    query_vec = _embed(topic)
    texts = [f["research_interests"] for f in fac_rows]
    from sentence_transformers import SentenceTransformer

    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    corpus_vecs = _EMBED_MODEL.encode(texts, normalize_embeddings=True)
    import numpy as np

    sims = corpus_vecs @ np.array(query_vec)
    ranked = sorted(zip(fac_rows, sims), key=lambda t: -t[1])[:top_k]

    facts: list[StructuredFact] = []
    warnings: list[str] = []
    for f, sim in ranked:
        if sim < min_similarity:
            continue
        schedule = (
            client.table("timetable_entry_faculty")
            .select("entry_id, timetable_entries(day_of_week,start_time,end_time,course_id, courses(course_code))")
            .eq("faculty_id", f["id"])
            .execute()
            .data
        )
        slots = {
            (
                row["timetable_entries"]["day_of_week"],
                row["timetable_entries"]["start_time"],
                row["timetable_entries"]["end_time"],
                (row["timetable_entries"].get("courses") or {}).get("course_code"),
            )
            for row in schedule
            if row.get("timetable_entries")
        }
        has_office_hours = bool(f.get("office_hours"))
        claim = f"{f['full_name']} ({f['initials']}) — research match for {topic!r} (similarity {sim:.2f})"
        facts.append(
            StructuredFact(
                claim=claim,
                data={
                    "faculty": {k: f[k] for k in ("full_name", "initials", "email", "office_location", "office_hours")},
                    "similarity": float(sim),
                    "teaching_slots": [
                        {"day_of_week": d, "start_time": s, "end_time": e, "course_code": c}
                        for d, s, e, c in sorted(slots)
                    ],
                    "availability_basis": "office_hours" if has_office_hours else "teaching_schedule_only",
                },
                source="faculty.research_interests (local embedding match) + timetable_entries (live schedule)",
            )
        )
        if not has_office_hours:
            warnings.append(
                f"{f['full_name']}: no office_hours on file — reporting teaching schedule only, "
                "not confirmed availability (AGENTS.md §18)"
            )

    if not facts:
        warnings.append(f"no faculty research_interests matched {topic!r} above the similarity threshold")
    return RetrievalResult(
        plan=QueryPlan(raw_query=topic, route=RouteType.HYBRID, topic_text=topic),
        facts=facts,
        warnings=warnings,
    )
