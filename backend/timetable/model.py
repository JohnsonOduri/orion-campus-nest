"""Canonical data model for timetable extraction results.

The normalizer's output shape is documented in Data/analysis.md §2.1 and the
task spec; all values trace back to the source PDF (no fabricated data).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------- constants

WEEKDAYS: dict[str, int] = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}

# Grid cells are either course entries or whole-grid non-course activities.
NON_COURSE_ACTIVITIES: dict[str, str] = {
    "sports/yoga/cultural activities": "sports",
    "coding club activities": "club_activity",
    "technical club activities": "club_activity",
    "sports": "sports",
    "yoga": "sports",
    "cultural activities": "club_activity",
}

VALID_ENTRY_TYPES = {
    "class",
    "lab",
    "tutorial",
    "seminar",
    "project",
    "club_activity",
    "sports",
    "break",
    "other",
}

TIME_RANGE_RE = re.compile(
    r"(\d{1,2})[.:]([0-5]\d)\s*(am|pm)?\s*[-–—]\s*(\d{1,2})[.:]([0-5]\d)\s*(am|pm)?",
    re.IGNORECASE,
)

COURSE_CODE_RE = re.compile(r"\b([IUE][A-Z]{2}\s?\d{3}|[A-Z]{2,4}\s?\d{3})\b")

CREDITS_RE = re.compile(r"\[(\d+)-(\d+)-(\d+)\]\s*(\d+)")

SECTION_HEADER_RE = re.compile(
    r"SEMESTER\s+(?P<semester>[IVX]+|\d+)\s+(?P<branch>.+?)\s+"
    r"BATCH\s*[-–—]\s*(?P<batch>[IVX]+|\d+)\s*(?:\[(?P<adm>[^\]]+)\])?",
    re.IGNORECASE,
)


# ------------------------------------------------------------ period headers

@dataclass(frozen=True)
class PeriodHeader:
    """A parsed period column header from a timetable grid."""

    slot_index: int
    start: Optional[str]  # "HH:MM" 24h, None when the PDF prints no time
    end: Optional[str]
    kind: str  # "teaching" | "break"
    raw: str = ""

    @property
    def is_time_derived(self) -> bool:
        return self.kind == "teaching" and self.start is None


def _to_24h(hour: int, minute: int, meridiem: Optional[str]) -> str:
    meridiem = (meridiem or "").lower()
    if meridiem == "pm" and hour != 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _scan_meridiem(text: str) -> Optional[str]:
    """Find an AM/PM token anywhere in the cluster text."""
    m = re.search(r"\b(AM|PM)\b", text, re.IGNORECASE)
    return m.group(1).lower() if m else None


def _range_24h(
    h1: int, m1: int, ap1: Optional[str], h2: int, m2: int, ap2: Optional[str]
) -> tuple[str, str]:
    """Convert a printed range to 24h, resolving missing meridiems safely.

    Word prints ranges like ``11.05-12.00 PM`` (crossing noon) with the
    meridiem only on the end time; naively inheriting PM for the start yields
    23:05. If applying the end's meridiem to the start makes start >= end,
    the start is the opposite meridiem.
    """
    ap1 = ap1.lower() if ap1 else None
    ap2 = ap2.lower() if ap2 else None
    if ap1 is None and ap2 is not None:
        if ap2 == "pm" and _to_24h(h1, m1, "pm") >= _to_24h(h2, m2, "pm"):
            ap1 = "am"
        else:
            ap1 = ap2
    if ap2 is None and ap1 is not None:
        if ap1 == "am" and _to_24h(h2, m2, "am") <= _to_24h(h1, m1, "am"):
            ap2 = "pm"
        else:
            ap2 = ap1
    start = _to_24h(h1, m1, ap1)
    end = _to_24h(h2, m2, ap2)
    if start >= end and ap1 is None and ap2 is None and int(h2) < 12:
        # bare afternoon range like "2.00-2.55" without any meridiem anywhere
        end = _to_24h(h2, m2, "pm")
    return start, end


def parse_period_header(text: Optional[str]) -> Optional[PeriodHeader]:
    """Parse a period header cell like ``6\\n(3.00-3.55 PM)`` or ``B\\nr\\ne\\na\\nk``.

    Tolerant of artifacts Word produces in these documents:
      * time ranges split across stacked header rows ("(9.00-9.55" + "AM)"),
      * overlapping text runs rendering as "(5.0P0M-7). 00",
      * fragments joined with the extractor's " | " cluster separator.
    Returns None for cells that are not period headers at all.
    """
    if not text:
        return None
    flat = " ".join(text.split())
    if not flat:
        return None

    # Break columns render vertically ("B r e a k" / "L u n c h B r e a k").
    # Tolerate glyph artifacts: this PDF sometimes doubles a letter ("breakk")
    # when Word overlaps runs, so match on the letter subset, not the spelling.
    compact = flat.replace(" ", "").lower()
    if compact in {"break", "lunchbreak"} or (
        4 <= len(compact) <= 12 and set(compact) <= set("breuknlach")
    ):
        return PeriodHeader(
            slot_index=0,
            start=None,
            end=None,
            kind="break",
            raw=flat,
        )

    # De-artifact overlapping glyph runs: "(5.0P0M-7). 00" style noise.
    # The meridiem run "P0M" overlays a minute digit (real text "5.00 PM"),
    # so restore that digit and keep the meridiem.
    cleaned = re.sub(r"(?i)p([0o])m", r"\1 PM", flat)
    cleaned = re.sub(r"(?i)a([0o])m", r"\1 AM", cleaned)
    cleaned = re.sub(r"(?i)p[0o]m", " PM ", cleaned)
    cleaned = re.sub(r"(?i)a[0o]m", " AM ", cleaned)
    cleaned = cleaned.replace(").", ".").replace(")", " ").replace("|", " ")

    # Strict shape first: "<slot> (<range>)"
    m = re.match(r"^(\d{1,2})\s*\((.*)\)$", flat, re.DOTALL)
    if m and 1 <= int(m.group(1)) <= 12:
        tm = TIME_RANGE_RE.search(m.group(2))
        if tm:
            h1, m1, ap1, h2, m2, ap2 = tm.groups()
            start, end = _range_24h(int(h1), int(m1), ap1, int(h2), int(m2), ap2)
            return PeriodHeader(int(m.group(1)), start, end, "teaching", raw=flat)

    # Tolerant fallback: slot number + unanchored time range in the cluster.
    slot_m = re.match(r"^(\d{1,2})\b", flat)
    if slot_m and 1 <= int(slot_m.group(1)) <= 12:
        slot = int(slot_m.group(1))
        tm = TIME_RANGE_RE.search(cleaned)
        if tm is None and " " in cleaned.strip():
            # glyph-overlay artifacts can interleave spaces into the range
            tm = TIME_RANGE_RE.search(cleaned.replace(" ", ""))
        if tm:
            h1, m1, ap1, h2, m2, ap2 = tm.groups()
            # Meridiem may appear once for the whole range ("5.00-7.00 PM").
            if ap1 is None and ap2 is None:
                scanned = _scan_meridiem(cleaned)
                ap1 = ap2 = scanned
            start, end = _range_24h(int(h1), int(m1), ap1, int(h2), int(m2), ap2)
            return PeriodHeader(slot, start, end, "teaching", raw=flat)
        return PeriodHeader(slot, None, None, "teaching", raw=flat)
    return None


# ----------------------------------------------------------------- day rows

def parse_day_row(label: Optional[str]) -> Optional[str]:
    """Normalize a row label to a weekday name, or None if not a day row."""
    if not label:
        return None
    token = label.strip().lower()
    for name in WEEKDAYS:
        if token.startswith(name[:3].lower()):
            return name
    return None


def entry_type_from_cell(text: str, has_lab_marker: bool) -> str:
    """Classify a grid cell's entry type.

    Precedence: explicit non-course activities > lab marker > (T) tutorial >
    default class. Course code is matched case-insensitively because a few
    source cells print codes in mixed case (e.g. "Adm" header noise).
    """
    flat = " ".join(text.split())
    lowered = flat.lower()
    for needle, etype in NON_COURSE_ACTIVITIES.items():
        if needle in lowered:
            return etype
    if has_lab_marker:
        return "lab"
    if re.search(r"\(\s*T\s*\)", flat):
        return "tutorial"
    return "class"


# ------------------------------------------------------------ source metadata

@dataclass(frozen=True)
class DocumentMetadata:
    """Header information printed on a timetable page."""

    semester: int
    programme: str
    branch: str
    batch: str
    valid_from: str  # ISO date
    valid_until: str  # ISO date
    raw_title: str = ""
    admission_note: str = ""


def document_metadata(section_title: str, page_title: str) -> Optional[DocumentMetadata]:
    """Parse ``B.TECH. SEMESTER III <branch> BATCH-I [Adm-2025]``-style titles.

    The validity window comes from the document-wide title ("TIME TABLE FOR
    AUGUST-NOVEMBER 2026"): we store exactly the printed range and never
    invent dates.
    """
    title = " ".join((page_title or "").split())
    m = re.search(
        r"TIME\s+TABLE\s+FOR\s+([A-Z]+)\s*[-–—]\s*([A-Z]+)\s+(\d{4})",
        title,
        re.IGNORECASE,
    )
    valid_from = valid_until = None
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
        "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    if m:
        m1, m2, year = m.group(1).lower(), m.group(2).lower(), int(m.group(3))
        if m1 in months and m2 in months:
            valid_from = f"{year}-{months[m1]:02d}-01"
            import calendar

            valid_until = f"{year}-{months[m2]:02d}-{calendar.monthrange(year, months[m2])[1]:02d}"

    sm = SECTION_HEADER_RE.search(" ".join((section_title or "").split()))
    if not sm:
        return None
    sem_raw = sm.group("semester")
    semester = (
        int(sem_raw)
        if sem_raw.isdigit()
        else {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}.get(sem_raw.upper(), 0)
    )
    return DocumentMetadata(
        semester=semester,
        programme="B.Tech",
        branch=sm.group("branch").strip(),
        batch=sm.group("batch").strip(),
        valid_from=valid_from or "",
        valid_until=valid_until or "",
        raw_title=" ".join((section_title or "").split()),
        admission_note=(sm.group("adm") or "").strip(),
    )


# ------------------------------------------------------------- final record

@dataclass
class TimetableRecord:
    """One normalized timetable cell, ready for validation."""

    programme: str
    branch: str
    semester: int
    batch: str
    section: str
    day: str
    slot_index: int
    start_time: Optional[str]
    end_time: Optional[str]
    course_code: Optional[str]
    course_name: Optional[str]
    faculty_initials: list[str] = field(default_factory=list)
    faculty_names: list[str] = field(default_factory=list)
    room: Optional[str] = None
    entry_type: str = "class"
    lab_batch: Optional[int] = None
    source_id: str = ""
    source_page: int = 0
    source_text: str = ""
    valid_from: str = ""
    valid_until: str = ""

    @property
    def weekday_index(self) -> int:
        return WEEKDAYS.get(self.day, 0)

    @property
    def source_uid(self) -> str:
        """Deterministic natural key: identical cells across pages dedupe."""
        parts = [
            self.source_id,
            f"s{self.semester}",
            self.branch,
            f"b{self.batch}",
            self.section,
            f"d{self.weekday_index}",
            f"p{self.slot_index}",
            self.start_time or "na",
            self.course_code or "none",
            self.entry_type,
        ]
        if self.lab_batch is not None:
            parts.append(f"lb{self.lab_batch}")
        return "|".join(parts)

    def to_dict(self) -> dict:
        return {
            "course_code": self.course_code,
            "course_name": self.course_name,
            "faculty_initials": self.faculty_initials,
            "faculty_names": self.faculty_names,
            "day": self.day,
            "slot_index": self.slot_index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "room": self.room,
            "semester": self.semester,
            "programme": self.programme,
            "branch": self.branch,
            "batch": self.batch,
            "section": self.section,
            "entry_type": self.entry_type,
            "lab_batch": self.lab_batch,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "source_id": self.source_id,
            "source_page": self.source_page,
            "source_text": self.source_text,
            "source_uid": self.source_uid,
        }
