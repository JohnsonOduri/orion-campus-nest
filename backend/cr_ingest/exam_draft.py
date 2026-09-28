"""Exam schedules from uploads: read, check, compare.

Exam timetables come in many layouts. Handled here without a model:

  - a grid: one row per date, one column per department, each cell
    "CODE Name" (optionally "CODE1 Name / CODE2 Name" = alternatives, e.g.
    two electives in the same slot) — AI-Tests/END_EXAM SEM V-OCT_ODD_2026.pdf;
  - a list: one row per exam with date / time / course (/ department) columns;
  - plain text lines "28-10-2026 09:30-12:30 CSE311 Artificial Intelligence".

Photos and scans go through vision.py (kind "exam_timetable"). Whatever the
source, `check()` reports problems instead of guessing, and the CR/admin edits
the draft before it's submitted; an admin approves it
(review_exam_schedule) before anything in `exams` changes.

A draft row:
    {"exam_date": "2026-10-28", "start_time": "09:30", "end_time": "12:30",
     "course_code": "CSE 311", "course_name": "Artificial Intelligence",
     "department": "COMPUTER SCIENCE AND ENGINEERING", "alt_group": null,
     "notes": null}
"""

from __future__ import annotations

import io
import re
from datetime import date
from typing import Any, Optional

from . import timetable_draft as td

EXAM_TYPES = ("end_sem", "mid_sem", "repeat", "quiz", "other")
EXAM_TYPE_LABELS = {"end_sem": "End semester", "mid_sem": "Mid semester", "repeat": "Repeat / supplementary",
                    "quiz": "Quiz / class test", "other": "Other"}

_CODE_RE = re.compile(r"\b([A-Z]{2,4})\s?-?\s?(\d{3}[A-Z]?)\b")
_DATE_NUM_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_WORD_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*(\d{4})?", re.I)
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})[.:](\d{2})\s*(a\.?m\.?|p\.?m\.?|noon)?\s*(?:-|–|—|to)\s*(\d{1,2})[.:](\d{2})\s*(a\.?m\.?|p\.?m\.?|noon)?", re.I)
_SESSION_RE = re.compile(r"\b(FN|AN|forenoon|afternoon)\b", re.I)


# ------------------------------------------------------------- normalise

def dept_key(name: Optional[str]) -> str:
    """One key per department however it's spelled: "CSE WITH SPECIALISATION
    IN CYBER SECURITY" and "CYBER SECURITY" are both "cyber"."""
    n = (name or "").upper()
    if "CYBER" in n:
        return "cyber"
    if ("DATA" in n and re.search(r"\bAI\b|ARTIFICIAL", n)) or "AIDS" in n or "AI&DS" in n.replace(" ", ""):
        return "aids"
    if "ELECTRONICS" in n or re.search(r"\bECE\b", n):
        return "ece"
    if "COMPUTER SCIENCE" in n or re.fullmatch(r"\s*CSE\s*", n):
        return "cse"
    if "MATHEMATIC" in n:
        return "maths"
    return re.sub(r"[^a-z]+", " ", n.lower()).strip()


def looks_like_department(cell: str) -> bool:
    n = (cell or "").upper()
    return any(k in n for k in ("COMPUTER", "ELECTRONICS", "CYBER", "DATA SCIENCE", "MATHEMATIC", "ENGINEERING",
                                "CSE", "ECE")) and not _CODE_RE.search(n)


def parse_date(text: str, today: Optional[date] = None) -> Optional[str]:
    m = _DATE_NUM_RE.search(text or "")
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    m = _DATE_WORD_RE.search(text or "")
    if m:
        y = int(m.group(3)) if m.group(3) else (today or date.today()).year
        try:
            return date(y, _MONTHS[m.group(2)[:3].lower()], int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def _to24(h: int, m: int, mer: Optional[str]) -> int:
    mer = (mer or "").lower().replace(".", "")
    if mer == "noon":
        return 12 * 60
    if mer.startswith("p") and h < 12:
        h += 12
    elif mer.startswith("a") and h == 12:
        h = 0
    elif not mer and 1 <= h <= 7:
        h += 12
    return h * 60 + m


def parse_time_range(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """(start "HH:MM", end "HH:MM", note). A printed end time that is
    impossible ("09.30 AM-12.30 AM") is read as the afternoon and the note
    says so — the reviewer sees the correction instead of a silent fix."""
    m = _TIME_RANGE_RE.search(text or "")
    if not m:
        s = _SESSION_RE.search(text or "")
        if s:
            fn = s.group(1).lower() in ("fn", "forenoon")
            return ("09:30", "12:30", None) if fn else ("14:00", "17:00", None)
        return None, None, None
    h1, m1, a1, h2, m2, a2 = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5)), m.group(6)
    start = _to24(h1, m1, a1 or (a2 if a2 and not (a2.lower().startswith("p") and h1 > h2 and h1 != 12) else None))
    end = _to24(h2, m2, a2)
    note = None
    if end <= start:
        fixed = end + 12 * 60 if end + 12 * 60 < 24 * 60 else end
        if a2 and a2.lower().startswith("a") and h2 == 12:
            fixed = 12 * 60 + m2  # "12.30 AM" printed where 12:30 PM is meant
        if fixed > start:
            note = f"The file says “{m.group(0).strip()}”; read as ending at {fixed // 60:02d}:{fixed % 60:02d}."
            end = fixed
    return f"{start // 60:02d}:{start % 60:02d}", f"{end // 60:02d}:{end % 60:02d}", note


def split_cell(cell: str) -> list[tuple[str, str]]:
    """"IEG311 Digital Signal Processing / IEG313 Quantum Computing..." ->
    [("IEG 311", "Digital Signal Processing"), ("IEG 313", "Quantum Computing...")]."""
    text = re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()
    matches = list(_CODE_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        tail = text[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(text)]
        name = re.sub(r"^[\s:–—-]+|[\s/,;–—-]+$", "", tail).strip()
        out.append((f"{m.group(1)} {m.group(2)}", name))
    return out


def parse_title(text: str) -> dict:
    # the heading only: course names further down ("Supply Chain Management")
    # must not decide the exam type
    lines = [l for l in (text or "").upper().splitlines() if l.strip()]
    t = " ".join(l for l in lines[:6] if not _CODE_RE.search(l))
    exam_type = ("repeat" if re.search(r"REPEAT|SUPPLEMENTARY|\bSUPPLY\b(?!\s+CHAIN)|BACKLOG", t) else
                 "mid_sem" if re.search(r"MID[\s-]?SEM|MID[\s-]?TERM|INTERNAL|SESSIONAL", t) else
                 "quiz" if re.search(r"\bQUIZ|CLASS\s+TEST", t) else
                 "end_sem" if re.search(r"END[\s-]?SEM|SEMESTER\s+EXAM|FINAL\s+EXAM|UNIVERSITY\s+EXAM", t) else "other")
    sem = None
    m = re.search(r"SEM(?:ESTER)?\s*[-:]?\s*([IVX]{1,4}|\d)\b", t)
    if m:
        v = m.group(1)
        sem = int(v) if v.isdigit() else {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}.get(v)
    return {"exam_type": exam_type, "semester": sem}


# ----------------------------------------------------------------- read

def _clean(cell: Any) -> str:
    return re.sub(r"[ \t]+", " ", str(cell or "")).strip()


def from_tables(tables: list[list[list[Any]]], today: Optional[date] = None) -> tuple[list[dict], list[str]]:
    """Exam rows from extracted tables (grid or list layout), plus notes."""
    entries: list[dict] = []
    notes: list[str] = []
    for table in tables:
        rows = [[_clean(c) for c in r] for r in table if r]
        if not rows:
            continue
        # department header: the row with the most department-looking cells
        dept_cols: dict[int, str] = {}
        best = max(rows, key=lambda r: sum(looks_like_department(c) for c in r))
        if sum(looks_like_department(c) for c in best) >= 1:
            dept_cols = {i: c.replace("\n", " ") for i, c in enumerate(best) if looks_like_department(c)}
        for r in rows:
            joined = " ".join(r)
            ex_date = next((parse_date(c, today) for c in r if parse_date(c, today)), None)
            if not ex_date:
                continue
            start = end = note = None
            for c in r:
                s, e, n = parse_time_range(c)
                if s:
                    start, end, note = s, e, n
                    break
            if note and note not in notes:
                notes.append(note)
            if dept_cols:
                for i, dept in dept_cols.items():
                    cell = r[i] if i < len(r) else ""
                    found = split_cell(cell)
                    alt = "/".join(code.replace(" ", "") for code, _ in found) if len(found) > 1 else None
                    for code, name in found:
                        entries.append({"exam_date": ex_date, "start_time": start, "end_time": end,
                                        "course_code": code, "course_name": name or None, "department": dept,
                                        "alt_group": alt, "notes": None})
            else:
                found = split_cell(joined)
                alt = "/".join(code.replace(" ", "") for code, _ in found) if len(found) > 1 else None
                for code, name in found:
                    name = _TIME_RANGE_RE.sub("", _DATE_NUM_RE.sub("", name)).strip(" -,")
                    entries.append({"exam_date": ex_date, "start_time": start, "end_time": end, "course_code": code,
                                    "course_name": name or None, "department": None, "alt_group": alt, "notes": None})
    return entries, notes


def from_text(text: str, today: Optional[date] = None) -> tuple[list[dict], list[str]]:
    """Line by line: a date, a time range and a course code on one line."""
    entries, notes = [], []
    current_date = None
    for line in (text or "").splitlines():
        d = parse_date(line, today)
        if d:
            current_date = d
        codes = split_cell(line)
        if not codes or not current_date:
            continue
        s, e, n = parse_time_range(line)
        if n and n not in notes:
            notes.append(n)
        alt = "/".join(c.replace(" ", "") for c, _ in codes) if len(codes) > 1 else None
        for code, name in codes:
            name = _TIME_RANGE_RE.sub("", _DATE_NUM_RE.sub("", name)).strip(" -,")
            entries.append({"exam_date": current_date, "start_time": s, "end_time": e, "course_code": code,
                            "course_name": name or None, "department": None, "alt_group": alt, "notes": None})
    return entries, notes


def from_pdf(data: bytes, today: Optional[date] = None) -> tuple[list[dict], list[str], str]:
    """(entries, notes, all text) from a PDF with a text layer."""
    import pdfplumber

    entries: list[dict] = []
    notes: list[str] = []
    texts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:8]:
            texts.append(page.extract_text() or "")
            e, n = from_tables(page.extract_tables() or [], today)
            entries += e
            notes += [x for x in n if x not in notes]
    text = "\n".join(texts)
    if not entries:
        entries, notes = from_text(text, today)
    return entries, notes, text


def from_vision(out: dict) -> list[dict]:
    rows = []
    for e in out.get("exams") or []:
        s, t, _ = parse_time_range(f"{e.get('start_time', '')}-{e.get('end_time', '')}")
        rows.append({"exam_date": parse_date(e.get("date") or "") or e.get("date"),
                     "start_time": s or e.get("start_time"), "end_time": t or e.get("end_time"),
                     "course_code": e.get("course_code"), "course_name": e.get("course_name"),
                     "department": e.get("department"), "alt_group": None, "notes": None})
    return rows


# ----------------------------------------------------------------- scope

def scope_entries(entries: list[dict], department: Optional[str], semester_departments: list[str]) -> tuple[list[dict], list[str]]:
    """Keep the rows for one department (a CR's), or map every row's
    department onto ORION's spelling for that semester (an admin's whole
    schedule). Returns (rows, notes)."""
    notes = []
    by_key = {dept_key(d): d for d in semester_departments}
    if department:
        key = dept_key(department)
        has_dept = any(e.get("department") for e in entries)
        kept = [dict(e, department=department) for e in entries
                if not has_dept or not e.get("department") or dept_key(e["department"]) == key]
        others = sorted({e["department"] for e in entries if e.get("department") and dept_key(e["department"]) != key})
        if others:
            notes.append(f"Kept your department's exams; the file also lists {len(others)} other department(s).")
        return kept, notes
    out = []
    unknown = set()
    for e in entries:
        mapped = by_key.get(dept_key(e.get("department"))) if e.get("department") else None
        if e.get("department") and not mapped:
            unknown.add(e["department"])
        out.append(dict(e, department=mapped or e.get("department")))
    if unknown:
        notes.append("No timetable class matches these departments for that semester: " + "; ".join(sorted(unknown)))
    return out, notes


# ----------------------------------------------------------------- check

def normalise(raw: dict, directory: Optional[td.Directory] = None) -> dict:
    code = (raw.get("course_code") or "").strip().upper()
    m = _CODE_RE.search(code)
    if m:
        code = f"{m.group(1)} {m.group(2)}"
    ex_date = raw.get("exam_date")
    if ex_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ex_date)):
        ex_date = parse_date(str(ex_date))
    known = directory.course(code) if directory and code else None
    return {
        "exam_date": ex_date or None,
        "start_time": td.norm_time(raw.get("start_time")),
        "end_time": td.norm_time(raw.get("end_time")),
        "course_code": code or None,
        "course_name": (raw.get("course_name") or (known or {}).get("course_name") or None),
        "department": raw.get("department") or None,
        "alt_group": raw.get("alt_group") or None,
        "notes": (raw.get("notes") or None),
        "in_catalogue": bool(known),
    }


def check(entries: list[dict], directory: td.Directory, today: date) -> tuple[list[dict], list[td.Issue]]:
    issues: list[td.Issue] = []
    out: list[dict] = []
    if not entries:
        issues.append(td.Issue(-1, "entries", "No exams were found. Add them below or upload a clearer file."))
    seen: dict[tuple, int] = {}
    for raw in entries:
        e = normalise(raw, directory)
        i = len(out)
        if not e["exam_date"]:
            issues.append(td.Issue(i, "exam_date", "Pick the exam date."))
        elif e["exam_date"] < today.isoformat():
            issues.append(td.Issue(i, "exam_date", "This date has already passed.", "warning"))
        if not e["start_time"] or not e["end_time"]:
            issues.append(td.Issue(i, "time", "Start and end time are needed."))
        elif e["start_time"] >= e["end_time"]:
            issues.append(td.Issue(i, "time", f"Ends ({e['end_time']}) before it starts ({e['start_time']})."))
        if not e["course_code"]:
            issues.append(td.Issue(i, "course_code", "Every exam needs a course code."))
        elif not e["in_catalogue"]:
            issues.append(td.Issue(i, "course_code", f"{e['course_code']} isn't in ORION's course list — it will be saved "
                                                     "with the name as printed.", "warning"))
        key = (e["exam_date"], e["course_code"], e["department"])
        if key in seen:
            issues.append(td.Issue(i, "course_code", "The same exam is listed twice.", "warning"))
        seen[key] = i
        out.append(e)
    # the same department sitting two different (non-alternative) exams at once
    for a_i, a in enumerate(out):
        for b_i in range(a_i + 1, len(out)):
            b = out[b_i]
            if (a["exam_date"], a["department"]) != (b["exam_date"], b["department"]) or a["course_code"] == b["course_code"]:
                continue
            if a["alt_group"] and a["alt_group"] == b["alt_group"]:
                continue
            if a["start_time"] and b["start_time"] and a["start_time"] < (b["end_time"] or "") and b["start_time"] < (a["end_time"] or ""):
                issues.append(td.Issue(b_i, "time", f"Overlaps {a['course_code']} on the same day.", "warning"))
    return out, issues


def storable(entries: list[dict]) -> list[dict]:
    keys = ("exam_date", "start_time", "end_time", "course_code", "course_name", "department", "alt_group", "notes")
    return [{k: e.get(k) for k in keys} for e in entries]


def diff(current: list[dict], proposed: list[dict]) -> dict:
    def key(e: dict) -> tuple:
        return (td.norm_code(e.get("course_code")), dept_key(e.get("department")))
    cur = {key(e): e for e in current}
    new = {key(e): e for e in proposed}
    def same(a: dict, b: dict) -> bool:
        return (a.get("exam_date"), (a.get("start_time") or "")[:5], (a.get("end_time") or "")[:5]) == \
               (b.get("exam_date"), (b.get("start_time") or "")[:5], (b.get("end_time") or "")[:5])
    return {"added": [new[k] for k in new if k not in cur], "removed": [cur[k] for k in cur if k not in new],
            "changed": [{"before": cur[k], "after": new[k]} for k in new if k in cur and not same(cur[k], new[k])],
            "unchanged": sum(1 for k in new if k in cur and same(cur[k], new[k]))}


def current_exams(client: Any, semester: int, exam_type: str, department: Optional[str]) -> list[dict]:
    rows = (client.table("exams").select("exam_date,start_time,end_time,course_code,course_name,department,alt_group")
            .eq("status", "active").eq("semester", semester).eq("exam_type", exam_type).execute().data or [])
    if department:
        rows = [r for r in rows if dept_key(r.get("department")) == dept_key(department)]
    return rows


def looks_like_exam_schedule(text: str) -> bool:
    t = text or ""
    return bool(re.search(r"\b(exam(ination)?s?|test|quiz|assessment)\b", t, re.I)) and \
        len(_DATE_NUM_RE.findall(t)) + len(_DATE_WORD_RE.findall(t)) >= 2 and len(_CODE_RE.findall(t)) >= 2
