"""OCR + structure extraction for CR uploads with Gemini's vision input.

Used only for what the deterministic paths can't read: photos, scans and
PDFs that aren't in the institute's timetable layout
(backend/timetable/extractor.py handles those without any model).

The model *transcribes*; it is never the source of truth:
  - the prompt forbids filling in anything not visible, and asks for
    empty values where the image is unreadable;
  - every course code and faculty initial it returns is resolved against
    the live directory afterwards (cr_ingest/timetable_draft.py), and
    anything unresolved is shown to the CR as an error to fix;
  - the CR edits the result and an admin approves it before a timetable
    changes; announcements are re-classified by rules.py, not by the model.

Plain REST over httpx (certifi CA bundle — urllib fails TLS on stock macOS
Pythons) — the PDF/image goes inline, the answer comes back as JSON
matching RESPONSE_SCHEMA.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = os.environ.get("ORION_VISION_MODEL", "gemini-3.5-flash-lite")
TIMEOUT_S = 60.0


class VisionUnavailable(RuntimeError):
    """No key, quota exhausted, network, or an unusable answer."""


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY")) and os.environ.get("ORION_VISION", "on").lower() not in {"off", "0", "false"}


_ENTRY = {
    "type": "OBJECT",
    "properties": {
        "day": {"type": "STRING", "description": "Full weekday name, e.g. Monday"},
        "start_time": {"type": "STRING", "description": "24-hour HH:MM"},
        "end_time": {"type": "STRING", "description": "24-hour HH:MM"},
        "course_code": {"type": "STRING", "description": "As printed, e.g. CSE 311; empty if none"},
        "course_name": {"type": "STRING"},
        "faculty_initials": {"type": "ARRAY", "items": {"type": "STRING"}},
        "entry_type": {"type": "STRING", "enum": ["class", "lab", "tutorial", "seminar", "project",
                                                  "club_activity", "sports", "break", "other"]},
        "lab_batch": {"type": "INTEGER"},
        "cell_text": {"type": "STRING", "description": "The cell's text exactly as printed"},
    },
    "required": ["day", "start_time", "end_time", "entry_type"],
}

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "kind": {"type": "STRING", "enum": ["timetable", "announcement", "other"]},
        "confidence": {"type": "NUMBER", "description": "0-1: how legible and complete the transcription is"},
        "text": {"type": "STRING", "description": "All readable text, in reading order"},
        "announcement_title": {"type": "STRING"},
        "announcement_body": {"type": "STRING"},
        "class_label": {"type": "STRING", "description": "Semester/branch/section the timetable is for, as printed"},
        "entries": {"type": "ARRAY", "items": _ENTRY},
        "legend": {
            "type": "ARRAY",
            "items": {"type": "OBJECT", "properties": {
                "course_code": {"type": "STRING"}, "course_name": {"type": "STRING"},
                "faculty": {"type": "STRING", "description": "Faculty name(s) as printed"},
                "faculty_initials": {"type": "STRING"},
            }},
        },
    },
    "required": ["kind", "confidence", "text"],
}


def _prompt(class_hint: Optional[str]) -> str:
    target = (f" If the page holds timetables for several classes, transcribe ONLY the one for: {class_hint}."
              if class_hint else "")
    return (
        "You are transcribing a document uploaded by a college class representative. Decide what it is:\n"
        "- \"timetable\": a weekly class schedule grid;\n"
        "- \"announcement\": a notice/message (quiz, exam, assignment, class change, event, circular...);\n"
        "- \"other\": anything else.\n\n"
        "Rules: transcribe ONLY what is visible. Never guess or complete a course code, name, initials, time or "
        "date that you cannot read — leave it empty instead, and lower `confidence`. Do not add information.\n\n"
        "For a timetable: one entry per occupied cell (a cell spanning several periods is one entry with the "
        "full time range). Use the column's printed time range, converted to 24-hour HH:MM. Faculty are the "
        "initials printed in the cell (e.g. \"ATS\"); a marker like (T) means tutorial, not initials; "
        "\"(EC LAB I)\" is a room, not initials. Skip empty cells and lunch/break columns. Copy the "
        f"course legend if the page has one.{target}\n\n"
        "For an announcement: `announcement_title` is its heading or first line; `announcement_body` the full "
        "message text.\n\nAlways put all readable text in `text`."
    )


def extract(data: bytes, mime_type: str, *, class_hint: Optional[str] = None) -> dict[str, Any]:
    """Structured transcription of one PDF/image. Raises VisionUnavailable."""
    if not available():
        raise VisionUnavailable("Gemini is not configured")
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode()}},
            {"text": _prompt(class_hint)},
        ]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    try:
        resp = httpx.post(f"{_API_BASE}/{MODEL}:generateContent", json=body,
                          headers={"x-goog-api-key": key}, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:  # timeouts, DNS, TLS
        logger.warning("vision extraction failed: %s", exc.__class__.__name__)
        raise VisionUnavailable(exc.__class__.__name__) from exc
    if resp.status_code >= 300:
        try:
            detail = (resp.json().get("error") or {}).get("message", "")[:200]
        except ValueError:
            detail = ""
        logger.warning("vision extraction HTTP %s: %s", resp.status_code, detail)
        raise VisionUnavailable("quota exhausted" if resp.status_code == 429 else f"HTTP {resp.status_code}")
    payload = resp.json()

    cands = payload.get("candidates") or []
    parts = ((cands[0] if cands else {}).get("content") or {}).get("parts") or []
    raw = "".join(p.get("text", "") for p in parts).strip()
    if not raw:
        raise VisionUnavailable("empty response")
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as exc:
        # maxOutputTokens hit mid-JSON on a very dense page
        raise VisionUnavailable("response was cut off") from exc
    if not isinstance(out, dict) or out.get("kind") not in {"timetable", "announcement", "other"}:
        raise VisionUnavailable("unexpected response shape")
    return out
