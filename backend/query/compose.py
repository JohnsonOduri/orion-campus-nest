"""Deterministic answer writer: GroundedContext -> Markdown reply.

ORION answers every question from retrieved data without needing an LLM
(CLAUDE.md §18 Phase 5: "for deterministic results, return structured
results directly instead of spending an LLM call"; §30: no LLM call when SQL
can answer). An LLM, when available, may only rephrase document passages —
see backend/app/api/ai.py.

Rules kept here:
- every sentence is built from a retrieved row or a verbatim document clause;
- every factual reply ends with a `*Source: ...*` line (the voice output
  skips that line — src/lib/ai/speech-text.ts);
- missing data is said plainly with where to look, never filled in.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from . import documents
from .types import GroundedContext, RouteType, StructuredIntent

_IST = timedelta(hours=5, minutes=30)
_DAYS = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
_MEAL_ORDER = {"breakfast": 0, "lunch": 1, "snacks": 2, "dinner": 3}
_ACRONYMS = {"IT", "AI", "ML", "DS", "DBMS", "OS", "CN", "VLSI", "IOT", "NLP", "CSE", "ECE", "II", "III", "IV",
             "VI", "VII", "VIII", "IX", "PT", "BTP", "MS", "UG", "PG", "HOD", "CAD", "DSP", "GPU", "API", "UI"}
_SMALL = {"and", "of", "the", "in", "for", "to", "with", "on", "a", "an", "or", "by", "&"}


def now_ist() -> datetime:
    return datetime.now(timezone.utc) + _IST


# ---------------------------------------------------------------- formatting

def nice_title(text: Optional[str]) -> str:
    if not text:
        return ""
    if text != text.upper():
        return text.strip()
    words = []
    for i, w in enumerate(text.strip().split()):
        core = w.strip("(),")
        if i > 0 and core.lower() in _SMALL:
            words.append(w.lower())
        elif core.upper() in _ACRONYMS or re.fullmatch(r"[A-Z]\.?", core) or (
                len(core) <= 3 and core.isalpha() and not re.search(r"[AEIOU]", core)) or (len(core) == 2 and core.isalpha()):
            words.append(w)
        else:
            lead = len(w) - len(w.lstrip("("))
            words.append(w[:lead] + w[lead:lead + 1].upper() + w[lead + 1:].lower())
    return " ".join(words)


def fmt_time(t: Optional[str]) -> str:
    if not t:
        return ""
    h, m = int(t[:2]), int(t[3:5])
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def fmt_range(start: Optional[str], end: Optional[str]) -> str:
    if not start:
        return ""
    s, e = fmt_time(start), fmt_time(end)
    if not e:
        return s
    if s[-2:] == e[-2:]:
        return f"{s[:-3]}–{e}"
    return f"{s} – {e}"


def fmt_date(d: str | date, with_weekday: bool = True) -> str:
    dt = date.fromisoformat(d) if isinstance(d, str) else d
    text = f"{dt.day} {dt.strftime('%B')}"
    if dt.year != now_ist().year:
        text += f" {dt.year}"
    return f"{dt.strftime('%A')}, {text}" if with_weekday else text


def relative_day(d: str | date) -> str:
    dt = date.fromisoformat(d) if isinstance(d, str) else d
    delta = (dt - now_ist().date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if delta > 1:
        return f"in {delta} days"
    return f"{-delta} days ago"


def person(name: str) -> str:
    return re.sub(r"\b(Dr|Prof|Mr|Ms|Mrs)\.(?=[A-Za-z])", r"\1. ", name.strip())


def join_names(names: Iterable[str]) -> str:
    items = [person(n) for n in dict.fromkeys(n for n in names if n)]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def source_line(*sources: Optional[str]) -> str:
    unique = [s for s in dict.fromkeys(s for s in sources if s)]
    return f"\n\n*Source: {'; '.join(unique)}*" if unique else ""


def entry_label(e: dict) -> str:
    if e.get("course_code"):
        return f"{nice_title(e.get('course_name'))} ({e['course_code']})".strip()
    if e.get("source_text"):
        st = e["source_text"].strip()
        return st if len(st) <= 4 else nice_title(st)
    return (e.get("entry_type") or "Class").replace("_", " ").title()


def entry_extras(e: dict, with_faculty: bool = True) -> str:
    bits = []
    if with_faculty and e.get("faculty_names"):
        bits.append(join_names(e["faculty_names"]))
    etype = e.get("entry_type")
    if etype and etype not in {"class", "other"}:
        bits.append(etype.replace("_", " ") + (f", batch {e['lab_batch']}" if e.get("lab_batch") else ""))
    if e.get("room"):
        bits.append(f"room {e['room']}")
    return f" — {' · '.join(bits)}" if bits else ""


# ---------------------------------------------------------------- timetable

def _merge_slots(entries: list[dict]) -> list[dict]:
    """Lab batches share a slot as separate rows — show one line per slot."""
    merged: dict[tuple, dict] = {}
    for e in sorted(entries, key=lambda e: (e.get("day_of_week") or 0, e.get("start_time") or "")):
        key = (e.get("day_of_week"), e.get("start_time"), e.get("end_time"), e.get("course_code") or e.get("source_text"), e.get("entry_type"))
        if key in merged:
            m = merged[key]
            m["faculty_names"] = list(dict.fromkeys((m.get("faculty_names") or []) + (e.get("faculty_names") or [])))
            if e.get("lab_batch") and m.get("lab_batch") and e["lab_batch"] not in m["lab_batch"]:
                m["lab_batch"] = f"{m['lab_batch']}/{e['lab_batch']}"
        else:
            merged[key] = dict(e)
    return list(merged.values())


def _entry_line(e: dict, today: bool = False) -> str:
    status = ""
    if today:
        now = now_ist().strftime("%H:%M:%S")
        if (e.get("end_time") or "") <= now:
            status = " *(done)*"
        elif (e.get("start_time") or "") <= now:
            status = " *(now)*"
    return f"- **{fmt_range(e.get('start_time'), e.get('end_time'))}** · {entry_label(e)}{entry_extras(e)}{status}"


def _day_phrase(day_ref: Optional[str], on: Optional[str]) -> str:
    if not day_ref or day_ref == "today":
        return "today"
    if day_ref in {"tomorrow", "yesterday"}:
        return day_ref
    return f"on {day_ref}" + (f" ({fmt_date(on, with_weekday=False)})" if on else "")


def compose_day(ctx: GroundedContext, day_ref: Optional[str]) -> str:
    entries = _merge_slots([f.data for f in ctx.facts if f.data.get("start_time")])
    hints = ctx.plan.hints if ctx.plan else {}
    on_date = None
    m = re.search(r"\((?:\w+ )?(\d{4}-\d{2}-\d{2})\)", ctx.facts[0].claim) if ctx.facts else None
    if m:
        on_date = m.group(1)
    phrase = _day_phrase(day_ref, on_date)
    is_today = phrase == "today"
    if hints.get("entry_type") == "lab":
        entries = [e for e in entries if e.get("entry_type") == "lab"]
    if not entries:
        if hints.get("entry_type") == "lab":
            return f"You have no labs {phrase}."
        weekend = day_ref in {"Sunday", "Saturday"}
        return f"You have no classes {phrase}." + (" Enjoy the weekend!" if weekend and day_ref == "Sunday" else "")
    src = source_line("your live timetable")
    focus = hints.get("focus")
    if focus == "first":
        e = entries[0]
        return f"Your first class {phrase} is **{entry_label(e)}** at {fmt_time(e['start_time'])} ({fmt_range(e['start_time'], e['end_time'])}){entry_extras(e)}.{src}"
    if focus == "last":
        e = entries[-1]
        return f"Your last class {phrase} is **{entry_label(e)}**, which ends at **{fmt_time(e['end_time'])}**{entry_extras(e)}.{src}"
    n = len(entries)
    head = (f"You have **{n} {'class' if n == 1 else 'classes'}** {phrase}:" if focus == "count"
            else f"Here's your timetable {phrase}:")
    lines = "\n".join(_entry_line(e, today=is_today) for e in entries)
    return f"{head}\n\n{lines}{src}"


def compose_week(ctx: GroundedContext) -> str:
    entries = _merge_slots([f.data for f in ctx.facts if f.data.get("start_time")])
    hints = ctx.plan.hints if ctx.plan else {}
    head = "Here's your timetable for this week:"
    if hints.get("entry_type") == "lab":
        entries = [e for e in entries if e.get("entry_type") == "lab"]
        head = "Your labs this week:"
        if not entries:
            return "You have no labs scheduled this week."
    wanted = hints.get("course_filter")
    if wanted:
        w_tokens = {t for t in re.findall(r"[a-z0-9]+", wanted.lower()) if t not in {"my", "the", "class", "lab"}}
        matched = [e for e in entries if w_tokens and w_tokens <= set(re.findall(r"[a-z0-9]+", f"{e.get('course_name','')} {e.get('course_code','')}".lower()))]
        if not matched:
            return f"I couldn't find a class matching **{wanted}** in your timetable this week."
        entries = matched
        head = f"Your **{entry_label(matched[0])}** sessions this week:"
    if not entries:
        return "I couldn't find any classes in your timetable this week."
    by_day: dict[int, list[dict]] = {}
    for e in entries:
        by_day.setdefault(e.get("day_of_week") or 0, []).append(e)
    parts = [head]
    for day in sorted(by_day):
        parts.append(f"\n**{_DAYS.get(day, f'Day {day}')}**")
        parts.extend(_entry_line(e) for e in by_day[day])
    return "\n".join(parts) + source_line("your live timetable")


def compose_next(ctx: GroundedContext, at_label: Optional[str] = None) -> str:
    fact = next((f for f in ctx.facts if f.data.get("_role")), None)
    if not fact:
        return "I couldn't find any upcoming classes in your timetable."
    d = fact.data
    src = source_line("your live timetable")
    if d["_role"] == "ongoing":
        lead = (f"At {at_label} you have **{entry_label(d)}** ({fmt_range(d['start_time'], d['end_time'])}){entry_extras(d)}."
                if at_label else
                f"You're in **{entry_label(d)}** right now ({fmt_range(d['start_time'], d['end_time'])}){entry_extras(d)}.")
        f = d.get("_followup")
        if f:
            lead += f" After that, your next class is **{entry_label(f)}** {f['_when']}, {fmt_range(f['start_time'], f['end_time'])}{entry_extras(f)}."
        else:
            lead += " That's your last class for today."
        return lead + src
    when = d.get("_when") or ""
    if not at_label and re.search(r"\bwho\s+(teaches|takes|is\s+teaching)\b", ctx.query, re.I) and d.get("faculty_names"):
        return (f"{join_names(d['faculty_names'])} {'teaches' if len(d['faculty_names']) == 1 else 'teach'} your next class, "
                f"**{entry_label(d)}** — {when}, {fmt_range(d['start_time'], d['end_time'])}." + src)
    if at_label:
        prefix = f"You don't have a class at {at_label}. The next one after that is"
    elif re.search(r"\b(right\s+now|now|currently|going\s+on)\b", ctx.query, re.I):
        prefix = "You don't have a class right now. Your next class is"
    else:
        prefix = "Your next class is"
    text = f"{prefix} **{entry_label(d)}** — {when}, {fmt_range(d['start_time'], d['end_time'])}{entry_extras(d)}."
    if d.get("_gap") and "no more classes today" in d["_gap"]:
        text += " You have no more classes today."
    elif d.get("_gap"):
        text += f" Nothing else is scheduled before then ({d['_gap'].split('— ')[-1]})."
    return text + src


def compose_free(ctx: GroundedContext, day_ref: str) -> str:
    facts = [f.data for f in ctx.facts]
    if facts and facts[0].get("_empty"):
        return f"You have no classes {_day_phrase(day_ref, None)}, so you're free all day."
    entries = _merge_slots([e for e in facts if e.get("start_time")])
    phrase = _day_phrase(day_ref, None)
    gaps: list[str] = []
    first = entries[0]
    if first["start_time"] > "09:00:00":
        gaps.append(f"before {fmt_time(first['start_time'])}")
    for a, b in zip(entries, entries[1:]):
        if b["start_time"] > a["end_time"]:
            start, end = datetime.strptime(a["end_time"], "%H:%M:%S"), datetime.strptime(b["start_time"], "%H:%M:%S")
            if (end - start).total_seconds() >= 30 * 60:
                gaps.append(fmt_range(a["end_time"], b["start_time"]))
    gaps.append(f"after {fmt_time(max(e['end_time'] for e in entries))}")
    busy = "; ".join(f"{fmt_range(e['start_time'], e['end_time'])} {entry_label(e)}" for e in entries)
    return (f"You're free {phrase} {join_names(gaps)}.\n\nYour classes {phrase}: {busy}."
            + source_line("your live timetable"))


# ---------------------------------------------------------------- courses & faculty

def compose_course(ctx: GroundedContext) -> str:
    d = ctx.facts[0].data
    name, code = nice_title(d.get("course_name")), d.get("course_code")
    bits = [f"**{name}** ({code}) is a"]
    if d.get("semester"):
        bits.append(f"semester {d['semester']}")
    bits.append(f"{d.get('programme') or 'B.Tech'} course.")
    text = " ".join(bits)
    sources = ["course catalog"]
    cur = d.get("curriculum")
    if d.get("credits") is not None:
        text += f" It carries **{d['credits']} credits**."
    elif cur:
        text += (f" It carries **{cur['credits']} credits** (lecture-tutorial-practical: "
                 f"{cur['lecture']}-{cur['tutorial']}-{cur['practical']}).")
        sources.append(cur["document_title"] + (f", p. {cur['page']}" if cur.get("page") else ""))
    if d.get("prerequisites"):
        text += f"\n\n**Prerequisites:** {d['prerequisites']}"
    if d.get("syllabus_summary"):
        text += f"\n\n**Syllabus:** {d['syllabus_summary']}"
    teachers = d.get("teachers") or []
    if teachers:
        text += f"\n\nTaught by {join_names(teachers)}."
    if not d.get("syllabus_summary"):
        text += "\n\nA syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document."
    return text + source_line(*sources)


def compose_course_faculty(ctx: GroundedContext) -> str:
    facts = ctx.facts
    course = facts[0].data.get("course") or {}
    label = f"**{nice_title(course.get('course_name'))}** ({course.get('course_code')})"
    if facts[0].data.get("_no_faculty"):
        return f"{label} is in the course catalog, but no teacher is linked to it in the current timetable."
    people = [f.data for f in facts if f.data.get("full_name")]
    names = [p["full_name"] for p in people]
    text = f"{label} is taught by {join_names(names)}."
    if len(names) > 1:
        text += " Different sections may have different teachers."
    contacts = [f"- {p['full_name']} — {p['email']}" for p in people if p.get("email")]
    if contacts:
        text += "\n\n" + "\n".join(contacts)
    return text + source_line("your live timetable", "faculty directory")


_ATTR_EMAIL = re.compile(r"\b(e-?mail|mail\s+id)\b", re.I)
_ATTR_OFFICE = re.compile(r"\b(office|cabin|room|where\s+(is|can\s+i\s+find|do\s+i\s+find))\b", re.I)
_ATTR_RESEARCH = re.compile(r"\b(research|work(s|ing)?\s+on|interests?|specializ|expert)\w*", re.I)


def _slots_text(slots: list[dict]) -> str:
    if not slots:
        return ""
    lines = []
    for s in slots[:10]:
        lines.append(f"- {_DAYS.get(s['day_of_week'], '')} {fmt_range(s['start_time'], s['end_time'])}"
                     + (f" ({s['course_code']})" if s.get("course_code") else ""))
    return "\n".join(lines)


def compose_faculty(ctx: GroundedContext) -> str:
    people = [f.data for f in ctx.facts]
    q = ctx.query
    hints = ctx.plan.hints if ctx.plan else {}
    if len(people) > 1 and not any(p["full_name"].lower() == (ctx.plan.topic_text or "").lower() for p in people):
        return ("I found more than one match — which one did you mean?\n\n"
                + "\n".join(f"- **{p['full_name']}**" + (f" — {p['email']}" if p.get("email") else "") for p in people)
                + source_line("faculty directory"))
    p = people[0]
    name = p["full_name"]
    src = source_line("faculty directory")
    if hints.get("focus") == "meet":
        slots = p.get("teaching_slots") or []
        text = f"ORION doesn't have office hours on file for **{name}**, so I can't confirm when they're free."
        if slots:
            text += f" They teach at these times, so they'll be busy then:\n\n{_slots_text(slots)}"
        if p.get("email"):
            text += f"\n\nThe reliable way is to email them to set a time: **{p['email']}**"
        if p.get("office_location"):
            text += f" (office: {p['office_location']})."
        return text + source_line("faculty directory", "your live timetable" if slots else None)
    if _ATTR_EMAIL.search(q):
        return (f"{name}'s email is **{p['email']}**." if p.get("email")
                else f"I don't have an email address on file for {name}.") + src
    if _ATTR_OFFICE.search(q) and not _ATTR_RESEARCH.search(q):
        return (f"{name}'s office is **{p['office_location']}**." if p.get("office_location")
                else f"I don't have an office location on file for {name}.") + (
                    f" Email: {p['email']}." if p.get("email") else "") + src
    if _ATTR_RESEARCH.search(q):
        return (f"{name}'s research interests: {p['research_interests']}." if p.get("research_interests")
                else f"I don't have research interests on file for {name}.") + src
    lines = [f"**{name}**" + (f" ({p['initials']})" if p.get("initials") else "")]
    if p.get("designation"):
        lines.append(f"- {p['designation']}")
    if p.get("email"):
        lines.append(f"- Email: {p['email']}")
    if p.get("office_location"):
        lines.append(f"- Office: {p['office_location']}")
    if p.get("office_hours"):
        lines.append(f"- Office hours: {p['office_hours']}")
    if p.get("research_interests"):
        lines.append(f"- Research: {p['research_interests']}")
    return "\n".join(lines) + src


def compose_research(ctx: GroundedContext) -> str:
    topic = (ctx.plan.topic_text if ctx.plan else "") or "that topic"
    meet = (ctx.plan.hints if ctx.plan else {}).get("meet")
    if not ctx.facts:
        return (f"I couldn't find any faculty who list **{topic}** in their research interests. "
                "Research profiles aren't on file for every faculty member, so the department pages may still help.")
    total = ctx.facts[0].data.get("total_matches", len(ctx.facts))
    shown = len(ctx.facts)
    parts = [f"{total} faculty list **{topic}** among their research interests"
             + (f" — here are the {shown} for whom it's most central:" if total > shown else ":")]
    for f in ctx.facts:
        fac = f.data["faculty"]
        line = f"\n**{fac['full_name']}**"
        details = []
        if fac.get("designation"):
            details.append(fac["designation"])
        if fac.get("email"):
            details.append(fac["email"])
        if fac.get("office_location"):
            details.append(f"office {fac['office_location']}")
        if details:
            line += " — " + " · ".join(details)
        parts.append(line)
        if fac.get("research_interests"):
            parts.append(f"- Research: {fac['research_interests']}")
        if meet:
            slots = f.data.get("teaching_slots") or []
            if slots:
                days = sorted({(s["day_of_week"], fmt_range(s["start_time"], s["end_time"])) for s in slots})
                parts.append("- Teaching (busy): " + "; ".join(f"{_DAYS.get(d, '')[:3]} {r}" for d, r in days[:6]))
    if meet:
        parts.append("\nNone of them have office hours on file, so I can't confirm when they're free. "
                     "Their teaching slots above are when they're busy — email is the best way to set up a meeting.")
    return "\n".join(parts) + source_line("faculty directory", "your live timetable" if meet else None)


def compose_roles(ctx: GroundedContext) -> str:
    role = (ctx.plan.hints or {}).get("role", "") if ctx.plan else ""
    if not ctx.facts:
        return f"I couldn't find anyone with that role in the faculty directory."
    people = [f.data for f in ctx.facts]
    if role == "psychologist":
        lead = "Yes — the institute has a psychologist you can reach out to:"
    elif role in {"medical", "nurse"}:
        lead = "Yes — here's the campus medical contact:" if len(people) == 1 else "Here are the campus medical contacts:"
    else:
        lead = "Here's who holds that role:" if len(people) > 1 else ""
    lines = []
    for p in people:
        bits = [p["designation"]]
        if p.get("email"):
            bits.append(p["email"])
        if p.get("phone"):
            bits.append(p["phone"])
        if p.get("office_location"):
            bits.append(f"office {p['office_location']}")
        lines.append(f"- **{p['full_name']}** — " + " · ".join(bits))
    if len(people) == 1 and not lead:
        p = people[0]
        text = f"**{p['full_name']}** is the {p['designation']}."
        extra = [x for x in (p.get("email"), p.get("phone"), f"office {p['office_location']}" if p.get("office_location") else None) if x]
        if extra:
            text += " Contact: " + " · ".join(extra) + "."
        return text + source_line("faculty directory")
    return f"{lead}\n\n" + "\n".join(lines) + source_line("faculty directory")


# ---------------------------------------------------------------- mess

def compose_mess(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts if f.data.get("meal")]
    meal = ctx.plan.meal if ctx.plan else None
    if not rows:
        return "There's no mess menu on file for that day." + (f" (asked about {meal})" if meal else "")
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        by_date.setdefault(r["display_date"], []).append(r)
    parts = []
    stale_dates = sorted({r["source_date"] for r in rows if not r.get("is_actual")})
    for d in sorted(by_date):
        day_rows = sorted(by_date[d], key=lambda r: _MEAL_ORDER.get(r["meal"], 9))
        header = f"**{fmt_date(d)}**" + (f" ({relative_day(d)})" if relative_day(d) in {"today", "tomorrow", "yesterday"} else "")
        if len(by_date) == 1 and len(day_rows) == 1:
            r = day_rows[0]
            parts.append(f"{r['meal'].capitalize()} on {header}: {', '.join(r['items']) or 'no items listed'}.")
            continue
        parts.append(header)
        for r in day_rows:
            parts.append(f"- **{r['meal'].capitalize()}:** {', '.join(r['items']) or 'no items listed'}")
        parts.append("")
    text = "\n".join(parts).strip()
    if stale_dates:
        text += ("\n\nNote: a menu hasn't been published for these dates yet, so this is the regular weekly "
                 f"menu from the most recent week on file ({', '.join(fmt_date(s, False) for s in stale_dates[:2])}"
                 f"{'…' if len(stale_dates) > 2 else ''}). It may change.")
    return text + source_line("mess menu")


# ---------------------------------------------------------------- calendar / exams

_EVENT_DISPLAY = {
    "class ends": "Last instructional day (classes end)",
    "end semester exam ends & semester ends": "End semester exams end and the semester ends",
}


def event_name(e: dict) -> str:
    return _EVENT_DISPLAY.get(e["event_name"].strip().lower(), e["event_name"])


def _event_line(e: dict) -> str:
    rel = relative_day(e["event_date"])
    past = date.fromisoformat(e["event_date"]) < now_ist().date()
    return f"- **{fmt_date(e['event_date'])}** — {event_name(e)} · {'already passed' if past else rel}"


def compose_calendar(ctx: GroundedContext) -> str:
    events = [f.data for f in ctx.facts]
    src = source_line("academic calendar, Odd semester 2026-27")
    today = now_ist().date()
    holiday_q = any(e.get("_holiday_query") for e in events) or re.search(r"holiday|vacation", ctx.query, re.I)
    if holiday_q and not any(e.get("event_type") in {"holiday", "vacation"} for e in events):
        text = "The academic calendar in ORION doesn't list any holidays for this semester."
        upcoming = [e for e in events if date.fromisoformat(e["event_date"]) >= today][:3]
        if upcoming:
            text += " Coming up next:\n\n" + "\n".join(_event_line(e) for e in upcoming)
        return text + src
    if not events:
        return "I couldn't find that on the academic calendar."
    if events[0].get("_mode") == "upcoming":
        head = ("Here are the upcoming deadlines:" if re.search(r"deadline", ctx.query, re.I)
                else "Coming up on the academic calendar:")
        return head + "\n\n" + "\n".join(_event_line(e) for e in events) + src

    starts = next((e for e in events if re.search(r"\b(starts?|begins?)\s*$", e["event_name"], re.I)), None)
    ends = next((e for e in events if e is not starts and re.search(r"\bends?\s*$", e["event_name"], re.I)), None)
    asks_end = any(e.get("_asks_end") for e in events)
    if starts and ends:
        name = re.sub(r"\s+(starts?|begins?)\s*$", "", starts["event_name"], flags=re.I)
        s_d, e_d = date.fromisoformat(starts["event_date"]), date.fromisoformat(ends["event_date"])
        if asks_end:
            lead = (f"**{event_name(ends)}** {'was' if e_d < today else 'is'} on **{fmt_date(e_d)}** "
                    f"({relative_day(e_d) if e_d >= today else 'already passed'}).")
            return lead + f" The {name} starts on {fmt_date(s_d)}." + src
        if e_d < today:
            return f"The **{name}** ran from {fmt_date(s_d)} to {fmt_date(e_d)} — it's already over." + src
        if s_d < today:
            return f"The **{name}** started on {fmt_date(s_d)} and runs until **{fmt_date(e_d)}** ({relative_day(e_d)})." + src
        return (f"The **{name}** runs from **{fmt_date(s_d)}** to **{fmt_date(e_d)}** — it starts {relative_day(s_d)}." + src)

    same = [e for e in events if e["event_name"] == events[0]["event_name"]]
    e = events[0]
    d = date.fromisoformat(e["event_date"])
    if len(same) > 1:
        dates = " and ".join(fmt_date(x["event_date"]) for x in same)
        return f"**{event_name(e)}** is on {dates} ({relative_day(same[0]['event_date'])})." + src
    if d < today:
        return (f"**{event_name(e)}** was on **{fmt_date(d)}** — that was {relative_day(d)}, so it has already passed." + src)
    return f"**{event_name(e)}** is on **{fmt_date(d)}** ({relative_day(d)})." + src


def compose_exam(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts if not f.data.get("_window")]
    window = [f.data for f in ctx.facts if f.data.get("_window")]
    course = (ctx.facts[0].data.get("course") if ctx.facts else None) or {}
    label = f"**{nice_title(course.get('course_name'))}** ({course.get('course_code')})" if course else "that course"
    src = source_line("exams" if rows else None, "academic calendar, Odd semester 2026-27")
    if rows:
        lines = [f"- **{fmt_date(r['exam_date'])}** — {r['exam_type']}"
                 + (f", {fmt_range(r.get('start_time'), r.get('end_time'))}" if r.get("start_time") else "") for r in rows]
        return f"Exams for {label}:\n\n" + "\n".join(lines) + src
    today = now_ist().date()
    end_start = next((e for e in window if re.search(r"end semester examination starts", e["event_name"], re.I)), None)
    end_end = next((e for e in window if re.search(r"end semester exam ends", e["event_name"], re.I)), None)
    text = f"The exam timetable for {label} hasn't been published in ORION yet."
    if end_start and date.fromisoformat(end_start["event_date"]) >= today:
        text += (f" From the academic calendar, the end semester exams run from **{fmt_date(end_start['event_date'])}**"
                 + (f" to **{fmt_date(end_end['event_date'])}**" if end_end else "") + ", so it will fall in that window.")
    upcoming = [e for e in window if date.fromisoformat(e["event_date"]) >= today and e is not end_start and e is not end_end][:2]
    if upcoming:
        text += "\n\nOther exam dates:\n\n" + "\n".join(_event_line(e) for e in upcoming)
    return text + src


# ---------------------------------------------------------------- misc structured

def compose_announcements(ctx: GroundedContext) -> str:
    if not ctx.facts:
        return "There are no current announcements right now. New ones show up here once an admin approves them."
    parts = ["Here are the current announcements:"]
    for f in ctx.facts:
        a = f.data
        when = (a.get("published_at") or a.get("created_at") or "")[:10]
        body = (a.get("content") or "").strip()
        if len(body) > 220:
            body = body[:220].rsplit(" ", 1)[0] + "…"
        parts.append(f"\n**{a['title']}**" + (f" · {fmt_date(when, False)}" if when else ""))
        if body:
            parts.append(body)
    return "\n".join(parts) + source_line("announcements (approved)")


_WARDEN_ROLE = {"hostel_warden": "Warden", "assistant_warden": "Assistant warden", "standby_warden": "Standby warden",
                "chief_warden": "Chief Warden", "hostel_manager": "Hostel Manager", "security_officer": "Security Officer",
                "associate_dean_hostel_affairs_and_student_events": "Associate Dean (Hostel Affairs & Student Events)"}


def _contact(r: dict) -> str:
    bits = [x for x in (r.get("phone"), r.get("email")) if x]
    return f" · {' · '.join(bits)}" if bits else ""


def compose_wardens(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts]
    if not rows:
        return "I couldn't find warden details for that hostel."
    mode = rows[0].get("_mode")
    src = source_line("Wardens Team, July 2026")
    if mode == "hall":
        parts = []
        for hall in dict.fromkeys(r["hall_name"] for r in rows):
            parts.append(f"**{nice_title(hall)}**")
            for r in (x for x in rows if x["hall_name"] == hall):
                parts.append(f"- {_WARDEN_ROLE.get(r['role'], r['role'])}: **{r['full_name']}**{_contact(r)}")
            parts.append("")
        return "\n".join(parts).strip() + src
    if mode == "general":
        return "\n".join(f"The {_WARDEN_ROLE.get(r['role'], r['role'])} is **{r['full_name']}**{_contact(r)}." for r in rows) + src
    halls = [r for r in rows if r.get("hall_name")]
    general = [r for r in rows if not r.get("hall_name")]
    parts = ["Which hostel are you in? Here are the wardens for each hall:\n"]
    parts += [f"- **{nice_title(r['hall_name'])}** — {r['full_name']}{_contact(r)}" for r in halls]
    if general:
        parts.append("\nInstitute-wide:\n")
        parts += [f"- {_WARDEN_ROLE.get(r['role'], r['role'])}: **{r['full_name']}**{_contact(r)}" for r in general]
    parts.append("\nAsk me about a specific hostel (e.g. \"wardens of Sahyadri hostel\") for its assistant wardens too.")
    return "\n".join(parts) + src


def compose_my_courses(ctx: GroundedContext) -> str:
    if not ctx.facts:
        return "I couldn't find any courses in your timetable."
    parts = [f"You have **{len(ctx.facts)} courses** this semester:\n"]
    for f in ctx.facts:
        c = f.data
        kinds = [t for t in c.get("types", []) if t not in {"class"}]
        line = f"- **{nice_title(c['course_name'])}** ({c['course_code']})"
        if c.get("faculty"):
            line += f" — {join_names(c['faculty'])}"
        if kinds:
            line += f" *({', '.join(kinds)})*"
        parts.append(line)
    return "\n".join(parts) + source_line("your live timetable")


def compose_profile(ctx: GroundedContext) -> str:
    if not ctx.facts:
        return "I don't have a student profile for your account yet. Complete registration so I can personalise answers."
    p = ctx.facts[0].data
    q = ctx.query.lower()
    dept = nice_title(p.get("department"))
    if "regulation" in q or "cohort" in q:
        reg = p.get("regulations")
        return ((f"The **{reg}** apply to you." if reg else "I can't tell which regulations apply to you from your profile.")
                + source_line("your profile"))
    if "section" in q or "batch" in q:
        return f"You're in section **{p.get('section')}**." + source_line("your profile")
    if "semester" in q or "year" in q:
        return f"You're in **semester {p.get('semester')}**." + source_line("your profile")
    if "department" in q or "branch" in q:
        return f"Your department is **{dept}**." + source_line("your profile")
    lines = [f"- Semester **{p.get('semester')}**, section **{p.get('section')}**",
             f"- {p.get('programme')} · {dept}"]
    if p.get("regulations"):
        lines.append(f"- Regulations: {p['regulations']}")
    return "Here's what I have for you:\n\n" + "\n".join(lines) + source_line("your profile")


def compose_classroom(ctx: GroundedContext) -> str:
    room = next((f.data for f in ctx.facts if f.data.get("_classroom")), None)
    nxt = next((f.data for f in ctx.facts if f.data.get("_role")), None)
    parts = []
    target = (nxt.get("_followup") if nxt and nxt.get("_role") == "ongoing" and nxt.get("_followup") else nxt)
    if target and target.get("room"):
        parts.append(f"Your next class, **{entry_label(target)}**, is in **{target['room']}**.")
    elif room:
        parts.append(f"Your section's classroom this semester is **{room['room_no']}**.")
        if target:
            parts.append(f"Your next class is **{entry_label(target)}** — {target.get('_when')}, "
                         f"{fmt_range(target['start_time'], target['end_time'])}.")
            if target.get("entry_type") == "lab":
                parts.append("It's a lab, so it will be in the lab rather than the classroom.")
        parts.append("(The timetable doesn't list a room for each class, so this is your section's allocated room.)")
    else:
        parts.append("The timetable doesn't list rooms, and I couldn't find a classroom allocation for your section.")
    return " ".join(parts) + source_line("classroom allocation, Odd semester 2026" if room else None, "your live timetable" if nxt else None)


# ---------------------------------------------------------------- documents

def _cohort_label(title: str, family: Optional[str], document_type: Optional[str] = None) -> str:
    if family and document_type == "regulations":
        return f"Under the **{title}**, which apply to you"
    if document_type == "regulations":
        return f"Under the **{title}**"
    return f"From the **{title}**"


def _citation(p: documents.Passage) -> str:
    sec = p.section_title or ""
    if not (re.match(r"^(R\.)?\d", sec) or (sec and len(sec) < 60 and not sec.isupper())):
        sec = ""
    if re.match(r"^\d", sec):
        sec = f"rule {sec}"
    return ", ".join(x for x in (p.document_title, sec, f"p. {p.page}" if p.page else None) if x)


def compose_documents(ctx: GroundedContext, cohort_family: Optional[str]) -> tuple[str, float, list[documents.Passage]]:
    passages, confidence = documents.best_passages(ctx.query, ctx.snippets)
    if not passages:
        return (_no_document_answer(ctx), 0.0, [])
    p = passages[0]
    source = _citation(p)
    quote = "\n>\n".join(f"> {line}" for line in _quote_lines(p.text))
    if confidence < 0.34:
        text = ("I couldn't find a rule that answers that directly. The closest thing in the documents I have is "
                f"this, from the **{p.document_title}**:\n\n{quote}\n\nIf that's not it, the Academic Office can help.")
        return text + source_line(source), confidence, passages
    return f"{_cohort_label(p.document_title, cohort_family, p.document_type)}:\n\n{quote}" + source_line(source), confidence, passages


def compose_overview(ctx: GroundedContext) -> str:
    topic = (ctx.plan.hints or {}).get("overview", "")
    if not ctx.facts:
        return _no_document_answer(ctx)
    head = {"hostel": "Here are the hostel rules students ask about most:",
            "anti-ragging": "Here are the key anti-ragging rules:"}.get(topic, "Here are the key rules:")
    parts = [head]
    sources = []
    for f in ctx.facts:
        p = f.data["passage"]
        parts.append(f"\n**{f.data['label']}** — {p.text}")
        sources.append(_citation(p))
    parts.append("\nAsk me about any one of these for the full rule.")
    return "\n".join(parts) + source_line(*sources)


def _quote_lines(text: str) -> list[str]:
    # One clause per line so numbered rules stay readable.
    parts = re.split(r"\s(?=(?:R\.)?\d{1,2}(?:\.\d{1,2})+\s+[A-Z])|\s•\s", text)
    return [p.strip() for p in parts if p.strip()]


def _no_document_answer(ctx: GroundedContext) -> str:
    return ("I couldn't find anything about that in ORION's campus documents (UG regulations, curricula, hostel rules, "
            "anti-ragging documents and verification procedures), so I won't guess. The Academic Office or your "
            "faculty advisor can confirm.")


# ---------------------------------------------------------------- out of scope

_OUT_OF_SCOPE = {
    "grades": ("I can't see grades, marks or CGPA — ORION doesn't store personal academic records. Your results are on "
               "the institute's academic portal, or ask your faculty advisor. I can explain how CGPA is calculated or "
               "tell you when results are published."),
    "attendance": ("ORION doesn't track your attendance — your course faculty maintain it, and you can check it with them. "
                   "I can tell you the attendance rules if that helps (\"What is the attendance requirement?\")."),
    "fees": ("ORION doesn't handle fee payments or balances — use the institute's official payment channels or the "
             "Accounts section. I can tell you fee payment deadlines from the academic calendar."),
    "general": ("I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, "
                "faculty, the mess menu, exams and deadlines, hostel rules and academic regulations."),
}

_UNSUPPORTED = ("I'm not sure what you mean. You can ask me things like:\n\n"
                "- What is my next class?\n- What's for lunch today?\n- When do the end semester exams start?\n"
                "- What is the attendance requirement?\n- Who is the warden of Sahyadri hostel?")


# ---------------------------------------------------------------- dispatch

def compose(ctx: GroundedContext, cohort_family: Optional[str] = None) -> str:
    intent = ctx.intent
    plan = ctx.plan
    if ctx.route == RouteType.SMALL_TALK:
        return ctx.facts[0].claim if ctx.facts else "Hi! How can I help?"
    if intent == StructuredIntent.OUT_OF_SCOPE:
        return _OUT_OF_SCOPE.get((plan.hints or {}).get("kind", "general"), _OUT_OF_SCOPE["general"])
    if ctx.route == RouteType.UNSUPPORTED:
        return _UNSUPPORTED
    if ctx.route == RouteType.SEMANTIC and (plan.hints or {}).get("overview"):
        return compose_overview(ctx)
    if ctx.route == RouteType.SEMANTIC:
        return compose_documents(ctx, cohort_family)[0]

    if not ctx.facts and intent in {StructuredIntent.COURSE_INFO, StructuredIntent.FACULTY_FOR_COURSE,
                                    StructuredIntent.FACULTY_LOOKUP, StructuredIntent.FACULTY_ROLE,
                                    StructuredIntent.MY_COURSES, StructuredIntent.EXAM_SCHEDULE}:
        return _no_structured_answer(ctx)

    if intent in {StructuredIntent.NEXT_CLASS}:
        return compose_next(ctx)
    if intent == StructuredIntent.CLASS_AT_TIME:
        return compose_next(ctx, at_label=fmt_time(_time_24(plan.topic_text)) if plan and plan.topic_text else None)
    if intent == StructuredIntent.DAY_TIMETABLE:
        return compose_day(ctx, "today")
    if intent == StructuredIntent.DAY_OF_WEEK_TIMETABLE:
        return compose_day(ctx, plan.topic_text if plan else None)
    if intent == StructuredIntent.WEEK_TIMETABLE:
        return compose_week(ctx)
    if intent == StructuredIntent.FREE_TIME:
        return compose_free(ctx, (plan.topic_text if plan else None) or "today")
    if intent == StructuredIntent.COURSE_INFO:
        return compose_course(ctx)
    if intent == StructuredIntent.FACULTY_FOR_COURSE:
        return compose_course_faculty(ctx)
    if intent == StructuredIntent.FACULTY_LOOKUP:
        return compose_faculty(ctx)
    if intent == StructuredIntent.FACULTY_RESEARCH:
        return compose_research(ctx)
    if intent == StructuredIntent.FACULTY_ROLE:
        return compose_roles(ctx)
    if intent in {StructuredIntent.MESS_TODAY, StructuredIntent.MESS_WEEK, StructuredIntent.MESS_ON_DAY}:
        return compose_mess(ctx)
    if intent == StructuredIntent.ACADEMIC_CALENDAR:
        return compose_calendar(ctx)
    if intent == StructuredIntent.EXAM_SCHEDULE:
        return compose_exam(ctx)
    if intent == StructuredIntent.ANNOUNCEMENTS:
        return compose_announcements(ctx)
    if intent == StructuredIntent.HOSTEL_WARDENS:
        return compose_wardens(ctx)
    if intent == StructuredIntent.MY_COURSES:
        return compose_my_courses(ctx)
    if intent == StructuredIntent.MY_PROFILE:
        return compose_profile(ctx)
    if intent == StructuredIntent.CLASSROOM:
        return compose_classroom(ctx)
    return _no_structured_answer(ctx)


def _time_24(text: str) -> str:
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", text, re.I)
    if not m:
        return "00:00:00"
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}:00"


def _no_structured_answer(ctx: GroundedContext) -> str:
    warning = ctx.warnings[0] if ctx.warnings else ""
    if "course code" in warning or "couldn't find a course" in warning:
        return "I couldn't find that course in the catalog. Check the course code (for example ICS 211)."
    if "no faculty found" in warning:
        return "I couldn't find a faculty member with that name. Try their full name, e.g. \"Tell me about Dr. Manu Madhavan\"."
    if "no upcoming class" in warning:
        return "I couldn't find any upcoming classes in your timetable."
    if "profile" in warning:
        return "I don't have a student profile for your account yet. Complete registration so I can show your timetable."
    return "I couldn't find that in ORION's campus data." + (f" ({warning})" if warning else "")
