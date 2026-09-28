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

from . import documents, router, timeq
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
        # "B Coding Club Activities": the "B" of a vertical "Break" column
        # the PDF extractor picked up with the cell text.
        st = re.sub(r"^[A-Z]\s+(?=[A-Z][a-z])", "", e["source_text"].strip())
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
        key = (e.get("day_of_week"), e.get("start_time"), e.get("end_time"), e.get("course_code") or e.get("source_text"),
               e.get("entry_type"), bool(e.get("_cancelled")))
        if key in merged:
            m = merged[key]
            m["faculty_names"] = list(dict.fromkeys((m.get("faculty_names") or []) + (e.get("faculty_names") or [])))
            if e.get("lab_batch") and m.get("lab_batch") and e["lab_batch"] not in m["lab_batch"]:
                m["lab_batch"] = f"{m['lab_batch']}/{e['lab_batch']}"
        else:
            merged[key] = dict(e)
    return list(merged.values())


def _change_tag(e: dict) -> str:
    if e.get("_cancelled"):
        return f" — ~~cancelled~~ *({e.get('_change_note') or 'cancelled'})*"
    if e.get("_moved_from"):
        return f" — *rescheduled here from {e['_moved_from']}*"
    if e.get("_extra"):
        return " — *extra class*"
    return ""


def _entry_line(e: dict, today: bool = False) -> str:
    status = ""
    if e.get("_cancelled") or e.get("_extra") or e.get("_moved_from"):
        return f"- **{fmt_range(e.get('start_time'), e.get('end_time'))}** · {entry_label(e)}{entry_extras(e)}{_change_tag(e)}"
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
    listed = _merge_slots([f.data for f in ctx.facts if f.data.get("start_time")])
    cancelled = [e for e in listed if e.get("_cancelled")]
    changed = [e for e in listed if e.get("_extra") or e.get("_moved_from")] + cancelled
    entries = [e for e in listed if not e.get("_cancelled")]
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
        if cancelled:
            return (f"Your classes {phrase} have been cancelled:\n\n" + "\n".join(_entry_line(e) for e in cancelled)
                    + source_line("your live timetable", "class updates from your CR"))
        weekend = day_ref in {"Sunday", "Saturday"}
        return f"You have no classes {phrase}." + (" Enjoy the weekend!" if weekend and day_ref == "Sunday" else "")
    src = source_line("your live timetable")
    focus = hints.get("focus")
    if hints.get("from") and hints.get("to"):
        lo, hi = timeq.to_minutes(hints["from"]), timeq.to_minutes(hints["to"])
        inside = [e for e in entries if timeq.to_minutes(e["start_time"]) < hi and timeq.to_minutes(e["end_time"]) > lo]
        part = hints.get("part") or f"between {fmt_time(hints['from'])} and {fmt_time(hints['to'])}"
        where = f"in the {part}" if part in ("morning", "afternoon", "evening") else part
        if not inside:
            return f"Nothing {where} {phrase} — you're free then." + src
        return (f"{where[0].upper() + where[1:]} {phrase} you have:\n\n"
                + "\n".join(_entry_line(e, today=is_today) for e in inside) + src)
    if focus == "past":
        now = now_ist()
        now_m = now.hour * 60 + now.minute
        done = [e for e in entries if timeq.to_minutes(e["end_time"]) <= now_m]
        ongoing = [e for e in entries if timeq.to_minutes(e["start_time"]) <= now_m < timeq.to_minutes(e["end_time"])]
        if not done and not ongoing:
            return "Nothing yet — none of today's classes have started." + src
        text = ("Classes already over today:\n\n" + "\n".join(_entry_line(e) for e in done)) if done else "No class has finished yet today."
        if ongoing:
            text += "\n\nGoing on now: " + "; ".join(f"**{entry_label(e)}** ({fmt_range(e['start_time'], e['end_time'])})" for e in ongoing)
        return text + "\n\nFor what was covered, check with your classmates or the course faculty." + src
    if focus == "first":
        e = entries[0]
        return f"Your first class {phrase} is **{entry_label(e)}** at {fmt_time(e['start_time'])} ({fmt_range(e['start_time'], e['end_time'])}){entry_extras(e)}.{src}"
    if focus == "last":
        e = entries[-1]
        return f"Your last class {phrase} is **{entry_label(e)}**, which ends at **{fmt_time(e['end_time'])}**{entry_extras(e)}.{src}"
    n = len(entries)
    head = (f"You have **{n} {'class' if n == 1 else 'classes'}** {phrase}:" if focus == "count"
            else f"Here's your timetable {phrase}:")
    if changed:
        head += f" *(includes {len(changed)} change{'s' if len(changed) != 1 else ''} announced by your CR)*"
        src = source_line("your live timetable", "class updates from your CR")
    shown = sorted(entries + cancelled, key=lambda e: e.get("start_time") or "")
    lines = "\n".join(_entry_line(e, today=is_today) for e in shown)
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
    if hints.get("focus") == "count" and not hints.get("course_filter"):
        teaching = [e for e in entries if (e.get("entry_type") or "class") in {"class", "lab", "tutorial"}]
        kinds: dict[str, int] = {}
        for e in teaching:
            kinds[e.get("entry_type") or "class"] = kinds.get(e.get("entry_type") or "class", 0) + 1
        per_day: dict[int, int] = {}
        for e in teaching:
            per_day[e.get("day_of_week") or 0] = per_day.get(e.get("day_of_week") or 0, 0) + 1
        split = ", ".join(f"{n} {k}{'s' if n != 1 and k != 'class' else ('es' if n != 1 else '')}"
                          for k, n in sorted(kinds.items(), key=lambda x: -x[1]))
        days = " · ".join(f"{_DAYS.get(d, '')[:3]} {n}" for d, n in sorted(per_day.items()))
        extra = len(entries) - len(teaching)
        return (f"You have **{len(teaching)} classes** this week ({split}).\n\nPer day: {days}."
                + (f" Plus {extra} activity slot{'s' if extra != 1 else ''} (clubs, sports, interaction hours)." if extra else "")
                + source_line("your live timetable"))
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
        return _with_next_event(ctx, lead, src)
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
    s_m, e_m = timeq.to_minutes(d.get("start_time")), timeq.to_minutes(d.get("end_time"))
    if re.search(r"\bhow\s+long\s+(is|does)\b|\bduration\b|\bhow\s+long\s+.*\blast\b", ctx.query, re.I) and s_m is not None and e_m is not None:
        text = f"Your next class, **{entry_label(d)}**, is {timeq.fmt_duration(e_m - s_m)} long — {when}, {fmt_range(d['start_time'], d['end_time'])}."
        return text + src
    if re.search(r"\bhow\s+(long|much\s+time)\s+(until|till|before|left)\b|\bwhen\s+does\s+my\s+next\s+class\s+start\b|\bstarts?\s+in\b", ctx.query, re.I) \
            and s_m is not None and "today" in when.lower():
        now = now_ist()
        gap = s_m - (now.hour * 60 + now.minute)
        if gap > 0:
            return (f"Your next class, **{entry_label(d)}**, starts in **{timeq.fmt_duration(gap)}** "
                    f"(at {fmt_time(d['start_time'])}){entry_extras(d)}." + src)
    if d.get("_gap") and "no more classes today" in d["_gap"]:
        text += " You have no more classes today."
    elif d.get("_gap"):
        text += f" Nothing else is scheduled before then ({d['_gap'].split('— ')[-1]})."
    return _with_next_event(ctx, text, src)


def _with_next_event(ctx: GroundedContext, text: str, src: str) -> str:
    """A bare "what's next?" also gets the next thing on the academic
    calendar (service adds it as a `_next_event` fact)."""
    event = next((f.data for f in ctx.facts if f.data.get("_next_event")), None)
    if not event:
        return text + src
    text += (f"\n\nNext on the academic calendar: **{event_name(event)}** on {fmt_date(event['event_date'])} "
             f"({relative_day(event['event_date'])}).")
    return text + source_line("your live timetable", "academic calendar, Odd semester 2026-27")


def compose_free(ctx: GroundedContext, day_ref: str) -> str:
    """Answers the exact time question asked (timeq.py): free AT a time,
    within a window, after/before a time, the longest slot — and only lists
    the whole day when the question was just "when am I free?"."""
    facts = [f.data for f in ctx.facts]
    phrase = _day_phrase(day_ref, None)
    ask = timeq.TimeAsk.from_hints((ctx.plan.hints or {}) if ctx.plan else {})
    if facts and facts[0].get("_empty"):
        return f"You have no classes {phrase}, so you're free all day." + source_line("your live timetable")
    entries = _merge_slots([e for e in facts if e.get("start_time") and not e.get("_cancelled")])
    blocks = timeq.busy_blocks(entries, entry_label)
    now = now_ist()
    on = facts[0].get("_date") if facts else None
    now_minute = now.hour * 60 + now.minute if (not on or on == now.date().isoformat()) else None
    if ask.now and now_minute is None:
        ask = timeq.TimeAsk()
    return timeq.answer_free(blocks, ask, phrase, now_minute) + source_line("your live timetable")


def compose_working_day(ctx: GroundedContext) -> str:
    meta = next((f.data for f in ctx.facts if f.data.get("_working_day")), {})
    on = date.fromisoformat(meta["date"])
    rel = relative_day(on)
    label = f"**{fmt_date(on)}**" + (f" ({rel})" if rel in {"today", "tomorrow", "yesterday"} else "")
    listed = _merge_slots([f.data for f in ctx.facts if f.data.get("start_time")])
    entries = [e for e in listed if not e.get("_cancelled")]
    cancelled = [e for e in listed if e.get("_cancelled")]
    teaching = [e for e in entries if (e.get("entry_type") or "class") in {"class", "lab", "tutorial"}]
    events = meta.get("events") or []
    src = source_line("your live timetable", "academic calendar, Odd semester 2026-27")
    def in_range(a: Optional[str], b: Optional[str]) -> bool:
        return bool(a and b and a <= on.isoformat() <= b)
    if meta.get("exams_start") and in_range(meta["exams_start"], meta.get("exams_end")):
        text = (f"{label} falls in the **end-semester exam period** "
                f"({fmt_date(meta['exams_start'], False)} – {fmt_date(meta['exams_end'], False)}), so regular classes don't run.")
    elif meta.get("class_ends") and on.isoformat() > meta["class_ends"]:
        text = (f"No regular classes on {label} — the last instructional day is "
                f"{fmt_date(meta['class_ends'])}.")
    elif meta.get("class_begins") and on.isoformat() < meta["class_begins"]:
        text = f"No — classes start on {fmt_date(meta['class_begins'])}, after {label}."
    elif on.isoweekday() == 7 and not entries:
        text = f"No — {label} is a Sunday; you have no classes."
    elif teaching:
        text = (f"Yes — {label} is a working day. You have **{len(teaching)} class{'es' if len(teaching) != 1 else ''}**, "
                f"from {fmt_time(teaching[0]['start_time'])} to {fmt_time(max(e['end_time'] for e in teaching))}:\n\n"
                + "\n".join(f"- {fmt_range(e['start_time'], e['end_time'])} · {entry_label(e)}{_change_tag(e)}" for e in teaching))
    elif entries:
        text = (f"{label} has no classes in your timetable, only " + ", ".join(entry_label(e) for e in entries) + ".")
    else:
        text = f"You have no classes on {label}."
    if cancelled:
        text += "\n\nCancelled that day (from your CR): " + "; ".join(
            f"**{entry_label(e)}** {fmt_range(e['start_time'], e['end_time'])}" for e in cancelled) + "."
    if events:
        text += "\n\nOn the academic calendar that day: " + "; ".join(f"**{event_name(e)}**" for e in events) + "."
    if not meta.get("holidays_listed") and re.search(r"\b(holiday|working|off)\b", ctx.query, re.I):
        text += "\n\nThe academic calendar in ORION doesn't list public holidays, so check the notice board for any declared holiday."
    return text + src


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
    if (ctx.plan.hints or {}).get("ask") == "core_elective" if ctx.plan else False:
        text += ("\n\nThe course catalogue doesn't record whether a course is core or an elective — your programme's "
                 "curriculum document lists it under its course category.")
    elif not d.get("syllabus_summary"):
        text += "\n\nA syllabus summary isn't available yet — the full syllabus is in your programme's curriculum document."
    return text + source_line(*sources)


def compose_course_faculty(ctx: GroundedContext) -> str:
    facts = ctx.facts
    course = facts[0].data.get("course") or {}
    label = f"**{nice_title(course.get('course_name'))}** ({course.get('course_code')})"
    if facts[0].data.get("_no_faculty"):
        return f"{label} is in the course catalog, but no teacher is linked to it in the current timetable."
    people = [f.data for f in facts if f.data.get("full_name")]
    names = [p["full_name"] for p in people]
    lab = any(p.get("_entry_type") == "lab" for p in people)
    text = (f"The {label} lab is taken by {join_names(names)}." if lab else f"{label} is taught by {join_names(names)}.")
    if len(names) > 1:
        text += " Different sections may have different teachers."
    contacts = [f"- {p['full_name']} — {p['email']}" for p in people if p.get("email")]
    if contacts:
        text += "\n\n" + "\n".join(contacts)
    return text + source_line("your live timetable", "faculty directory")


_ATTR_EMAIL = re.compile(r"\b(e-?mail|mail\s+id)\b", re.I)
_ATTR_PHONE = re.compile(r"\b(phone|mobile|number|call|contact\s+no|landline|extension)\b", re.I)
_ATTR_CONTACT = re.compile(r"\b(contact|reach|get\s+in\s+touch)\b", re.I)
_ATTR_OFFICE = re.compile(r"\b(office|cabin|room|where\s+(is|can\s+i\s+find|do\s+i\s+find))\b", re.I)
_ATTR_RESEARCH = re.compile(r"\b(research|work(s|ing)?\s+on|interests?|specializ|expert)\w*", re.I)
_ATTR_POSITION = re.compile(r"\b(position|designation|role|post|title|fit\s+in|what\s+(does|is)\s+\S+(\s+\S+){0,3}\s+do)\b", re.I)


def _matched_differently(typed: Optional[str], full_name: str) -> bool:
    """True when the name found isn't what was typed ("Jhon" -> "John"), so
    the answer should say which person it resolved to. Only the name words
    of the question count — "Amit sir email" typed "Amit" correctly."""
    if not typed:
        return False
    from . import campus  # lazy: campus pulls in retrieval

    from . import lexicon

    found = set(re.sub(r"[^a-z ]+", " ", full_name.lower()).split())
    # A typed word that is close to — but not exactly — one of the name's
    # words ("Jhon" / "John"); unrelated words ("available") don't count.
    return any(w not in found and max((lexicon.similarity(w, t) for t in found), default=0) >= 0.75
               for w in campus.query_name_words(typed))


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
        return ("More than one person matches — which one did you mean?\n\n"
                + "\n".join(f"- **{p['full_name']}**" + (f" — {p['designation']}" if p.get("designation") else "")
                             + (f" · {p['email']}" if p.get("email") else "") for p in people)
                + source_line("faculty directory"))
    p = people[0]
    name = p["full_name"]
    src = source_line("faculty directory")
    # A misspelt name that resolved to someone ("Jhon" -> "Dr.John Paul
    # Martin") says so, so the student can tell if it's the wrong person.
    lead = f"Closest match in the directory: **{name}**.\n\n" if _matched_differently(ctx.plan.topic_text if ctx.plan else None, name) else ""
    if hints.get("focus") == "meet":
        slots = p.get("teaching_slots") or []
        text = f"I don't have office hours on file for **{name}**, so I can't confirm when they're free."
        if slots:
            text += f" They teach at these times, so they'll be busy then:\n\n{_slots_text(slots)}"
        if p.get("email"):
            text += f"\n\nThe reliable way is to email them to set a time: **{p['email']}**"
        if p.get("office_location"):
            text += f" (office: {p['office_location']})."
        return text + source_line("faculty directory", "your live timetable" if slots else None)
    if hints.get("focus") == "availability":
        slots = p.get("teaching_slots") or []
        now = now_ist()
        now_m, dow = now.hour * 60 + now.minute, now.isoweekday()
        today = sorted((s for s in slots if s.get("day_of_week") == dow), key=lambda s: s["start_time"])
        busy = next((s for s in today if timeq.to_minutes(s["start_time"]) <= now_m < timeq.to_minutes(s["end_time"])), None)
        nxt = next((s for s in today if timeq.to_minutes(s["start_time"]) > now_m), None)
        if busy:
            text = (f"By the timetable, **{name}** is teaching right now — {busy.get('course_code') or 'a class'} "
                    f"until {fmt_time(busy['end_time'])}.")
        else:
            text = f"By the timetable, **{name}** isn't teaching right now."
            text += (f" Their next class today is {nxt.get('course_code') or 'a class'} at {fmt_time(nxt['start_time'])}."
                     if nxt else " They have no more classes today.")
        text += (" I can't see whether they're actually in their cabin"
                 + (f" ({p['office_location']})" if p.get("office_location") else "")
                 + (f" — email **{p['email']}** to be sure." if p.get("email") else "."))
        return lead + text + source_line("your live timetable", "faculty directory")
    if hints.get("focus") == "subjects":
        subjects = p.get("subjects") or []
        mine = p.get("_my_courses")
        if mine is not None:
            shared = [c for c in subjects if c["course_code"] in mine]
            if shared:
                return (lead + f"Yes — **{name}** teaches "
                        + join_names([f"**{nice_title(c['course_name'])}** ({c['course_code']})" for c in shared])
                        + ", which you take this semester." + source_line("your live timetable"))
            return (lead + f"No — **{name}** doesn't teach any of your courses this semester"
                    + (f" (they teach {', '.join(c['course_code'] for c in subjects)})." if subjects else ".")
                    + source_line("your live timetable"))
        if not subjects:
            return lead + (f"**{name}** isn't linked to any course in the current timetable, so I can't say what they "
                           f"teach this semester.") + src
        lines = []
        for c in subjects:
            kinds = [t for t in c["types"] if t != "class"]
            lines.append(f"- **{nice_title(c['course_name'])}** ({c['course_code']})"
                         + (f" — {', '.join(kinds)}" if kinds else "")
                         + (f" · {', '.join(c['classes'][:3])}" + ("…" if len(c["classes"]) > 3 else "") if c["classes"] else ""))
        return (lead + f"**{name}** teaches {len(subjects)} course{'s' if len(subjects) > 1 else ''} this semester:\n\n"
                + "\n".join(lines) + source_line("your live timetable", "faculty directory"))
    if _ATTR_PHONE.search(q) and not _ATTR_EMAIL.search(q):
        return lead + (f"{name}'s phone number is **{p['phone']}**." if p.get("phone")
                       else f"I don't have a phone number on file for {name}.") + (
                    f" Email: {p['email']}." if p.get("email") else "") + src
    if _ATTR_CONTACT.search(q) and not (_ATTR_EMAIL.search(q) or _ATTR_OFFICE.search(q)):
        bits = [x for x in (f"email **{p['email']}**" if p.get("email") else None,
                            f"phone **{p['phone']}**" if p.get("phone") else None,
                            f"office {p['office_location']}" if p.get("office_location") else None) if x]
        return lead + (f"You can reach **{name}** by " + ", ".join(bits) + "." if bits
                       else f"I don't have contact details on file for {name}.") + src
    if _ATTR_POSITION.search(q) and p.get("designation") and not _ATTR_EMAIL.search(q) and not _ATTR_RESEARCH.search(q):
        article = "an" if p["designation"][:1].lower() in "aeiou" else "a"
        text = f"**{name}** is {article} **{p['designation']}**"
        text += (" at IIIT Kottayam." if not p.get("email") else f" — email {p['email']}")
        text += (f", office {p['office_location']}." if p.get("office_location") else ("" if text.endswith(".") else "."))
        return lead + text + src
    if _ATTR_EMAIL.search(q):
        return lead + (f"{name}'s email is **{p['email']}**." if p.get("email")
                else f"I don't have an email address on file for {name}.") + src
    if _ATTR_OFFICE.search(q) and not _ATTR_RESEARCH.search(q):
        return lead + (f"{name}'s office is **{p['office_location']}**." if p.get("office_location")
                else f"I don't have an office location on file for {name}.") + (
                    f" Email: {p['email']}." if p.get("email") else "") + src
    if _ATTR_RESEARCH.search(q):
        return lead + (f"{name}'s research interests: {p['research_interests']}." if p.get("research_interests")
                else f"I don't have research interests on file for {name}.") + src
    lines = [f"**{name}**" + (f" ({p['initials']})" if p.get("initials") else "")]
    if p.get("designation"):
        lines.append(f"- {p['designation']}")
    if p.get("email"):
        lines.append(f"- Email: {p['email']}")
    if p.get("phone"):
        lines.append(f"- Phone: {p['phone']}")
    if p.get("office_location"):
        lines.append(f"- Office: {p['office_location']}")
    if p.get("office_hours"):
        lines.append(f"- Office hours: {p['office_hours']}")
    if p.get("research_interests"):
        lines.append(f"- Research: {p['research_interests']}")
    return lead + "\n".join(lines) + src


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
        label = {"librarian": "a librarian", "iqac": "an IQAC coordinator", "placement": "a training/placement officer"}.get(role, "anyone with that role")
        return (f"The faculty directory in ORION doesn't list {label}. The administrative office can point you to the "
                "right person.")
    people = [f.data for f in ctx.facts]
    note = next((p.get("_note") for p in people if p.get("_note")), None)
    if note:
        text = compose_roles_list(people, role)
        return f"{note}\n\n{text}"
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


def compose_roles_list(people: list[dict], role: str) -> str:
    lines = []
    for p in people:
        bits = [p["designation"]] + [x for x in (p.get("email"), p.get("phone"),
                                                 f"office {p['office_location']}" if p.get("office_location") else None) if x]
        lines.append(f"- **{p['full_name']}** — " + " · ".join(bits))
    return "\n".join(lines) + source_line("faculty directory")


# ---------------------------------------------------------------- faculty directory

def compose_faculty_directory(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts]
    meta = rows[0] if rows else {}
    label, total, groups = meta.get("_filter"), meta.get("_total", 0), meta.get("_groups") or {}
    src = source_line("faculty directory")
    people = [r for r in rows if r.get("full_name") and not r.get("_near_miss")]
    if label and not people:
        text = f"No one in the faculty directory is designated **{label}**."
        near = [r for r in rows if r.get("_near_miss")]
        if near:
            text += (" The closest titles are the **Associate Deans** — faculty members who also hold an "
                     "administrative role:\n\n" + "\n".join(f"- **{r['full_name']}** — {r['designation']}" for r in near))
        return text + src
    if label:
        yes = "Yes — " if meta.get("_yes_no") else ""
        noun = {"administrative": "faculty members also hold administrative positions",
                "academic administration": "people are in academic administration",
                "professional support": "people are in professional support roles"}.get(label, f"people are **{label}**")
        plural = {"Assistant Professor": "Assistant Professors", "Associate Professor": "Associate Professors",
                  "Lab Faculty": "Lab Faculty", "Adjunct": "adjunct faculty", "Visiting": "visiting faculty"}
        head = f"{yes}{len(people)} {noun}:" if label in {"administrative", "academic administration", "professional support"} \
            else f"{yes}**{len(people)}** people in the directory are **{plural.get(label, label)}**:"
        if len(people) <= 25 or label in {"administrative", "academic administration"}:
            body = "\n".join(f"- **{r['full_name']}** — {r['designation']}" for r in people)
        else:
            limit = 40
            shown = ", ".join(r["full_name"] for r in people[:limit])
            more = len(people) - limit
            body = f"{shown}, and {more} more." if more > 0 else f"{shown}."
        return f"{head}\n\n{body}" + src
    order = ["Assistant Professors", "Lab Faculty", "Adjunct Faculty", "Heads of Department", "Associate Deans"]
    parts = [f"{groups[g]} {g}" for g in order if groups.get(g)]
    parts += [f"{n} {g}" for g, n in sorted(groups.items()) if g not in order]
    text = (f"The faculty directory lists **{total} teaching faculty**: {join_names(f'**{x}**' for x in parts)}."
            "\n\nAsk me about a group (\"who are the adjunct faculty?\", \"which faculty are assistant professors?\"), "
            "a department head (\"who heads ECE?\"), a research area (\"who works on machine learning?\"), or a "
            "person by name.")
    if meta.get("_dept_asked"):
        text = ("Departments aren't recorded for individual faculty in the directory yet (only for department heads), "
                "so I can't list teachers by department. " + text)
    return text + src


# ---------------------------------------------------------------- mess

def _dish_answer(rows: list[dict], dish: str) -> Optional[str]:
    hits = []
    for r in sorted(rows, key=lambda r: (r["display_date"], _MEAL_ORDER.get(r["meal"], 9))):
        for item in r["items"]:
            if re.search(rf"{re.escape(dish.rstrip('s'))}", item, re.I):
                hits.append((r, item.strip()))
    if not rows:
        return None
    day = rows[0]["display_date"]
    when = f"{fmt_date(day)}" + (f" ({relative_day(day)})" if relative_day(day) in {"today", "tomorrow", "yesterday"} else "")
    if hits:
        found = "; ".join(f"**{item}** at {r['meal']}" for r, item in hits)
        return f"Yes — {found} on {when}."
    menu = "\n".join(f"- **{r['meal'].capitalize()}:** {', '.join(r['items'])}"
                     for r in sorted(rows, key=lambda r: _MEAL_ORDER.get(r["meal"], 9)))
    return f"No {dish} on the menu for {when}. Here's what's on it:\n\n{menu}"


def compose_mess(ctx: GroundedContext) -> str:
    meal = ctx.plan.meal if ctx.plan else None
    mess_time = ((ctx.plan.hints or {}) if ctx.plan else {}).get("mess_time")
    if mess_time:
        timing = next((f.data for f in ctx.facts if f.data.get("_timings")), None)
        if not timing or not timing.get("timings"):
            return ("I don't have the mess timings on file. The menu board at the dining hall lists them."
                    + source_line("mess timings (not on file)"))
        now = now_ist()
        return (timeq.answer_mess_time(timing["timings"], mess_time, meal, now.hour * 60 + now.minute)
                + source_line(f"mess timings ({timing.get('source') or 'published menu'})"))
    rows = [f.data for f in ctx.facts if f.data.get("meal")]
    if rows and ((ctx.plan.hints or {}) if ctx.plan else {}).get("veg_check"):
        nonveg_re = re.compile(r"\b(chicken|egg\w*|fish|mutton|beef|pork|prawns?|meat|omelette|keema|non[\s-]?veg\w*)\b", re.I)
        lines = []
        for r_ in sorted(rows, key=lambda r_: _MEAL_ORDER.get(r_["meal"], 9)):
            found = [i for i in r_["items"] if nonveg_re.search(i)]
            lines.append(f"- **{r_['meal'].capitalize()}:** " + (f"non-veg — {', '.join(found)} (veg items too)" if found else "vegetarian"))
        d = rows[0]["display_date"]
        head = (f"{rows[0]['meal'].capitalize()} on **{fmt_date(d)}** is **"
                + ("not fully vegetarian" if any("non-veg" in l for l in lines) else "vegetarian") + "**."
                if len(rows) == 1 else f"On **{fmt_date(d)}**:")
        return (head + ("\n\n" + "\n".join(lines) if len(rows) > 1 or "non-veg" in lines[0] else "")
                + "\n\n(Judged from the dish names on the menu.)" + source_line("mess menu"))
    if not rows:
        return "There's no mess menu on file for that day." + (f" (asked about {meal})" if meal else "")
    dish = (ctx.plan.hints or {}).get("dish") if ctx.plan else None
    if dish:
        text = _dish_answer(rows, dish) or ""
        stale = sorted({r["source_date"] for r in rows if not r.get("is_actual")})
        if stale:
            text += (f"\n\nNote: this is the regular weekly menu from the most recent week on file "
                     f"({fmt_date(stale[0], False)}); a menu hasn't been published for these dates yet.")
        return text + source_line("mess menu")
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


def _compose_calendar_mode(ctx: GroundedContext, mode: str) -> str:
    rows = [f.data for f in ctx.facts]
    events = [e for e in rows if not e.get("_class")]
    src = source_line("academic calendar, Odd semester 2026-27")
    today = now_ist().date()
    hints = (ctx.plan.hints or {}) if ctx.plan else {}
    if mode == "on_date":
        target = hints.get("date")
        label = fmt_date(target) if target else "that date"
        on = [e for e in events if not e.get("_nearest")]
        if on:
            tense = "was" if target and date.fromisoformat(target) < today else "is"
            lines = "\n".join(f"- **{event_name(e)}**" for e in on)
            return f"On **{label}** the academic calendar {'had' if tense == 'was' else 'has'}:\n\n{lines}" + src
        text = f"Nothing is on the academic calendar for **{label}**."
        if events:
            text += " Nearest events:\n\n" + "\n".join(_event_line(e) for e in events)
        return text + src
    if mode == "gap":
        if len(events) == 2 and events[0].get("_gap_days") is not None:
            a, b = events
            days = a["_gap_days"]
            return (f"**{event_name(a)}** is on {fmt_date(a['event_date'])} and **{event_name(b)}** is on "
                    f"{fmt_date(b['event_date'])} — **{days} day{'s' if days != 1 else ''}** apart." + src)
        if len(events) == 1 and events[0].get("_gap_from_today"):
            e = events[0]
            d = date.fromisoformat(e["event_date"])
            n = (d - today).days
            if n < 0:
                return f"**{event_name(e)}** was on {fmt_date(d)} — {-n} days ago." + src
            return f"**{event_name(e)}** is on {fmt_date(d)} — **{n} day{'s' if n != 1 else ''}** from today." + src
        return "I couldn't tell which two calendar events you meant. Try naming both, e.g. \"days between classes end and the end semester exams\"." + src
    if mode == "after_event":
        if not events:
            anchor = hints.get("anchor", "that event")
            return f"I couldn't find anything on the academic calendar after {anchor}." + src
        e = events[0]
        return (f"After the **{nice_title(_base_label(e.get('_anchor', '')))}** (ends {fmt_date(e['_anchor_date'])}), the next event is "
                f"**{event_name(e)}** on {fmt_date(e['event_date'])} ({relative_day(e['event_date'])})." + src)
    if mode == "exams":
        if not events:
            return "There are no exams on the academic calendar." + src
        return ("Exams on the academic calendar this semester:\n\n" + "\n".join(_event_line(e) for e in events)
                + "\n\nThe per-course exam timetable isn't published in ORION yet." + src)
    if mode == "upcoming":
        if not events:
            return "There's nothing left on the academic calendar for this semester." + src
        return "Coming up on the academic calendar:\n\n" + "\n".join(_event_line(e) for e in events) + src
    if mode == "past":
        if not events:
            return "Nothing on the academic calendar has happened yet this semester." + src
        return "Already past on the academic calendar (most recent first):\n\n" + "\n".join(_event_line(e) for e in events) + src
    if mode == "today":
        on = [e for e in events if e.get("_today")]
        nxt = [e for e in events if e.get("_next")]
        classes = _merge_slots([r for r in rows if r.get("_class")])
        parts = []
        if on:
            parts.append("On the academic calendar today: " + "; ".join(f"**{event_name(e)}**" for e in on) + ".")
        else:
            parts.append("Nothing special is on the academic calendar today.")
        if classes:
            parts.append(f"You have **{len(classes)} class{'es' if len(classes) != 1 else ''}** today: "
                         + "; ".join(f"{fmt_range(c['start_time'], c['end_time'])} {entry_label(c)}" for c in classes) + ".")
        else:
            parts.append("You have no classes today.")
        if nxt:
            e = nxt[0]
            parts.append(f"Next on the calendar: **{event_name(e)}** on {fmt_date(e['event_date'])} ({relative_day(e['event_date'])}).")
        return "\n\n".join(parts) + source_line("academic calendar, Odd semester 2026-27", "your live timetable" if classes else None)
    return ""


def _base_label(name: str) -> str:
    return re.sub(r"\s+(starts?|begins?|ends?)\s*$", "", name or "", flags=re.I)


def compose_calendar(ctx: GroundedContext) -> str:
    mode = ((ctx.plan.hints or {}) if ctx.plan else {}).get("cal_mode")
    if mode:
        text = _compose_calendar_mode(ctx, mode)
        if text:
            return text
    events = [f.data for f in ctx.facts]
    src = source_line("academic calendar, Odd semester 2026-27")
    today = now_ist().date()
    holiday_q = any(e.get("_holiday_query") for e in events) or re.search(r"holiday|vacation", ctx.query, re.I)
    if holiday_q and not any(e.get("event_type") in {"holiday", "vacation"} for e in events):
        text = "The academic calendar doesn't list any holidays for this semester."
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


_EXAM_TYPE_WORDS = {"end_sem": "end-semester", "mid_sem": "mid-semester", "repeat": "repeat", "quiz": "quiz",
                    "other": ""}


def _exam_line(r: dict) -> str:
    alt = f" *(or {r['alt_group'].replace('/', ' / ')} — your elective)*" if r.get("alt_group") else ""
    return (f"- **{fmt_date(r['exam_date'])}** · {fmt_range(r.get('start_time'), r.get('end_time'))} · "
            f"{nice_title(r.get('course_name')) or ''} ({r.get('course_code')})".replace(" ()", "") + alt)


def compose_exam(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts if f.data.get("_exam")]
    window = [f.data for f in ctx.facts if f.data.get("_window")]
    course = next((f.data.get("course") for f in ctx.facts if f.data.get("course")), None) or {}
    today = now_ist().date()
    if rows:
        src = source_line("exam schedule (approved by the admin)")
        upcoming = [r for r in rows if r["exam_date"] >= today.isoformat()]
        if rows[0].get("_asked_course"):
            r = (upcoming or rows)[0]
            kind = _EXAM_TYPE_WORDS.get(r.get("exam_type"), "")
            rel = relative_day(r["exam_date"])
            when = f"**{fmt_date(r['exam_date'])}**" + (f" ({rel})" if rel in {"today", "tomorrow"} else "")
            text = (f"Your **{nice_title(r.get('course_name')) or r.get('course_code')}** ({r.get('course_code')}) "
                    f"{kind + ' ' if kind else ''}exam is on {when}, {fmt_range(r.get('start_time'), r.get('end_time'))}.")
            if r.get("alt_group"):
                text += f" It's in the same slot as {r['alt_group'].replace('/', ' / ')} — sit the one you're registered for."
            return text + src
        if re.search(r"\b(next|upcoming|first)\s+exam\b", ctx.query, re.I) and upcoming:
            r = upcoming[0]
            return (f"Your next exam is **{nice_title(r.get('course_name'))}** ({r.get('course_code')}) on "
                    f"**{fmt_date(r['exam_date'])}**, {fmt_range(r.get('start_time'), r.get('end_time'))}." + src)
        shown = upcoming or rows
        kind = _EXAM_TYPE_WORDS.get(shown[0].get("exam_type"), "")
        return (f"Your {kind + ' ' if kind else ''}exam schedule ({len(shown)} exam{'s' if len(shown) != 1 else ''}):\n\n"
                + "\n".join(_exam_line(r) for r in shown) + src)
    label = f"**{nice_title(course.get('course_name'))}** ({course.get('course_code')})" if course else "your courses"
    src = source_line("academic calendar, Odd semester 2026-27")
    end_start = next((e for e in window if re.search(r"end semester examination starts", e["event_name"], re.I)), None)
    end_end = next((e for e in window if re.search(r"end semester exam ends", e["event_name"], re.I)), None)
    text = f"The exam timetable for {label} hasn't been published in ORION yet."
    if end_start and date.fromisoformat(end_start["event_date"]) >= today:
        text += (f" From the academic calendar, the end semester exams run from **{fmt_date(end_start['event_date'])}**"
                 + (f" to **{fmt_date(end_end['event_date'])}**" if end_end else "") + ".")
    upcoming_ev = [e for e in window if date.fromisoformat(e["event_date"]) >= today and e is not end_start and e is not end_end][:2]
    if upcoming_ev:
        text += "\n\nOther exam dates:\n\n" + "\n".join(_event_line(e) for e in upcoming_ev)
    return text + src


# ---------------------------------------------------------------- misc structured

_NOTICE_NAMES = {"QUIZ": "quiz", "ASSIGNMENT": "assignment", "CLASS_UPDATE": "class change or cancellation",
                 "NOTICE": "class notice"}


def _event_when(a: dict) -> str:
    if not a.get("event_date"):
        return ""
    when = f"**{fmt_date(a['event_date'])}**"
    rel = relative_day(a["event_date"])
    if rel in ("today", "tomorrow"):
        when += f" ({rel})"
    if a.get("event_time"):
        t = str(a["event_time"])[:5]
        hh, mm = int(t[:2]), t[3:5]
        when += f" at {hh % 12 or 12}:{mm} {'PM' if hh >= 12 else 'AM'}"
    return when


def compose_announcements(ctx: GroundedContext) -> str:
    notice = (ctx.plan.hints or {}).get("notice") if ctx.plan else None
    if not ctx.facts:
        if notice:
            return (f"No {_NOTICE_NAMES.get(notice, 'notice')} has been posted for your class. "
                    "Your CR posts these in ORION — if you heard about one elsewhere, check with them.")
        return "There are no current announcements right now."
    parts = []
    if notice and notice != "NOTICE":
        first = ctx.facts[0].data
        when = _event_when(first)
        parts.append(f"**{first['title']}**" + (f" — {when}." if when else "."))
        body = (first.get("content") or "").strip()
        if body and body.lower() != first["title"].strip().lower():
            parts.append(body[:400] + ("…" if len(body) > 400 else ""))
        rest = ctx.facts[1:]
        if rest:
            parts.append("\nAlso posted:")
            parts.extend(f"- **{f.data['title']}**" + (f" — {_event_when(f.data)}" if f.data.get("event_date") else "")
                         for f in rest)
    else:
        parts.append("Here are the current announcements:")
        for f in ctx.facts:
            a = f.data
            posted = (a.get("published_at") or a.get("created_at") or "")[:10]
            when = _event_when(a)
            body = (a.get("content") or "").strip()
            if len(body) > 220:
                body = body[:220].rsplit(" ", 1)[0] + "…"
            head = f"\n**{a['title']}**" + (f" · {when}" if when else (f" · posted {fmt_date(posted, False)}" if posted else ""))
            parts.append(head)
            if body:
                parts.append(body)
    by_cr = any(f.data.get("auto_published") for f in ctx.facts)
    return "\n".join(parts) + source_line("announcements" + (" (class notices posted by your CR)" if by_cr else ""))


_WARDEN_ROLE = {"hostel_warden": "Warden", "assistant_warden": "Assistant warden", "standby_warden": "Standby warden",
                "chief_warden": "Chief Warden", "hostel_manager": "Hostel Manager", "security_officer": "Security Officer",
                "associate_dean_hostel_affairs_and_student_events": "Associate Dean (Hostel Affairs & Student Events)"}


def _contact(r: dict) -> str:
    bits = [x for x in (r.get("phone"), r.get("email")) if x]
    return f" · {' · '.join(bits)}" if bits else ""


def _hall_gender(hall: str) -> Optional[str]:
    m = re.search(r"\((BOYS|GIRLS)\)", hall.upper())
    return {"BOYS": "boys'", "GIRLS": "girls'"}.get(m.group(1)) if m else None


def compose_wardens(ctx: GroundedContext) -> str:
    rows = [f.data for f in ctx.facts]
    if not rows:
        return "I couldn't find warden details for that hostel."
    if ((ctx.plan.hints or {}) if ctx.plan else {}).get("focus") == "gender":
        halls = list(dict.fromkeys(r["hall_name"] for r in rows if r.get("hall_name")))
        src = source_line("Wardens Team, July 2026")
        def bare(h: str) -> str:
            return nice_title(re.sub(r"\s*\((BOYS|GIRLS)\)\s*", "", h, flags=re.I))
        if rows[0].get("_mode") == "hall" and halls:
            return "\n".join(f"**{bare(h)}** is a **{_hall_gender(h) or 'mixed'}** hostel." for h in halls) + src
        girls = [bare(h) for h in halls if _hall_gender(h) == "girls'"]
        boys = [bare(h) for h in halls if _hall_gender(h) == "boys'"]
        return (f"**Girls' hostels:** {', '.join(girls) or 'none listed'}\n\n**Boys' hostels:** {', '.join(boys) or 'none listed'}"
                + src)
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
    hints = (ctx.plan.hints or {}) if ctx.plan else {}
    facts = ctx.facts
    if hints.get("lab"):
        with_lab = [f for f in facts if "lab" in (f.data.get("types") or [])]
        if not with_lab:
            return "None of your courses has a lab session in the current timetable." + source_line("your live timetable")
        return (f"**{len(with_lab)} of your {len(facts)} courses** have labs:\n\n"
                + "\n".join(f"- **{nice_title(f.data['course_name'])}** ({f.data['course_code']})"
                             + (f" — {join_names(f.data['faculty'])}" if f.data.get("faculty") else "") for f in with_lab)
                + source_line("your live timetable"))
    if hints.get("credits"):
        lines, total, known = [], 0, 0
        docs = set()
        for f in facts:
            c, cur = f.data, f.data.get("curriculum")
            credit = c.get("credits") if c.get("credits") is not None else (cur or {}).get("credits")
            if credit is not None:
                total += int(credit)
                known += 1
            if cur:
                docs.add(cur["document_title"])
            lines.append(f"- **{nice_title(c['course_name'])}** ({c['course_code']}) — "
                         + (f"**{credit} credits**" if credit is not None else "credits not found in your curriculum"))
        head = f"Your {len(facts)} courses this semester"
        head += f" add up to **{total} credits**:" if known == len(facts) else f" ({known} with credits on file):"
        return head + "\n\n" + "\n".join(lines) + source_line("your live timetable", *sorted(docs))
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
    if re.search(r"\b(advis[oe]r|class\s+teacher|mentor)\b", q):
        return ("ORION doesn't have faculty-advisor assignments yet, so I can't tell you who yours is — your "
                "department office or CR will know." + source_line("your profile"))
    if "semester" in q or "year" in q:
        sem = p.get("semester")
        year = (int(sem) + 1) // 2 if sem else None
        ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(year or 0, "")
        asked = re.search(r"\b(first|second|third|fourth|final|1st|2nd|3rd|4th)[\s-]+year\b", q)
        if asked and year:
            want = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "final": 4}[asked.group(1)]
            return (("Yes" if want == year else "No") + f" — you're in semester {sem}, which is your **{ordinal} year**."
                    + source_line("your profile"))
        return (f"You're in **semester {sem}**" + (f" — your **{ordinal} year**." if ordinal else ".")) + source_line("your profile")
    if "department" in q or "branch" in q:
        return f"Your department is **{dept}**." + source_line("your profile")
    lines = [f"- Semester **{p.get('semester')}**, section **{p.get('section')}**",
             f"- {p.get('programme')} · {dept}"]
    if p.get("regulations"):
        lines.append(f"- Regulations: {p['regulations']}")
    return "Here's what I have for you:\n\n" + "\n".join(lines) + source_line("your profile")


def _room_key(r: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (r or "").upper())


def compose_classroom(ctx: GroundedContext) -> str:
    room = next((f.data for f in ctx.facts if f.data.get("_classroom")), None)
    nxt = next((f.data for f in ctx.facts if f.data.get("_role")), None)
    hints = (ctx.plan.hints or {}) if ctx.plan else {}
    src = source_line("classroom allocation, Odd semester 2026" if room else None)
    asked = hints.get("room")
    if asked:
        if not room:
            return (f"I don't have a classroom allocation on file for your section, so I can't confirm whether "
                    f"**{asked}** is yours. The timetable doesn't list rooms either.")
        if _room_key(room["room_no"]) == _room_key(asked):
            return f"Yes — **{room['room_no']}** is your section's classroom this semester." + src
        return (f"No — your section's classroom this semester is **{room['room_no']}**, not {asked}. "
                "(Labs are held in the labs, not the classroom.)" + src)
    if hints.get("lab"):
        labs = _merge_slots([f.data for f in ctx.facts if f.data.get("_lab")])
        text = "The timetable doesn't list lab rooms, so I can't tell you which lab to go to — ask your lab faculty or CR."
        if labs:
            text += "\n\nYour labs this week:\n" + "\n".join(
                f"- {_DAYS.get(e.get('day_of_week'), '')} {fmt_range(e['start_time'], e['end_time'])} · {entry_label(e)}"
                + (f" — {join_names(e['faculty_names'])}" if e.get("faculty_names") else "") for e in labs)
        if room:
            text += f"\n\nYour section's classroom (for lectures) is **{room['room_no']}**."
        return text + source_line("your live timetable", "classroom allocation, Odd semester 2026" if room else None)
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

def _cohort_label(
    title: str, passage_cohort: Optional[str], own_family: Optional[str], document_type: Optional[str] = None
) -> str:
    """`passage_cohort` is the cohort the RETRIEVED passage actually belongs
    to; `own_family` is the caller's own. They can differ when the question
    explicitly named a different cohort (router.detect_cohort_reference) —
    saying "which apply to you" in that case would be exactly the CLAUDE.md
    §20 violation this whole path exists to prevent, so the two are compared
    rather than assuming a passage is always the caller's own."""
    if document_type != "regulations":
        return f"From the **{title}**"
    if own_family and passage_cohort and passage_cohort == own_family:
        return f"Under the **{title}**, which apply to you"
    if own_family and passage_cohort and passage_cohort != own_family:
        return f"Under the **{title}** (not your own regulations — you're on the {own_family} cohort)"
    if own_family:
        return f"Under the **{title}**"
    return f"Under the **{title}**"


# Confidence (share of the question's own key terms the chosen clause
# covers, documents.best_passages) needed to quote a passage as the answer.
_QUOTE_CONFIDENCE = 0.34
# Below this, the passage is not shown at all — not even hedged.
_MIN_RELEVANCE = 0.20
# A question the router recognised no pattern for at all reaches document
# search as a last resort; there is no independent signal that it is even a
# document question, so a near-miss passage is far likelier to be unrelated.
# It has to clear the full quoting bar or ORION says it doesn't have it.
_FALLBACK_MIN_RELEVANCE = _QUOTE_CONFIDENCE
# Meaning check (hybrid search, documents.search). Measured on the live
# corpus 2026-09-28: every relevant chosen passage scored 0.64-0.78; every
# irrelevant one was either absent from the semantic results or <= 0.55.
_VEC_NOT_ABOUT_IT = 0.62
_VEC_CLEARLY_ABOUT_IT = 0.70


def semantic_verdict(passage: documents.Passage, snippets: list) -> Optional[str]:
    """"reject" / "accept" / None (no opinion) for a chosen passage, from the
    vector similarity of its chunk — None when vector search didn't run."""
    if not any(getattr(sn, "vector_similarity", None) is not None for sn in snippets):
        return None
    vs = passage.vector_similarity
    if vs is None or vs < _VEC_NOT_ABOUT_IT:
        return "reject"
    if vs >= _VEC_CLEARLY_ABOUT_IT:
        return "accept"
    return None


# A positive signal from the router that this really is a document
# question: it recognised a hostel/anti-ragging/procedure/regulation topic,
# or the question named a cohort. Without one of these, reaching document
# search only means nothing else matched.
_DOCUMENT_SIGNALS = ("category", "document_type", "overview", "cohort_ref", "semantic")


def _is_document_question(plan_hints: dict[str, str]) -> bool:
    return any(plan_hints.get(k) for k in _DOCUMENT_SIGNALS)


def _relevance_floor(plan_hints: dict[str, str]) -> float:
    """Below this, nothing is shown. A question the router only *guessed*
    was a document question has to clear the full quoting bar."""
    return _MIN_RELEVANCE if _is_document_question(plan_hints) else _FALLBACK_MIN_RELEVANCE


def _citation(p: documents.Passage) -> str:
    sec = p.section_title or ""
    if not (re.match(r"^(R\.)?\d", sec) or (sec and len(sec) < 60 and not sec.isupper())):
        sec = ""
    if re.match(r"^\d", sec):
        sec = f"rule {sec}"
    return ", ".join(x for x in (p.document_title, sec, f"p. {p.page}" if p.page else None) if x)


def _compose_cohort_comparison(
    ctx: GroundedContext, own_family: str, other_cohort: str
) -> tuple[str, float, list[documents.Passage]]:
    """Both cohorts' rules, shown side by side, for a question that
    explicitly asks how they differ ("is the 2026 rule different from
    mine?") — never blends them into one answer or silently substitutes one
    for the other (CLAUDE.md §20)."""
    own_snips = [s for s in ctx.snippets if s.cohort == own_family]
    other_snips = [s for s in ctx.snippets if s.cohort == other_cohort]
    # The raw comparison phrasing ("...different for the 2026 admission
    # batch compared to mine?") scores badly against the actual rule text,
    # which never says "2026"/"batch"/"compared" — strip that scaffolding so
    # both sides are judged on the real subject (e.g. "attendance").
    topic_query = router.strip_cohort_noise(ctx.query)
    own_passages, own_conf = documents.best_passages(topic_query, own_snips) if own_snips else ([], 0.0)
    other_passages, other_conf = documents.best_passages(topic_query, other_snips) if other_snips else ([], 0.0)

    def block(label: str, passages: list[documents.Passage], confidence: float) -> str:
        if not passages or confidence < 0.34:
            return f"**{label}:** I couldn't find a specific rule for this cohort in the documents I have."
        p = passages[0]
        quote = "\n>\n".join(f"> {line}" for line in _quote_lines(p.text))
        return f"**{label}** ({p.document_title}):\n\n{quote}" + source_line(_citation(p))

    text = f"{block(f'Your cohort ({own_family})', own_passages, own_conf)}\n\n{block(other_cohort, other_passages, other_conf)}"
    passages = own_passages[:1] + other_passages[:1]
    confidence = max(own_conf, other_conf)
    return text, confidence, passages


# Words that say what kind of answer is wanted, not what it's about.
_GENERIC_ASK = {
    "about", "apply", "applying", "application", "obtain", "getting", "procedure", "process", "allowed", "permitted",
    "student", "students", "college", "campus", "institute", "iiitk", "kottayam", "during", "should", "would",
    "could", "there", "their", "which", "where", "these", "those", "maximum", "minimum", "number", "details",
    "information", "explain", "tell", "means", "meaning", "happens", "happen", "someone", "anyone", "people",
    "person", "within", "before", "after", "without", "through", "rules", "regulation", "regulations", "policy",
    "policies", "guidelines", "allowed", "possible", "require", "required", "requirement", "requirements",
    "please", "exactly", "really", "semester", "course", "courses", "class", "classes", "first", "second", "third",
    "fourth", "final", "batch", "document", "documents", "section", "things", "thing", "other", "different",
    "total", "today", "tomorrow", "right", "being", "doing", "using", "going", "getting", "taking", "making",
}


def _unmentioned_terms(query: str, snippets: list) -> list[str]:
    """Specific words of the question that no retrieved passage contains
    (prefix match, so "timings" ~ "timing"), unless the synonym table maps
    them to wording the documents use."""
    text = " ".join((getattr(s, "content", "") or "").lower() for s in snippets)
    if not text:
        return []
    out = []
    for w in dict.fromkeys(re.findall(r"[a-z]{5,}", query.lower())):
        if w in _GENERIC_ASK or w in documents._STOP or documents.expand_query(w)[1]:
            continue
        if w[:5] not in text:
            out.append(w)
    return out


def compose_documents(ctx: GroundedContext, cohort_family: Optional[str]) -> tuple[str, float, list[documents.Passage]]:
    plan_hints = ctx.plan.hints or {}
    cohort_ref = plan_hints.get("cohort_ref")
    if cohort_ref and plan_hints.get("cohort_compare") == "yes" and cohort_family and cohort_ref != cohort_family:
        return _compose_cohort_comparison(ctx, cohort_family, cohort_ref)

    passages, confidence = documents.best_passages(ctx.query, ctx.snippets)
    if not passages:
        return (_no_document_answer(ctx), 0.0, [])
    p = passages[0]
    source = _citation(p)
    quote = "\n>\n".join(f"> {line}" for line in _quote_lines(p.text))
    # Relevance floor. Full-text search always returns its best row, however
    # weak — without a floor, "Where is Dr. X's cabin?" came back quoting an
    # anti-ragging committee memo, and a free-period question came back with
    # curriculum text that merely contained the word "Lectures". A retrieved
    # passage that doesn't actually cover the question is worse than saying
    # so: it reads as sourced and authoritative while being unrelated.
    verdict = semantic_verdict(p, ctx.snippets)
    missing = _unmentioned_terms(ctx.query, ctx.snippets) if verdict != "accept" else []
    if missing:
        # "bonafide certificate", "library timings": the documents never
        # mention the thing asked about, so a passage that shares the other
        # word ("certificate", "library") would be a confident wrong answer.
        return (f"The campus documents I have don't mention **{' '.join(missing[:2])}**, so I can't answer that "
                "from them. The Academic Office (or the office concerned) can help." + source_line("campus documents"),
                0.0, [])
    if verdict == "reject":
        # Shares words with the question but isn't about it ("examination
        # hall rules" -> a textbook by Prentice Hall). Worse than silence.
        return (_no_document_answer(ctx), 0.0, [])
    if verdict == "accept":
        confidence = max(confidence, _QUOTE_CONFIDENCE)
    if confidence < _relevance_floor(plan_hints):
        return (_no_document_answer(ctx), confidence, [])
    if confidence < _QUOTE_CONFIDENCE:
        text = ("I couldn't find a rule that answers that directly. The closest thing in the documents I have is "
                f"this, from the **{p.document_title}**:\n\n{quote}\n\nIf that's not it, the Academic Office can help.")
        return text + source_line(source), confidence, passages
    label = _cohort_label(p.document_title, p.cohort, cohort_family, p.document_type)
    if plan_hints.get("cross_cohort") == "yes" and cohort_family and p.cohort != cohort_family:
        own = {"21-25": "UG Regulations (2021-25 batch)", "26-onwards": "UG Regulations (2026 admission onwards)"}.get(
            cohort_family, "your regulations")
        label = (f"Your regulations (**{own}**) don't have a rule on this. The **{p.document_title}** do — they "
                 "don't formally apply to your batch, but here's what they say for reference")
    return f"{label}:\n\n{quote}" + source_line(source), confidence, passages


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
    return ("I couldn't find anything about that in the campus documents I have (UG regulations, curricula, hostel "
            "rules, anti-ragging documents and verification procedures), so I won't guess. The Academic Office or "
            "your faculty advisor can confirm.")


# ---------------------------------------------------------------- out of scope

_OUT_OF_SCOPE = {
    "grades": ("I can't see grades, marks or CGPA — I don't store personal academic records. Your results are on "
               "the institute's academic portal, or ask your faculty advisor. I can explain how CGPA is calculated or "
               "tell you when results are published."),
    "attendance": ("I don't track your attendance — your course faculty maintain it, and you can check it with them. "
                   "I can tell you the attendance rules if that helps (\"What is the attendance requirement?\")."),
    "fees": ("I don't handle fee payments or balances — use the institute's official payment channels or the "
             "Accounts section. I can tell you fee payment deadlines from the academic calendar."),
    "general": ("I'm RION, ORION's campus assistant for IIIT Kottayam, so I stick to campus information — your "
                "classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations."),
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
    if intent == StructuredIntent.WORKING_DAY:
        return compose_working_day(ctx)
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
    if intent == StructuredIntent.FACULTY_DIRECTORY:
        return compose_faculty_directory(ctx)
    if intent == StructuredIntent.CONVERSATION:
        return "I don't have an earlier answer in this conversation to refer to."
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
        asked = re.search(r"matching '([^']+)'", warning)
        name = f" called **{asked.group(1)}**" if asked and len(asked.group(1)) < 40 else ""
        return (f"I couldn't find a course{name} in ORION's course catalogue — it only has the courses in this "
                "semester's timetables. Try the course code (for example ICS 211) or the full course name.")
    if "designation found" in warning:
        role = re.search(r"'([^']+)' designation", warning)
        label = {"librarian": "a librarian", "iqac": "an IQAC coordinator"}.get(role.group(1) if role else "", "anyone in that role")
        return (f"The faculty directory in ORION doesn't list {label}. The administrative office can point you to the "
                "right person.")
    if "no faculty found" in warning:
        from . import campus  # lazy: campus pulls in retrieval

        words = campus.query_name_words(ctx.plan.topic_text or ctx.query) if ctx.plan else []
        who = f" named **{' '.join(w.capitalize() for w in words)}**" if words else " with that name"
        return (f"I couldn't find anyone{who} in the faculty directory. If they're new or visiting they may not be "
                "listed yet — try their full name or surname.")
    if "no upcoming class" in warning:
        return "I couldn't find any upcoming classes in your timetable."
    if "profile" in warning:
        return "I don't have a student profile for your account yet. Complete registration so I can show your timetable."
    return "I couldn't find that in the campus data I have." + (f" ({warning})" if warning else "")
