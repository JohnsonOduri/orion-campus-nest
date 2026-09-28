"""Deterministic checks for CR uploads — no model involved.

Everything here runs on plain text (a PDF's text layer, OCR output, or what
the CR typed) and decides the things that must not depend on an LLM:

  - which announcement category a notice falls in, and therefore whether a
    CR may publish it straight away (academic, for their own class) or it
    goes to an admin (events, clubs, anything else);
  - whether the text carries sensitive data (CLAUDE.md §22) — if it does,
    it is never auto-published;
  - the date/time a notice is about ("quiz on 12 Oct at 10 AM").

The same category list is enforced again in Postgres
(orion_is_academic_category + the announcements insert policy), so this
module decides what to *suggest*; the database decides what is *allowed*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Optional

# Must match public.orion_is_academic_category() in
# supabase/migrations/20260928150000_cr_upload_workflow.sql.
ACADEMIC_CATEGORIES = ("QUIZ", "EXAM", "ASSIGNMENT", "CLASS_UPDATE", "DEADLINE", "ACADEMIC")
OTHER_CATEGORIES = ("EVENT", "CLUB", "OFFICIAL", "GENERAL", "ADVERTISEMENT")
CATEGORIES = ACADEMIC_CATEGORIES + OTHER_CATEGORIES

# Longest auto-published announcement lifetime; the RLS policy allows 62
# days so a date picked in another timezone can't trip it.
MAX_AUTO_DAYS = 60
DEFAULT_AUTO_DAYS = 14


def is_academic(category: Optional[str]) -> bool:
    return (category or "").upper() in ACADEMIC_CATEGORIES


# ------------------------------------------------------------- category

# First match wins, so the specific kinds come before the general
# "academic" catch-all.
_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("QUIZ", re.compile(r"\b(quiz(zes)?|surprise\s+test|class\s+test|mcq\s+test)\b", re.I)),
    ("EXAM", re.compile(r"\b(mid[\s-]?sem(ester)?|end[\s-]?sem(ester)?|exam(ination)?s?|viva(\s+voce)?|re[\s-]?test|internal\s+test)\b", re.I)),
    ("ASSIGNMENT", re.compile(r"\b(assignments?|home\s*work|lab\s+records?|submit(ted|ting|ssion)?|report\s+(is\s+)?due)\b", re.I)),
    ("CLASS_UPDATE", re.compile(
        r"\b(class(es)?|lecture|lab|tutorial|session)s?\b[^.\n]{0,40}\b(cancel+ed|cancel+ation|resched|postponed?|preponed?|shifted|moved|suspended)"
        r"|\b(extra|additional|make[\s-]?up|substitute|compensat\w*)\s+(class|lecture|lab|session)"
        r"|\bno\s+(class|classes|lecture|lab)\b|\broom\s+change", re.I)),
    ("DEADLINE", re.compile(r"\b(deadline|last\s+date|due\s+(date|by|on)|closes\s+on|registration\s+closes)\b", re.I)),
]
_ACADEMIC_RE = re.compile(
    r"\b(course|lecture|syllabus|attendance|project\s+review|tutorial|lab|practical|semester|"
    r"elective|credits?|grades?|marks|faculty\s+advisor|hod|class\s+room|timetable)\b", re.I)
_CLUB_RE = re.compile(r"\bclubs?\b", re.I)
_EVENT_RE = re.compile(r"\b(fest|hackathon|competition|workshop|webinar|guest\s+(talk|lecture)|cultural|sports\s+meet|"
                       r"celebration|orientation|seminar\s+on|symposium|meet[\s-]?up)\b", re.I)
_OFFICIAL_RE = re.compile(r"\b(circular|office\s+order|notification\s+no|registrar|dean|director)\b", re.I)
_AD_RE = re.compile(r"(\d+\s?%\s*off|\bdiscount|\bcoupon|\bpromo\s*code|\bbuy\s+now|\blimited\s+(seats|offer)|"
                    r"\benrol+\s+now|\bpaid\s+(course|internship)|\bflat\s+\d+|\bcashback|\bsponsored)", re.I)


def classify_category(text: str) -> str:
    """Suggested announcement category for `text`. An advertisement is only
    called one when nothing academic is in it too (CLAUDE.md §23: promotional
    wording doesn't disqualify an official notice)."""
    t = text or ""
    for label, pattern in _CATEGORY_RULES:
        if pattern.search(t):
            return label
    academic = bool(_ACADEMIC_RE.search(t))
    if _AD_RE.search(t) and not academic:
        return "ADVERTISEMENT"
    if _CLUB_RE.search(t):
        return "CLUB"
    if _EVENT_RE.search(t):
        return "EVENT"
    if academic:
        return "ACADEMIC"
    if _OFFICIAL_RE.search(t):
        return "OFFICIAL"
    return "GENERAL"


# ------------------------------------------------------ sensitive data

_SENSITIVE: list[tuple[str, re.Pattern[str]]] = [
    ("an Aadhaar-like 12-digit number", re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")),
    ("a PAN number", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("bank account details", re.compile(r"\b(a/?c\s*(no|number)|account\s+(no|number)|ifsc)\b|\b[A-Z]{4}0[A-Z0-9]{6}\b", re.I)),
    ("a password or OTP", re.compile(r"\b(password|passcode|pass\s*word|otp|pin)\s*[:=-]\s*\S+", re.I)),
    ("an API key or token", re.compile(r"\b(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]+)")),
    ("a personal phone number", re.compile(r"(?<!\d)(\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("medical or disciplinary details", re.compile(r"\b(diagnos\w+|medical\s+(report|history)|disciplinary\s+action\s+against|suspended\s+student)\b", re.I)),
]


def sensitive_findings(text: str) -> list[str]:
    """Human-readable list of what looks sensitive in `text` (empty = clean).
    Anything found here keeps an announcement away from auto-publishing."""
    found = []
    for label, pattern in _SENSITIVE:
        if pattern.search(text or ""):
            found.append(label)
    return found


# -------------------------------------------------------- dates / times

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DMY_WORDS = re.compile(rf"\b(\d{{1,2}})(st|nd|rd|th)?\s*(of\s+)?{_MONTH_RE}\s*,?\s*(\d{{4}})?", re.I)
_MDY_WORDS = re.compile(rf"\b{_MONTH_RE}\s+(\d{{1,2}})(st|nd|rd|th)?\s*,?\s*(\d{{4}})?", re.I)
_NUMERIC = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_REL = re.compile(r"\b(day\s+after\s+tomorrow|tomorrow|today|tonight)\b", re.I)
_WEEKDAY = re.compile(r"\b(next\s+|this\s+|on\s+|coming\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)


def _year_for(month: int, day: int, today: date) -> int:
    """A date written without a year means the next time it comes round
    (within the academic year), not a date months in the past."""
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    return today.year + 1 if candidate < today - timedelta(days=60) else today.year


def _safe_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract_date(text: str, today: date) -> Optional[date]:
    """The first date the text names, or None. Explicit dates beat relative
    words; Indian day-first order for numeric dates (12/10 = 12 October)."""
    t = text or ""
    m = _ISO.search(t)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DMY_WORDS.search(t)
    if m:
        mon = _MONTHS[m.group(4)[:3].lower()]
        day = int(m.group(1))
        year = int(m.group(5)) if m.group(5) else _year_for(mon, day, today)
        return _safe_date(year, mon, day)
    m = _MDY_WORDS.search(t)
    if m:
        mon = _MONTHS[m.group(1)[:3].lower()]
        day = int(m.group(2))
        year = int(m.group(4)) if m.group(4) else _year_for(mon, day, today)
        return _safe_date(year, mon, day)
    m = _NUMERIC.search(t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        return _safe_date(y, mo, d)
    m = _REL.search(t)
    if m:
        word = m.group(1).lower()
        return today + timedelta(days={"today": 0, "tonight": 0, "tomorrow": 1}.get(word, 2))
    m = _WEEKDAY.search(t)
    if m:
        target = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(m.group(2).lower()) + 1
        delta = (target - today.isoweekday()) % 7
        if (m.group(1) or "").strip().lower() == "next" and delta == 0:
            delta = 7
        return today + timedelta(days=delta)
    return None


def extract_time(text: str) -> Optional[time]:
    m = _TIME.search(text or "")
    if not m:
        return None
    if m.group(3):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        pm = m.group(3).lower().startswith("p")
        if h > 12 or mi > 59:
            return None
        h = (h % 12) + (12 if pm else 0)
        return time(h, mi)
    return time(int(m.group(4)), int(m.group(5)))


# ------------------------------------------------------------ title

_GENERIC_TITLE_RE = re.compile(r"(important\s+)?(notice|announcement|circular|update|info(rmation)?)[\s:.!-]*", re.I)


def suggest_title(text: str, category: str) -> str:
    """First meaningful line, trimmed — the CR edits it anyway."""
    for line in (text or "").splitlines():
        line = re.sub(r"\s+", " ", line).strip(" -•*#:\t")
        if len(line) >= 4 and not _GENERIC_TITLE_RE.fullmatch(line):
            return line[:120]
    return {"QUIZ": "Quiz", "EXAM": "Exam", "ASSIGNMENT": "Assignment", "CLASS_UPDATE": "Class update",
            "DEADLINE": "Deadline"}.get(category, "Announcement")


@dataclass
class AnnouncementDraft:
    title: str
    content: str
    category: str
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    valid_until: Optional[str] = None
    sensitive: list[str] = field(default_factory=list)

    @property
    def auto_publish(self) -> bool:
        return is_academic(self.category) and not self.sensitive

    def to_dict(self) -> dict:
        return {
            "title": self.title, "content": self.content, "category": self.category,
            "event_date": self.event_date, "event_time": self.event_time, "valid_until": self.valid_until,
            "sensitive": self.sensitive, "auto_publish": self.auto_publish,
        }


def default_valid_until(event_date: Optional[date], today: date) -> date:
    """Visible until the day after the event, else two weeks; never past
    the auto-publish ceiling."""
    until = (event_date + timedelta(days=1)) if event_date and event_date >= today else today + timedelta(days=DEFAULT_AUTO_DAYS)
    return min(until, today + timedelta(days=MAX_AUTO_DAYS))


def draft_announcement(text: str, today: date, *, title: Optional[str] = None,
                       category: Optional[str] = None) -> AnnouncementDraft:
    body = (text or "").strip()
    cat = (category or classify_category(body)).upper()
    if cat not in CATEGORIES:
        cat = classify_category(body)
    ev = extract_date(body, today)
    tm = extract_time(body)
    if title and _GENERIC_TITLE_RE.fullmatch(title.strip()):
        title = None  # "NOTICE" as a heading says nothing; use the first real line
    return AnnouncementDraft(
        title=(title or suggest_title(body, cat)).strip()[:120],
        content=body,
        category=cat,
        event_date=ev.isoformat() if ev else None,
        event_time=tm.strftime("%H:%M") if tm else None,
        valid_until=default_valid_until(ev, today).isoformat(),
        sensitive=sensitive_findings(body),
    )


# --------------------------------------------------- upload kind (rules)

_DAY_NAME_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat)(day|sday|nesday|rsday|urday)?\b", re.I)
_TIME_RANGE_RE = re.compile(r"\d{1,2}[.:]\d{2}\s*(am|pm)?\s*[-–—to]+\s*\d{1,2}[.:]\d{2}", re.I)
_CODE_RE = re.compile(r"\b[A-Z]{2,4}\s?\d{3}\b")


def looks_like_timetable(text: str) -> bool:
    """A weekly grid: most weekday names, several time ranges and course codes."""
    t = text or ""
    days = {m.group(1).lower() for m in _DAY_NAME_RE.finditer(t)}
    return len(days) >= 4 and len(_TIME_RANGE_RE.findall(t)) >= 3 and len(_CODE_RE.findall(t)) >= 4
