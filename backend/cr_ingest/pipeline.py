"""CR upload → editable draft.

    file ─ validate (type by magic bytes, size)
         ├─ PDF in the institute timetable layout → timetable/extractor.py (no model)
         ├─ PDF with a text layer that isn't a timetable → announcement via rules.py (no model)
         └─ photo / scan / other layout → vision.py (Gemini OCR + structure)
       → timetable draft checked against the live directory (timetable_draft.check)
         or announcement draft classified by rules.py
       → returned to the CR to correct. Nothing authoritative changes here.

The CR's class always comes from their profile (server-side), never from
the file or the request.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from . import exam_draft as ed, rules, timetable_draft as td, vision

logger = logging.getLogger(__name__)

MAX_BYTES = 4 * 1024 * 1024  # the frontend proxy (Vercel) caps request bodies at ~4.5 MB
_MAGIC = [
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
]
EXTENSIONS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class UploadRejected(ValueError):
    """Shown to the CR as-is."""


def sniff(data: bytes) -> str:
    """The file's real type from its first bytes — the browser's claimed
    Content-Type and the file name are not trusted."""
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadRejected("The file is larger than 4 MB. Take a smaller photo or compress the PDF.")
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise UploadRejected("Only PDF, JPEG, PNG or WebP files can be uploaded.")


def class_of(profile: dict) -> Optional[dict]:
    if not profile.get("semester") or not profile.get("department"):
        return None
    cls = {k: profile.get(k) for k in ("semester", "programme", "department", "batch", "section")}
    cls["batch"] = cls.get("batch") or cls.get("section")
    cls["programme"] = cls.get("programme") or "B.Tech"
    return cls


def pdf_text(data: bytes, max_pages: int = 6) -> str:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages]).strip()
    except Exception:  # noqa: BLE001 - corrupt/encrypted PDF: treat as having no text layer
        return ""


@dataclass
class Draft:
    kind: str  # "timetable" | "exam_timetable" | "announcement" | "other"
    method: str  # "layout" | "text" | "vision" | "manual"
    confidence: float
    text: str = ""
    announcement: Optional[dict] = None
    timetable: Optional[dict] = None
    warnings: Optional[list[str]] = None
    exams: Optional[dict] = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "method": self.method, "confidence": round(self.confidence, 2),
                "text": self.text[:6000], "announcement": self.announcement, "timetable": self.timetable,
                "exams": self.exams, "warnings": self.warnings or []}


def timetable_payload(client: Any, cls: dict, entries: list[dict], directory: td.Directory,
                      notes: Optional[list[str]] = None) -> dict:
    checked, issues = td.check(entries, directory)
    current = td.current_entries(client, cls)
    return {
        "class": cls,
        "class_label": td.class_label(cls),
        "entries": checked,
        "issues": [i.to_dict() for i in issues],
        "can_submit": not td.blocking(issues),
        "diff": td.diff(current, checked),
        "current_count": len(current),
        "notes": notes or [],
    }


def semester_departments(client: Any, semester: Optional[int]) -> list[str]:
    try:
        options = client.rpc("orion_class_options").execute().data or []
    except Exception:  # noqa: BLE001
        return []
    return sorted({o["department"] for o in options if not semester or o.get("semester") == semester})


def exam_payload(client: Any, scope: dict, entries: list[dict], exam_type: str, today: date,
                 notes: Optional[list[str]] = None, title_semester: Optional[int] = None) -> dict:
    """An editable exam schedule: rows checked, compared with what's live.
    `scope` = {"semester", "department" (None = every department: admin)}."""
    directory = td.Directory.load(client)
    checked, issues = ed.check(entries, directory, today)
    if title_semester and scope.get("semester") and title_semester != scope["semester"]:
        issues.insert(0, td.Issue(-1, "semester", f"This exam schedule is for semester {title_semester}, but it would be "
                                                  f"saved for semester {scope['semester']}."))
    current = ed.current_exams(client, scope["semester"], exam_type, scope.get("department"))
    departments = sorted({e["department"] for e in checked if e.get("department")})
    return {
        "scope": scope,
        "scope_label": (f"Semester {scope['semester']} · " + (scope["department"] or "all departments")),
        "exam_type": exam_type,
        "exam_type_label": ed.EXAM_TYPE_LABELS.get(exam_type, exam_type),
        "entries": checked,
        "issues": [i.to_dict() for i in issues],
        "can_submit": not td.blocking(issues),
        "diff": ed.diff(current, checked),
        "current_count": len(current),
        "departments": departments,
        "notes": notes or [],
    }


def exam_scope(client: Any, cls: Optional[dict], is_admin: bool, target: Optional[dict],
               title_semester: Optional[int]) -> dict:
    """A CR's exams: their semester + department. An admin's: the semester
    and (optionally) department they picked, else the file's semester and
    every department."""
    if not is_admin:
        if not cls:
            raise UploadRejected("Complete your academic profile first — exams are submitted for your own department.")
        return {"semester": cls["semester"], "department": cls["department"], "programme": cls.get("programme")}
    target = target or {}
    sem = target.get("semester") or title_semester
    if not sem:
        raise UploadRejected("Pick the semester this exam schedule is for.")
    return {"semester": int(sem), "department": target.get("department"), "programme": target.get("programme")}


def _exam_draft(client: Any, entries: list[dict], notes: list[str], title: dict, cls: Optional[dict],
                is_admin: bool, target: Optional[dict], today: date, method: str, conf: float, text: str) -> Draft:
    scope = exam_scope(client, cls, is_admin, target, title.get("semester"))
    kept, scope_notes = ed.scope_entries(entries, scope.get("department"),
                                         semester_departments(client, scope["semester"]))
    return Draft("exam_timetable", method, conf, text,
                 exams=exam_payload(client, scope, kept, title.get("exam_type") or "end_sem", today,
                                    notes + scope_notes, title.get("semester")))


def process(client: Any, profile: dict, data: bytes, today: date, target: Optional[dict] = None) -> Draft:
    """`target`: the class an ADMIN is uploading for (a CR's class always
    comes from their profile; a CR's target is ignored)."""
    mime = sniff(data)
    is_admin = profile.get("role") == "ADMIN"
    cls = class_of(target) if is_admin and target else class_of(profile)
    warnings: list[str] = []
    text = pdf_text(data) if mime == "application/pdf" else ""

    # 0. An exam timetable (before the class timetable check: exam PDFs have
    #    weekdays and time ranges too).
    if mime == "application/pdf" and ed.looks_like_exam_schedule(text):
        entries, notes, _ = ed.from_pdf(data, today)
        if entries:
            return _exam_draft(client, entries, notes, ed.parse_title(text), cls, is_admin, target, today,
                               "layout", 0.95, text)

    # 1. The institute's own timetable PDF: deterministic, no model.
    if mime == "application/pdf" and cls and rules.looks_like_timetable(text):
        found = td.from_institute_pdf(data, cls)
        if found is not None:
            directory = td.Directory.load(client)
            notes = []
            if not found["entries"]:
                notes.append(f"This PDF has timetables for {len(found['classes'])} classes, but not yours "
                             f"({td.class_label(cls)}). Classes in it: " + "; ".join(found["classes"][:12]))
            elif len(found["classes"]) > 1:
                notes.append(f"Took your class's grid out of a PDF with {len(found['classes'])} classes.")
            return Draft("timetable", "layout", 0.97 if found["entries"] else 0.0, text,
                         timetable=timetable_payload(client, cls, found["entries"], directory, notes),
                         warnings=warnings)

    # 2. A PDF that is plainly a text notice: rules only.
    if mime == "application/pdf" and len(text) >= 40 and not rules.looks_like_timetable(text):
        return Draft("announcement", "text", 0.9, text,
                     announcement=rules.draft_announcement(text, today).to_dict(), warnings=warnings)

    # 3. Photos, scans, other layouts: Gemini vision.
    try:
        out = vision.extract(data, mime, class_hint=td.class_label(cls) if cls else None)
    except vision.VisionUnavailable as exc:
        logger.info("vision unavailable for CR upload: %s", exc)
        if text:
            warnings.append("Automatic reading isn't available right now, so this was treated as a text notice.")
            return Draft("announcement", "text", 0.6, text,
                         announcement=rules.draft_announcement(text, today).to_dict(), warnings=warnings)
        raise UploadRejected(
            "Couldn't read this file automatically right now"
            + (" (daily limit reached)" if "quota" in str(exc) else "")
            + ". You can type the announcement instead, or edit your current timetable by hand.") from exc

    conf = float(out.get("confidence") or 0.0)
    ocr_text = out.get("text") or ""
    if conf < 0.5:
        warnings.append("The image was hard to read — check every value carefully before submitting.")

    if out["kind"] == "exam_timetable":
        title = ed.parse_title(out.get("exam_title") or ocr_text)
        return _exam_draft(client, ed.from_vision(out), [], title, cls, is_admin, target, today, "vision", conf, ocr_text)

    if out["kind"] == "timetable":
        if not cls:
            raise UploadRejected("Complete your academic profile (semester, department, section) first — "
                                 "a timetable is always submitted for your own class.")
        directory = td.Directory.load(client)
        entries = td.from_vision(out, directory)
        notes = []
        if out.get("class_label"):
            notes.append(f"The file says it's for: {out['class_label']}. It will be submitted for "
                         f"{td.class_label(cls)}.")
        return Draft("timetable", "vision", conf, ocr_text,
                     timetable=timetable_payload(client, cls, entries, directory, notes), warnings=warnings)

    body = (out.get("announcement_body") or ocr_text).strip()
    if not body:
        raise UploadRejected("No readable text was found in this file.")
    draft = rules.draft_announcement(body, today, title=out.get("announcement_title") or None)
    if out["kind"] == "other":
        warnings.append("This doesn't look like a timetable or a notice. Check it before posting.")
    return Draft(out["kind"] if out["kind"] == "announcement" else "other", "vision", conf, ocr_text,
                 announcement=draft.to_dict(), warnings=warnings)
