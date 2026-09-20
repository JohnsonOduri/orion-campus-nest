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

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .types import QueryPlan, RetrievalResult, SemanticSnippet, StructuredFact, StructuredIntent

_EMBED_MODEL = None


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


def next_class(client: Any, at: Optional[datetime] = None, include_activities: bool = False) -> RetrievalResult:
    at = at or datetime.now(timezone.utc)
    res = client.rpc(
        "orion_next_class",
        {"p_user_id": None, "p_at": at.isoformat(), "p_include_activities": include_activities},
    ).execute()
    data = res.data
    if not data:
        return RetrievalResult(
            plan=_plan(StructuredIntent.NEXT_CLASS),
            warnings=["no upcoming class found in the resolved student's active, valid timetable"],
        )
    entry_day = data.get("day_of_week")
    weekday_name = _day_name(entry_day)
    end_time = data.get("end_time") or ""
    is_today = entry_day == at.isoweekday() and end_time > at.strftime("%H:%M:%S")
    if is_today:
        when_phrase = f"today ({weekday_name})"
        gap_note = ""
    else:
        days_until = ((entry_day - at.isoweekday() + 6) % 7) + 1 if entry_day is not None else None
        if days_until == 1:
            when_phrase = f"tomorrow ({weekday_name})"
            gap_note = " (you have no more classes today)"
        else:
            when_phrase = weekday_name
            # This is genuinely the chronologically nearest class the RPC found
            # (that's what "next class" ordering guarantees), so it's always
            # true that nothing is scheduled in the gap — surfacing that
            # explicitly is what stops a multi-day jump from reading as random.
            gap_note = f" (no classes are scheduled between now and then — {days_until} days away)" if days_until else ""
    claim = (
        f"Next class: {data.get('course_code')} {data.get('course_name') or ''} "
        f"{when_phrase}, {data.get('start_time')}-{data.get('end_time')}{gap_note}"
    ).strip()
    fact = StructuredFact(
        claim=claim,
        data=data,
        source="orion_next_class RPC (live timetable)",
        source_id=data.get("source_id"),
    )
    return RetrievalResult(plan=_plan(StructuredIntent.NEXT_CLASS), facts=[fact])


def day_timetable(client: Any, on_date: Optional[str] = None) -> RetrievalResult:
    args = {"p_user_id": None, "p_on_date": on_date}
    res = client.rpc("orion_day_timetable", args).execute()
    entries = res.data or []
    facts = [
        StructuredFact(
            claim=f"{e.get('course_code') or e.get('entry_type')} {e.get('start_time')}-{e.get('end_time')}",
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
            claim=f"{e.get('course_code') or e.get('entry_type')} {_day_name(e.get('day_of_week'))} "
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


def day_of_week_timetable(client: Any, weekday_name: str) -> RetrievalResult:
    """"What classes do I have on Monday?" — resolves to the nearest
    upcoming occurrence of that weekday (today counts if today already is
    that weekday), then calls orion_day_timetable for that specific date —
    same RPC and validity/status filtering as every other timetable query,
    just with the date computed from a weekday name instead of "today"."""
    target_num = _WEEKDAY_TO_NUM.get(weekday_name)
    if target_num is None:
        return RetrievalResult(
            plan=_plan(StructuredIntent.DAY_OF_WEEK_TIMETABLE),
            warnings=[f"unrecognized weekday name: {weekday_name!r}"],
        )
    today = datetime.now(timezone.utc)
    offset = (target_num - today.isoweekday()) % 7
    target_date = (today + timedelta(days=offset)).date().isoformat()

    res = client.rpc("orion_day_timetable", {"p_user_id": None, "p_on_date": target_date}).execute()
    entries = res.data or []
    facts = [
        StructuredFact(
            claim=f"{e.get('course_code') or e.get('entry_type')} {e.get('start_time')}-{e.get('end_time')} "
            f"({weekday_name} {target_date})",
            data=e,
            source="orion_day_timetable RPC (live timetable)",
            source_id=e.get("source_id"),
        )
        for e in entries
    ]
    warnings = [] if entries else [f"no active, valid entries for {weekday_name} ({target_date})"]
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
    rows = split_mess_items(sorted(mess_menu_for_day(all_rows, date.today()), key=lambda r: r["meal"]))
    facts = [_mess_fact(r) for r in _filter_meal(rows, meal)]
    warnings = [] if facts else ["no active mess menu found for today or the most recent matching weekday"]
    return RetrievalResult(plan=_plan(StructuredIntent.MESS_TODAY), facts=facts, warnings=warnings)


def mess_week(client: Any, meal: Optional[str] = None) -> RetrievalResult:
    all_rows = mess_all_active_rows(client)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    rows: list[dict] = []
    for i in range(7):
        rows.extend(mess_menu_for_day(all_rows, week_start + timedelta(days=i)))
    rows.sort(key=lambda r: (r["display_date"], r["meal"]))
    facts = [_mess_fact(r) for r in _filter_meal(split_mess_items(rows), meal)]
    warnings = [] if facts else ["no active mess menu found for this week or the most recent matching weekdays"]
    return RetrievalResult(plan=_plan(StructuredIntent.MESS_WEEK), facts=facts, warnings=warnings)


def _resolve_mess_target_date(day_ref: str) -> Optional[date]:
    ref = day_ref.strip().lower()
    today = date.today()
    if ref == "yesterday":
        return today - timedelta(days=1)
    if ref == "tomorrow":
        return today + timedelta(days=1)
    target_num = _WEEKDAY_TO_NUM.get(day_ref.strip().capitalize())
    if target_num is not None:
        offset = (target_num - today.isoweekday()) % 7
        return today + timedelta(days=offset)
    return None


def mess_on_day(client: Any, day_ref: str, meal: Optional[str] = None) -> RetrievalResult:
    """"Yesterday's dinner", "what's for lunch tomorrow", "mess menu on
    Monday" — resolves the actual referenced date (never silently falling
    back to today's menu, the bug found live: mess_today() always used
    date.today() regardless of what the query asked for) and reuses the
    same weekly-rotation fallback every other mess lookup uses."""
    target = _resolve_mess_target_date(day_ref)
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
