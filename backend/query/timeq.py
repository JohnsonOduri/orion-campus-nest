"""Time questions answered precisely: "Am I free at 2?", "Do I have a free
hour between 2 and 4?", "Am I free after 3pm?", "What's my longest free
slot today?", "Is the mess open now?", "When does lunch end?".

Before 2026-09-28 every one of these got the same full-day dump
(AI-Tests/ WhatsApp 14.52.42*, 14.56.01*). This module turns the question
into a constraint once (`parse`, pure, used by the router) and answers that
constraint from the day's periods / meal timings (`free_*`, `mess_*`, pure,
used by the composer). No I/O, no model.

Clock conventions for bare hours ("at 2", "between 2 and 4"): 1–7 mean
afternoon/evening (no class starts at 2 AM), 8–11 morning, 12 noon.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# ------------------------------------------------------------- clock parsing

_CLOCK = r"(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?|noon)?"
_AT_RE = re.compile(rf"\b(?:at|@|around)\s+{_CLOCK}(?![\d:])", re.I)
_BETWEEN_RE = re.compile(rf"\b(?:between|from)\s+{_CLOCK}\s*(?:and|to|till|until|-|–)\s*{_CLOCK}", re.I)
_AFTER_RE = re.compile(rf"\b(?:after|past|from)\s+{_CLOCK}(?![\d:])", re.I)
_BEFORE_RE = re.compile(rf"\b(?:before|until|till)\s+{_CLOCK}(?![\d:])", re.I)
_NOW_RE = re.compile(r"\b(right\s+now|now|currently|at\s+the\s+moment|at\s+this\s+moment)\b", re.I)
_LONGEST_RE = re.compile(r"\b(longest|biggest|largest|longer|maximum|max|most)\b", re.I)
_DURATION_RE = re.compile(r"\b(an?|one|two|three|\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)\b", re.I)
_FREE_HOUR_RE = re.compile(r"\bfree\s+hour\b", re.I)
_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}

# Named parts of the day, as windows in minutes.
PARTS_OF_DAY = {
    "morning": (8 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, 20 * 60),
    "before lunch": (8 * 60, 12 * 60),
    "after lunch": (13 * 60 + 30, 17 * 60),
}
_PART_RE = re.compile(r"\b(before\s+lunch|after\s+lunch|morning|afternoon|evening)\b", re.I)


def clock_minutes(hour: str, minute: Optional[str], meridiem: Optional[str]) -> Optional[int]:
    h, m = int(hour), int(minute or 0)
    if h > 23 or m > 59:
        return None
    mer = (meridiem or "").lower().replace(".", "")
    if mer == "noon":
        return 12 * 60
    if mer.startswith("p") and h < 12:
        h += 12
    elif mer.startswith("a") and h == 12:
        h = 0
    elif not mer and 1 <= h <= 7:
        h += 12  # "at 2" in a college day is 2 PM
    return h * 60 + m


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def to_minutes(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", str(value))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def fmt_clock(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def fmt_span(start: int, end: int) -> str:
    return f"{fmt_clock(start)}–{fmt_clock(end)}"


def fmt_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} hour{'s' if h > 1 else ''}" if h else f"{m} min"


@dataclass(frozen=True)
class TimeAsk:
    """What a time question constrains. All times in minutes after midnight."""

    at: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    min_minutes: Optional[int] = None
    longest: bool = False
    now: bool = False
    part: Optional[str] = None  # "morning", "afternoon", ...

    def hints(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.at is not None:
            out["at"] = hhmm(self.at)
        if self.start is not None:
            out["from"] = hhmm(self.start)
        if self.end is not None:
            out["to"] = hhmm(self.end)
        if self.min_minutes:
            out["min"] = str(self.min_minutes)
        if self.longest:
            out["longest"] = "yes"
        if self.now:
            out["now"] = "yes"
        if self.part:
            out["part"] = self.part
        return out

    @classmethod
    def from_hints(cls, hints: dict) -> "TimeAsk":
        return cls(at=to_minutes(hints.get("at")), start=to_minutes(hints.get("from")), end=to_minutes(hints.get("to")),
                   min_minutes=int(hints["min"]) if hints.get("min") else None, longest=hints.get("longest") == "yes",
                   now=hints.get("now") == "yes", part=hints.get("part"))

    @property
    def is_specific(self) -> bool:
        return any(v is not None for v in (self.at, self.start, self.end)) or self.longest or self.now or bool(self.min_minutes)


def parse(question: str) -> TimeAsk:
    """The time constraint a question states (empty TimeAsk if none)."""
    q = question or ""
    at = start = end = min_minutes = None
    part = None
    m = _BETWEEN_RE.search(q)
    if m:
        a = clock_minutes(m.group(1), m.group(2), m.group(3) or m.group(6))
        b = clock_minutes(m.group(4), m.group(5), m.group(6))
        # "between 11 and 1": 11 AM to 1 PM; keep the order sensible.
        if a is not None and b is not None:
            if b <= a and b + 12 * 60 > a:
                b += 12 * 60 if b < 12 * 60 else 0
            start, end = a, b
    if start is None:
        pm = _PART_RE.search(q)
        if pm:
            part = re.sub(r"\s+", " ", pm.group(1).lower())
            start, end = PARTS_OF_DAY[part]
    if start is None and end is None:
        after = _AFTER_RE.search(q)
        before = _BEFORE_RE.search(q)
        if after:
            start = clock_minutes(after.group(1), after.group(2), after.group(3))
        if before:
            end = clock_minutes(before.group(1), before.group(2), before.group(3))
        if start is None and end is None:
            m = _AT_RE.search(q)
            if m:
                at = clock_minutes(m.group(1), m.group(2), m.group(3))
    now = bool(_NOW_RE.search(q)) and at is None and start is None and end is None
    d = _DURATION_RE.search(q)
    if d:
        n = _NUM_WORDS.get(d.group(1).lower())
        amount = float(n if n is not None else d.group(1))
        min_minutes = int(amount * (60 if d.group(2).lower().startswith("h") else 1))
    elif _FREE_HOUR_RE.search(q):
        min_minutes = 60
    return TimeAsk(at=at, start=start, end=end, min_minutes=min_minutes,
                   longest=bool(_LONGEST_RE.search(q)), now=now, part=part)


# -------------------------------------------------------------- free time

# A gap shorter than this is walking time between rooms, not free time.
MIN_GAP = 10


@dataclass(frozen=True)
class Busy:
    start: int
    end: int
    label: str


def busy_blocks(entries: list[dict], label_of) -> list[Busy]:
    blocks = []
    for e in entries:
        s, t = to_minutes(e.get("start_time")), to_minutes(e.get("end_time"))
        if s is not None and t is not None and t > s:
            blocks.append(Busy(s, t, label_of(e)))
    return sorted(blocks, key=lambda b: (b.start, b.end))


def free_windows(blocks: list[Busy], day_start: int, day_end: int) -> list[tuple[int, int]]:
    """Free intervals within [day_start, day_end] (gaps < MIN_GAP ignored)."""
    free, cursor = [], day_start
    for b in blocks:
        if b.end <= day_start or b.start >= day_end:
            continue
        if b.start - cursor >= MIN_GAP:
            free.append((cursor, min(b.start, day_end)))
        cursor = max(cursor, b.end)
    if day_end - cursor >= MIN_GAP:
        free.append((cursor, day_end))
    return free


def busy_at(blocks: list[Busy], minute: int) -> list[Busy]:
    return [b for b in blocks if b.start <= minute < b.end]


def next_block(blocks: list[Busy], minute: int) -> Optional[Busy]:
    return next((b for b in blocks if b.start > minute), None)


def prev_block(blocks: list[Busy], minute: int) -> Optional[Busy]:
    ended = [b for b in blocks if b.end <= minute]
    return max(ended, key=lambda b: b.end) if ended else None


def _list_blocks(blocks: list[Busy]) -> str:
    return "; ".join(f"{fmt_span(b.start, b.end)} {b.label}" for b in blocks)


def answer_free(blocks: list[Busy], ask: TimeAsk, phrase: str, now_minute: Optional[int] = None) -> str:
    """The answer to exactly what was asked. `phrase` is "today" /
    "tomorrow" / "on Friday". `now_minute` is used for "now" questions."""
    if not blocks:
        return f"You have no classes {phrase}, so you're free all day."
    first, last = blocks[0].start, max(b.end for b in blocks)

    if ask.now or ask.at is not None:
        t = now_minute if ask.now and now_minute is not None else ask.at
        when = "right now" if ask.now else f"at {fmt_clock(t)}"
        here = busy_at(blocks, t)
        if here:
            b = here[0]
            ends = max(x.end for x in here)
            return f"No — {when} {phrase if not ask.now else ''} you have **{b.label}** ({fmt_span(b.start, b.end)}). You're free again from {fmt_clock(ends)}." \
                .replace("  ", " ").replace(" .", ".")
        nxt, prv = next_block(blocks, t), prev_block(blocks, t)
        free_from = prv.end if prv else None
        if nxt:
            span = f"from {fmt_clock(free_from)} " if free_from is not None else ""
            text = (f"Yes — you're free {when} {phrase if not ask.now else ''}. That free time runs {span}until "
                    f"{fmt_clock(nxt.start)}, when you have **{nxt.label}**.")
        else:
            text = f"Yes — you're free {when} {phrase if not ask.now else ''}. Your last class ends at {fmt_clock(last)}, so you're free for the rest of the day."
        return re.sub(r"\s{2,}", " ", text).replace(" .", ".")

    if ask.longest and ask.start is None and ask.end is None:
        between = free_windows(blocks, first, last)
        if not between:
            return (f"You don't have a break between classes {phrase} — they run back to back from "
                    f"{fmt_clock(first)} to {fmt_clock(last)}. You're free after {fmt_clock(last)}.")
        s, e = max(between, key=lambda w: (w[1] - w[0], -w[0]))
        text = f"Your longest free slot {phrase} is **{fmt_span(s, e)}** ({fmt_duration(e - s)})."
        others = [w for w in between if w != (s, e)]
        if others:
            text += " Other breaks: " + ", ".join(f"{fmt_span(a, b)} ({fmt_duration(b - a)})" for a, b in others) + "."
        text += f" After your last class ends at {fmt_clock(last)} you're free for the rest of the day."
        return text

    if ask.start is not None or ask.end is not None:
        lo = ask.start if ask.start is not None else min(first, 8 * 60)
        hi = ask.end if ask.end is not None else max(last, 23 * 60 + 59)
        label = (f"in the {ask.part}" if ask.part and ask.part in ("morning", "afternoon", "evening")
                 else ask.part if ask.part else
                 f"between {fmt_clock(lo)} and {fmt_clock(hi)}" if ask.start is not None and ask.end is not None
                 else f"after {fmt_clock(lo)}" if ask.start is not None else f"before {fmt_clock(hi)}")
        inside = [b for b in blocks if b.end > lo and b.start < hi]
        free = free_windows(blocks, lo, hi)
        need = ask.min_minutes
        if need:
            fits = [w for w in free if w[1] - w[0] >= need]
            if fits:
                s, e = fits[0]
                text = f"Yes — you have **{fmt_span(s, e)}** free {phrase} ({fmt_duration(e - s)})."
            else:
                longest = max(free, key=lambda w: w[1] - w[0]) if free else None
                text = f"No — you don't have {fmt_duration(need)} free {label} {phrase}."
                if longest:
                    text += f" The most you get is {fmt_span(*longest)} ({fmt_duration(longest[1] - longest[0])})."
            if inside:
                text += f" Classes {label}: {_list_blocks(inside)}."
            return text
        if not inside:
            return f"Yes — you're free {label} {phrase}; no classes then."
        if not free:
            return f"No — you're busy {label} {phrase}: {_list_blocks(inside)}."
        def span(w: tuple[int, int]) -> str:
            # No end was asked for: the last window just runs on.
            return f"from {fmt_clock(w[0])} onwards" if ask.end is None and w[1] >= hi else fmt_span(*w)
        free_txt = ", ".join(f"**{span(w)}**" for w in free)
        return (f"{label[0].upper() + label[1:]} {phrase} you're free {free_txt}. "
                f"Busy with: {_list_blocks(inside)}.")

    between = free_windows(blocks, first, last)
    parts = []
    if first > 8 * 60 + 30:
        parts.append(f"before {fmt_clock(first)}")
    parts += [fmt_span(s, e) for s, e in between]
    parts.append(f"after {fmt_clock(last)}")
    listing = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    return f"You're free {phrase} {listing}.\n\nYour classes {phrase}: {_list_blocks(blocks)}."


# ------------------------------------------------------------------ mess

_MESS_OPEN_NOW_RE = re.compile(r"\b(open|serving|available|going\s+on)\b[^?]*\b(now|right\s+now|currently|at\s+the\s+moment)\b"
                               r"|\b(now|right\s+now|currently)\b[^?]*\b(open|serving)\b|\bis\s+(the\s+)?mess\s+open\b", re.I)
_MESS_OPEN_RE = re.compile(r"\b(open|opens|opening|start|starts|begin|begins)\b", re.I)
_MESS_CLOSE_RE = re.compile(r"\b(close|closes|closing|shut|end|ends|over|last\s+time|till\s+when|until\s+when)\b", re.I)
_MESS_TIME_RE = re.compile(r"\b(what\s+time|when|timings?|times?|hours|schedule|how\s+long|till|until|served\s+(from|at))\b", re.I)
_MENU_WORDS_RE = re.compile(r"\b(menu|what'?s|what\s+is|what\s+are|items?|dish|serve[sd]?\s+(for|in)|having|eat)\b", re.I)


def mess_time_question(q: str) -> Optional[str]:
    """"open_now" | "open" | "close" | "timing" | None (a menu question).
    "What's for lunch?" is about food; "When is lunch?" / "lunch timings" /
    "is the mess open now?" are about time."""
    if _MESS_OPEN_NOW_RE.search(q):
        return "open_now"
    timed = _MESS_TIME_RE.search(q)
    if not timed and not re.search(r"\b(open|close|closes|closing|opens)\b", q, re.I):
        return None
    if re.search(r"\bwhat'?s\s+for\b|\bwhat\s+is\s+for\b|\bmenu\b|\bwhat\s+(are|r)\s+we\s+having\b", q, re.I):
        return None
    if _MESS_CLOSE_RE.search(q):
        return "close"
    if _MESS_OPEN_RE.search(q):
        return "open"
    return "timing"


MEAL_ORDER = ["breakfast", "lunch", "snacks", "dinner"]


def answer_mess_time(timings: dict[str, tuple[int, int]], kind: str, meal: Optional[str],
                     now_minute: int) -> str:
    """`timings`: meal -> (start, end) minutes."""
    rows = [(m, *timings[m]) for m in MEAL_ORDER if m in timings]
    if not rows:
        return "I don't have the mess timings on file."
    table = " · ".join(f"{m.capitalize()} {fmt_span(s, e)}" for m, s, e in rows)
    if meal and meal in timings:
        s, e = timings[meal]
        name = meal.capitalize()
        if kind == "close":
            return f"{name} is served until **{fmt_clock(e)}** (it starts at {fmt_clock(s)})."
        if kind == "open":
            return f"{name} starts at **{fmt_clock(s)}** and is served until {fmt_clock(e)}."
        if kind == "open_now":
            if s <= now_minute < e:
                return f"Yes — {meal} is being served now, until **{fmt_clock(e)}**."
            return (f"No — {meal} is served {fmt_span(s, e)}." +
                    (f" It starts in {fmt_duration(s - now_minute)}." if now_minute < s else ""))
        return f"{name} is served **{fmt_span(s, e)}**."
    if kind == "open_now":
        current = next(((m, s, e) for m, s, e in rows if s <= now_minute < e), None)
        if current:
            m, s, e = current
            return f"Yes — the mess is open now: **{m}** is being served until **{fmt_clock(e)}**."
        upcoming = next(((m, s, e) for m, s, e in rows if s > now_minute), None)
        if upcoming:
            m, s, e = upcoming
            return (f"No — the mess is closed right now. It opens next for **{m}** at **{fmt_clock(s)}** "
                    f"(in {fmt_duration(s - now_minute)}).\n\nToday's timings: {table}.")
        return f"No — the mess has closed for the day (dinner ended at {fmt_clock(rows[-1][2])}). Breakfast is from {fmt_clock(rows[0][1])} tomorrow."
    if kind == "open":
        return f"The mess opens at **{fmt_clock(rows[0][1])}** for breakfast.\n\nTimings: {table}."
    if kind == "close":
        return (f"The mess closes at **{fmt_clock(rows[-1][2])}**, after dinner. Between meals it's closed — "
                f"timings: {table}.")
    return f"Mess timings: {table}."
