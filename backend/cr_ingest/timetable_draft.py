"""A CR's editable timetable draft: build it, check it, compare it.

A draft is a list of plain dicts — one per period — that the CR edits in
the grid and that is stored as-is in approval_requests.payload:

    {"day_of_week": 1, "start_time": "09:30", "end_time": "10:25",
     "course_code": "CSE 311", "faculty_initials": ["ATS"],
     "entry_type": "class", "lab_batch": null, "source_text": "..."}

Three ways to get one: the deterministic institute-PDF extractor (no model),
Gemini vision (photos/scans), or the class's current timetable (to edit by
hand). Whatever the source, `check()` resolves every course code and
faculty initial against the live directory — the same resolution
review_cr_timetable() repeats in SQL at approval — and reports problems
instead of guessing (CLAUDE.md §8/§9: unknown codes/initials are reported,
never invented; validation rejects, it doesn't silently repair).
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ENTRY_TYPES = ("class", "lab", "tutorial", "seminar", "project", "club_activity", "sports", "other")
TEACHING = {"class", "lab", "tutorial"}
MAX_ENTRIES = 200


def norm_code(code: Optional[str]) -> str:
    return re.sub(r"\s+", "", (code or "").upper())


# ------------------------------------------------------------ directory

@dataclass
class Directory:
    """Live course + faculty lookup, read with the caller's own JWT."""

    courses: dict[str, dict] = field(default_factory=dict)  # norm code -> row
    faculty: dict[str, dict] = field(default_factory=dict)  # upper initials -> row

    @classmethod
    def load(cls, client: Any) -> "Directory":
        courses = client.table("courses").select("id,course_code,course_name,semester").execute().data or []
        faculty = client.table("faculty").select("id,full_name,initials,status").execute().data or []
        return cls(
            courses={norm_code(c["course_code"]): c for c in courses if c.get("course_code")},
            faculty={f["initials"].strip().upper(): f for f in faculty if f.get("initials")},
        )

    def course(self, code: Optional[str]) -> Optional[dict]:
        return self.courses.get(norm_code(code)) if code else None

    def course_by_name(self, name: Optional[str]) -> Optional[dict]:
        n = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
        if len(n) < 4:
            return None
        hits = [c for c in self.courses.values()
                if re.sub(r"[^a-z0-9]+", " ", (c.get("course_name") or "").lower()).strip() == n]
        return hits[0] if len(hits) == 1 else None

    def course_acronyms(self) -> set[str]:
        """"DSP" for Digital Signal Processing, … — printed in cells next to
        the code and easily mistaken for a teacher's initials."""
        skip = {"and", "of", "for", "the", "in", "to", "with", "a", "an", "&"}
        out = set()
        for c in self.courses.values():
            words = [w for w in re.findall(r"[A-Za-z]+", c.get("course_name") or "") if w.lower() not in skip]
            if len(words) >= 2:
                out.add("".join(w[0].upper() for w in words))
        return out

    def initials_for_name(self, name: str) -> Optional[str]:
        """Directory initials for a printed faculty name (legend lookup)."""
        from query import campus  # lazy: query/ pulls in more than this needs

        people = [{"full_name": f["full_name"], "initials": i} for i, f in self.faculty.items() if f.get("full_name")]
        match = campus.match_faculty_name(f"Dr. {name}", people)
        if not match:
            return None
        for p in people:
            if p["full_name"] == match:
                return p["initials"]
        return None


# ------------------------------------------------------------ normalise

_TIME_RE = re.compile(r"^\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*$", re.I)


def norm_time(value: Any) -> Optional[str]:
    """"9.30", "9:30 AM", "14:00", "2 pm" -> "HH:MM"; None if unreadable.
    A bare 1-7 o'clock is afternoon — no college class starts at 2 AM."""
    m = _TIME_RE.match(str(value or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ap = (m.group(3) or "").lower()
    if h > 23 or mi > 59:
        return None
    if ap.startswith("p") and h < 12:
        h += 12
    elif ap.startswith("a") and h == 12:
        h = 0
    elif not ap and 1 <= h <= 7:
        h += 12
    return f"{h:02d}:{mi:02d}"


def norm_day(value: Any) -> Optional[int]:
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        d = int(value)
        return d if 1 <= d <= 7 else None
    v = str(value or "").strip().lower()[:3]
    for i, name in enumerate(DAYS, start=1):
        if name.lower().startswith(v) and len(v) == 3:
            return i
    return None


_CODE_IN_TEXT_RE = re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b")
_TYPE_MARKER_RE = re.compile(r"\s*(\(?\s*(LAB|T|TUT|TUTORIAL)\s*\)?)\s*$", re.I)


def normalise(raw: dict, directory: Optional[Directory] = None) -> dict:
    """One period in canonical draft form. Keeps what it can't read (as
    None/empty) so check() can report it rather than dropping it."""
    code = (raw.get("course_code") or "").strip().upper()
    etype = (raw.get("entry_type") or "class").strip().lower()
    # "CSE 312 LAB" / "IMA 311 (T)": a code plus a type marker, as printed.
    marker = _TYPE_MARKER_RE.search(code)
    if marker and _CODE_IN_TEXT_RE.search(code[:marker.start()]):
        etype = "lab" if marker.group(2).upper() == "LAB" else "tutorial"
        code = code[:marker.start()].strip()
    # Exactly one code inside extra text ("CSE311:" / "CSE 311 AI") -> that code;
    # two codes ("IEG 311/313") stay as typed, for the CR to decide.
    codes = _CODE_IN_TEXT_RE.findall(code)
    shared = re.search(r"\d{3}\s*/\s*\d{3}", code)  # "IEG 311/313" names two courses
    if len(codes) == 1 and not shared and not directory_has(directory, code):
        code = f"{codes[0][0]} {codes[0][1]}"
    if directory and code:
        hit = directory.course(code)
        if hit:
            code = hit["course_code"]
    if directory and not code and raw.get("course_name"):
        hit = directory.course_by_name(raw.get("course_name"))
        if hit:
            code = hit["course_code"]
    fac = raw.get("faculty_initials") or []
    if isinstance(fac, str):
        fac = re.split(r"[,/&;\s]+", fac)
    fac = [f.strip().upper().strip(".()") for f in fac if f and f.strip().strip(".()")]
    fac = [f for f in fac if f not in {"T", "LAB"}]  # "(T)" = tutorial marker, never a person
    if etype not in ENTRY_TYPES and etype != "break":
        etype = "other"
    lab = raw.get("lab_batch")
    try:
        lab = int(lab) if lab not in (None, "", 0) else None
    except (TypeError, ValueError):
        lab = None
    return {
        "day_of_week": norm_day(raw.get("day_of_week", raw.get("day"))),
        "start_time": norm_time(raw.get("start_time")),
        "end_time": norm_time(raw.get("end_time")),
        "course_code": code or None,
        "faculty_initials": list(dict.fromkeys(fac)),
        "entry_type": etype,
        "lab_batch": lab,
        "source_text": (raw.get("source_text") or raw.get("cell_text") or "")[:500] or None,
    }


def directory_has(directory: Optional[Directory], code: str) -> bool:
    return bool(directory and directory.course(code))


# ---------------------------------------------------------------- check

@dataclass
class Issue:
    index: int  # -1 = whole timetable
    field: str
    message: str
    severity: str = "error"  # "error" blocks submit; "warning" doesn't

    def to_dict(self) -> dict:
        return {"index": self.index, "field": self.field, "message": self.message, "severity": self.severity}


def check(entries: list[dict], directory: Directory) -> tuple[list[dict], list[Issue]]:
    """(entries annotated with resolved names, issues). Breaks are dropped:
    they are never stored as periods."""
    issues: list[Issue] = []
    out: list[dict] = []
    acronyms = directory.course_acronyms()
    if not entries:
        issues.append(Issue(-1, "entries", "The timetable has no periods."))
    if len(entries) > MAX_ENTRIES:
        issues.append(Issue(-1, "entries", f"A timetable can have at most {MAX_ENTRIES} periods."))
    for raw in entries:
        e = normalise(raw, directory)
        if e["entry_type"] == "break":
            continue
        i = len(out)
        if e["day_of_week"] is None:
            issues.append(Issue(i, "day_of_week", "Pick a day."))
        if not e["start_time"] or not e["end_time"]:
            # A whole-day activity block (Saturday sports) prints no time; a
            # class always has one.
            if e["entry_type"] in TEACHING or e["start_time"] or e["end_time"]:
                issues.append(Issue(i, "time", "Start and end time are needed (HH:MM)."))
            else:
                issues.append(Issue(i, "time", "No time given — this will show as an all-day activity.", "warning"))
        elif e["start_time"] >= e["end_time"]:
            issues.append(Issue(i, "time", f"Ends ({e['end_time']}) before it starts ({e['start_time']})."))
        course = directory.course(e["course_code"])
        e["course_name"] = course["course_name"] if course else None
        if e["course_code"] and not course:
            issues.append(Issue(i, "course_code", f"\"{e['course_code']}\" isn't in the course catalogue."))
        if not e["course_code"] and e["entry_type"] in TEACHING:
            issues.append(Issue(i, "course_code", f"A {e['entry_type']} needs a course code."))
        names = []
        for ini in list(e["faculty_initials"]):
            f = directory.faculty.get(ini)
            if f:
                names.append(f["full_name"])
            elif ini in acronyms:
                # "DSP" next to "IEG 311" is Digital Signal Processing, not a person.
                e["faculty_initials"].remove(ini)
                issues.append(Issue(i, "faculty_initials", f"Removed \"{ini}\": it's a course abbreviation, "
                                                            "not a teacher's initials.", "warning"))
            else:
                issues.append(Issue(i, "faculty_initials", f"No faculty member has the initials \"{ini}\"."))
        e["faculty_names"] = names
        if e["entry_type"] in TEACHING and course and not e["faculty_initials"]:
            issues.append(Issue(i, "faculty_initials", "No teacher given for this period.", "warning"))
        out.append(e)
    issues.extend(_overlaps(out))
    return out, issues


def _overlaps(entries: list[dict]) -> list[Issue]:
    """Two periods at the same time on the same day clash — unless they're
    for different lab batches (batch 1 in one lab, batch 2 in another). Two
    teaching periods clashing is an error; an activity (club hour, sports)
    overlapping a class is only a warning — the institute's own timetables
    do that."""
    issues = []
    for i, a in enumerate(entries):
        for j in range(i + 1, len(entries)):
            b = entries[j]
            if a["day_of_week"] != b["day_of_week"] or not all(
                    (a["start_time"], a["end_time"], b["start_time"], b["end_time"])):
                continue
            if a["lab_batch"] and b["lab_batch"] and a["lab_batch"] != b["lab_batch"]:
                continue
            if a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]:
                day = DAYS[(a["day_of_week"] or 1) - 1]
                both_teaching = a["entry_type"] in TEACHING and b["entry_type"] in TEACHING
                issues.append(Issue(j, "time", f"Overlaps another period on {day} "
                                               f"({a['start_time']}–{a['end_time']}).",
                                    "error" if both_teaching else "warning"))
    return issues


def blocking(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)


def storable(entries: list[dict]) -> list[dict]:
    """What goes into approval_requests.payload: the canonical fields only
    (resolved names are re-derived from the directory whenever shown)."""
    keys = ("day_of_week", "start_time", "end_time", "course_code", "faculty_initials", "entry_type",
            "lab_batch", "source_text")
    return [{k: e.get(k) for k in keys} for e in entries]


# ---------------------------------------------------------------- diff

def _key(e: dict) -> tuple:
    return (e.get("day_of_week"), e.get("start_time"), e.get("lab_batch"))


def diff(current: list[dict], proposed: list[dict]) -> dict:
    """What approval would change, period by period."""
    cur = {_key(e): e for e in current}
    new = {_key(e): e for e in proposed}

    def same(a: dict, b: dict) -> bool:
        return (norm_code(a.get("course_code")) == norm_code(b.get("course_code"))
                and a.get("end_time") == b.get("end_time")
                and a.get("entry_type") == b.get("entry_type")
                and sorted(a.get("faculty_initials") or []) == sorted(b.get("faculty_initials") or []))

    added = [new[k] for k in new if k not in cur]
    removed = [cur[k] for k in cur if k not in new]
    changed = [{"before": cur[k], "after": new[k]} for k in new if k in cur and not same(cur[k], new[k])]
    return {"added": added, "removed": removed, "changed": changed,
            "unchanged": sum(1 for k in new if k in cur and same(cur[k], new[k]))}


# --------------------------------------------------------------- sources

def current_entries(client: Any, cls: dict) -> list[dict]:
    """The class's live timetable as a draft (read through RLS)."""
    rows = (
        client.table("timetable_entries")
        .select("day_of_week,start_time,end_time,entry_type,lab_batch,source_text,valid_from,valid_until,"
                "courses(course_code,course_name),timetable_entry_faculty(ord,faculty(initials,full_name))")
        .eq("semester", cls["semester"]).eq("department", cls["department"])
        .eq("batch", cls["batch"]).eq("section", cls["section"]).eq("status", "active")
        .order("day_of_week").order("start_time")
        .execute().data or []
    )
    out = []
    for r in rows:
        if r.get("entry_type") == "break":
            continue
        fac = sorted(r.get("timetable_entry_faculty") or [], key=lambda x: x.get("ord") or 0)
        out.append({
            "day_of_week": r["day_of_week"],
            "start_time": (r.get("start_time") or "")[:5] or None,
            "end_time": (r.get("end_time") or "")[:5] or None,
            "course_code": (r.get("courses") or {}).get("course_code"),
            "course_name": (r.get("courses") or {}).get("course_name"),
            "faculty_initials": [f["faculty"]["initials"] for f in fac if f.get("faculty")],
            "faculty_names": [f["faculty"]["full_name"] for f in fac if f.get("faculty")],
            "entry_type": r.get("entry_type") or "class",
            "lab_batch": r.get("lab_batch"),
            "source_text": r.get("source_text"),
        })
    return out


def class_label(cls: dict) -> str:
    return f"Semester {cls['semester']} · {cls['department']} · Section {cls['section']}"


def from_institute_pdf(data: bytes, cls: dict) -> Optional[dict]:
    """Run the deterministic extractor (backend/timetable/) on a PDF in the
    institute's layout. None when the PDF isn't in that layout at all;
    otherwise {"entries": [...] (this class only), "classes": [labels found]}."""
    from timetable.service import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.pdf"
        path.write_bytes(data)
        try:
            result = run_pipeline(path, source_id="cr_upload")
        except Exception:  # noqa: BLE001 - not this layout / unreadable: let the next path try
            return None
    records = result.preview.get("records") or []
    if not records:
        return None
    found = sorted({(r["semester"], r["branch"], r["section"]) for r in records})
    mine = [r for r in records
            if r["semester"] == cls["semester"] and r["branch"] == cls["department"]
            and r["section"] == cls["section"] and r["batch"] == cls["batch"]]
    return {
        "entries": [{
            "day_of_week": norm_day(r["day"]), "start_time": r["start_time"], "end_time": r["end_time"],
            "course_code": r["course_code"], "faculty_initials": r["faculty_initials"],
            "entry_type": r["entry_type"], "lab_batch": r["lab_batch"], "source_text": r["source_text"],
        } for r in mine],
        "classes": [f"Semester {s} · {b} · Section {sec}" for s, b, sec in found],
    }


def from_vision(out: dict, directory: Directory) -> list[dict]:
    """Vision transcription -> draft periods, using the page's own legend to
    turn printed names into codes/initials where the cell only had names."""
    legend_codes: dict[str, str] = {}
    legend_initials: dict[str, list[str]] = {}
    for row in out.get("legend") or []:
        code = (row.get("course_code") or "").strip()
        name = (row.get("course_name") or "").strip().lower()
        if code and name:
            legend_codes[name] = code
        if code and row.get("faculty_initials"):
            legend_initials[norm_code(code)] = re.split(r"[,/&;\s]+", row["faculty_initials"])
        elif code and row.get("faculty"):
            inis = [directory.initials_for_name(n) for n in re.split(r",|&|/| and ", row["faculty"]) if n.strip()]
            if inis and all(inis):
                legend_initials[norm_code(code)] = inis  # type: ignore[assignment]
    entries = []
    for e in out.get("entries") or []:
        raw = dict(e)
        if not raw.get("course_code") and (raw.get("course_name") or "").strip().lower() in legend_codes:
            raw["course_code"] = legend_codes[raw["course_name"].strip().lower()]
        if not raw.get("faculty_initials") and raw.get("course_code"):
            raw["faculty_initials"] = legend_initials.get(norm_code(raw["course_code"]), [])
        entries.append(raw)
    return entries
