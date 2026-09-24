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

from . import retrieval
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


def academic_calendar(client: Any, query: str) -> RetrievalResult:
    """Best-matching calendar event (+ its Starts/Ends partner), or the next
    events for "what's coming up" / "upcoming deadlines" questions."""
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


# ------------------------------------------------------------ announcements

def announcements(client: Any) -> RetrievalResult:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = (
        client.table("announcements")
        .select("id,title,content,category,department,batch,target_role,created_at,published_at,valid_until")
        .eq("status", "active")
        .or_(f"valid_until.is.null,valid_until.gte.{now_iso}")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data
        or []
    )
    facts = [StructuredFact(claim=r["title"], data=r, source="announcements (approved)") for r in rows]
    return RetrievalResult(plan=_plan(StructuredIntent.ANNOUNCEMENTS), facts=facts,
                           warnings=[] if facts else ["no current approved announcements"])


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
}
_DEPT_ALIASES = [
    (r"\b(cse|computer\s+science)\b", ["Computer Science"]),
    (r"\b(ece|electronics|communication)\b", ["Electronics"]),
    (r"\b(cyber|security|csy)\b", ["Cyber"]),
    (r"\b(humanities|computational\s+science|maths?|mathematics)\b", ["Computational Science", "Humanities"]),
    (r"\bacademic", ["Academic"]),
    (r"\bhostel|student\s+events\b", ["Hostel"]),
    (r"\bstudents?\s+welfare|career\b", ["Students Welfare", "Career"]),
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
    for pattern, frags in _DEPT_ALIASES:
        if re.search(pattern, q):
            narrowed = [r for r in picked if any(f.lower() in r["designation"].lower() for f in frags)]
            if narrowed:
                picked = narrowed
                break
    facts = [StructuredFact(claim=f"{r['full_name']} — {r['designation']}", data=r, source="faculty directory (live)")
             for r in picked[:8]]
    return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_ROLE), facts=facts,
                           warnings=[] if facts else [f"no one with a '{role}' designation found in the faculty directory"])


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
            ct = set(cn.split())
            if n_tokens and ct:
                score = len(n_tokens & ct) / max(len(n_tokens), len(ct))
                if score > best_score:
                    best, best_score = c, score
        return best if best_score >= 0.6 else None
    return None


def link_entities(client: Any, query: str) -> dict[str, str]:
    """Course or faculty names mentioned without a code/title ("What is IT
    Workshop III?", "what does Manu Madhavan research")."""
    q = f" {_norm(query)} "
    found: dict[str, str] = {}
    for c in sorted(all_courses(client), key=lambda c: -len(c["course_name"])):
        cn = _norm(c["course_name"])
        if len(cn) > 5 and f" {cn} " in q:
            found["course_code"] = c["course_code"]
            break
    for f in all_faculty_names(client):
        name = _norm(re.sub(r"^(dr|prof|mr|ms|mrs)\.?\s+", "", f["full_name"], flags=re.I))
        parts = [p for p in name.split() if len(p) > 2]
        if len(parts) >= 2 and all(f" {p} " in q for p in parts[:2]):
            found["faculty_name"] = f["full_name"]
            break
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


def faculty_for_course(client: Any, course_code: Optional[str], course_name: Optional[str]) -> RetrievalResult:
    course = resolve_course(client, code=course_code, name=None if course_code else course_name)
    if not course:
        label = course_code or course_name or "that course"
        return RetrievalResult(plan=_plan(StructuredIntent.FACULTY_FOR_COURSE),
                               warnings=[f"couldn't find a course matching {label!r} in the catalog"])
    result = retrieval.faculty_for_course(client, course["course_code"])
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
