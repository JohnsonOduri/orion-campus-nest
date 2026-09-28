# CR upload workflow — timetables and class announcements

Added 2026-09-28. Migration: `supabase/migrations/20260928150000_cr_upload_workflow.sql`
(applied to the hosted project as `cr_upload_workflow`).

## What a CR can do

| Upload / input | What ORION does | Who decides | Result |
|---|---|---|---|
| Timetable PDF in the institute's layout | `backend/timetable/` extractor (no model), CR's class only | **Admin** approves | Class timetable replaced from the chosen date |
| Timetable photo / scan / other layout | Gemini vision OCR → draft | **Admin** approves | same |
| "Edit current timetable" | Class's live timetable as a draft | **Admin** approves | same |
| Notice PDF / photo, or typed text | Rules classify it; dates/times extracted | **Academic** (quiz, exam, assignment, class update, deadline, other academic): CR, **live immediately for their own class**. Anything else: admin | Announcement |

The CR always edits the draft before it goes anywhere. Nothing a CR does
writes to `timetable_entries` directly.

## Pipeline (`backend/cr_ingest/`)

```text
file ── sniff type from bytes (PDF/JPEG/PNG/WebP, ≤4 MB)
     ├─ PDF + looks like a timetable ─► timetable/ extractor, filtered to the CR's class
     ├─ PDF with a text layer ─────────► rules.py (announcement)
     └─ image / scan / other layout ──► vision.py (Gemini, JSON schema, "transcribe only")
     ─► timetable_draft.check(): every course code + faculty initial resolved
        against the live directory; unknowns, missing times, clashes reported
     ─► CR edits in the grid / form ─► submit
```

- `rules.py` — category, sensitive-data findings (phone numbers, Aadhaar,
  PAN, bank details, passwords, keys, medical/disciplinary), date/time
  extraction, expiry. **Deterministic**: the model never decides the
  category or whether something is published.
- `vision.py` — one Gemini call returns kind + transcription + grid +
  legend. The prompt forbids filling in anything unreadable. Its output is
  a draft, never data.
- `timetable_draft.py` — normalisation ("CSE 312 LAB" → CSE 312 / lab,
  "(T)" → tutorial, a course acronym like "DSP" is not a teacher),
  checking, diff against the current timetable.
- `pipeline.py` — picks the path; the CR's class always comes from their
  profile.

## Database

- `approval_requests.payload` (jsonb) holds a timetable proposal: the class
  (from `student_profiles`), `valid_from`, `valid_until`, `entries`.
- `submit_cr_timetable()` — SECURITY INVOKER; CR/admin only; own class
  only; basic shape checks. Inserting a `timetable_update` request needs
  the CR/ADMIN role in RLS too.
- `review_cr_timetable()` — SECURITY DEFINER + `is_admin()` first (same
  pattern as `review_announcement`). On approval, atomically:
  1. closes the class's active periods at `valid_from − 1` (superseded if
     that's already past);
  2. inserts the new periods (`source_id = cr_submission:<id>`),
     re-resolving every code and initial. An unknown one aborts the whole
     approval;
  3. marks the request approved and writes `audit_logs`.
- `announcements` gains `semester/programme/section`, `event_date`,
  `event_time`, `auto_published`, `source_kind`, `source_file_path`. The
  **insert policy** is the real rule. A CR may insert either:
  - a `pending` row; or
  - an `active`, `auto_published` row, only if all of these hold:
    - the category is academic (`orion_is_academic_category`);
    - it is scoped to exactly the CR's own class;
    - `valid_until` is at most ~2 months away.
- Every auto-published row is audit-logged by a trigger. Admins can take
  any live announcement down with `archive_announcement()` (audited).
- Storage bucket `cr-uploads` (private, 4 MB, PDF/images). A CR writes
  only under `<uid>/`. The uploader and admins can read. The API calls
  Storage with the caller's JWT, never the service role.

## API

```text
POST /cr/uploads                  raw file body -> draft (+ stored original path)
GET  /cr/uploads/url?path=        signed link (uploader or admin, by storage policy)
GET  /cr/timetable/current        live timetable as a draft
POST /cr/timetable/check          re-check an edited draft
POST /cr/timetable/submit         -> submit_cr_timetable
GET  /cr/timetable/submissions    own proposals + status
POST /cr/announcements/preview    category, dates, checks, publish decision + reason
POST /cr/announcements            academic + own class -> live; else pending
GET  /admin/timetable-submissions pending, re-checked, with diff vs current
POST /admin/timetable-submissions/{id}/review
GET  /admin/announcements/live    live notices incl. CR auto-published
POST /admin/announcements/{id}/archive
```

`GET /announcements` and the AI now return campus-wide notices **plus**
the caller's class notices (`campus.announcement_visible_to`). Questions
such as "when is the quiz?", "is class cancelled tomorrow?" and "when is
the assignment due?" route to class notices (`router.class_notice_kind`).
Rule questions like "rules for late submission" still go to the
regulations.

## UI

- `/cr` has four tabs: **Upload** (drop a file), **Timetable** (editable
  weekly grid with red/amber cells, diff badges, effective date, note →
  submit), **Announcement** (form prefilled from OCR, with a live "goes
  live now / admin review" explanation) and **History**.
- `/admin` shows timetable changes (class, submitter, diff, read-only
  grid, original file) with approve/reject, and live announcements with
  take-down.
- `/announcements` shows event date/time and "your class" / "posted by
  your CR".

## Verification (2026-09-28)

- Live DB, rolled-back transaction (nothing persisted). 18 checks passed,
  with no blocked action allowed and no allowed action blocked:
  - a CR's academic notice for their own class is allowed;
  - an EVENT, another section, or a 100-day expiry is blocked;
  - a student can't submit a timetable, insert a request, or auto-publish;
  - a CR can't approve, archive, or update `timetable_entries`;
  - admin approval closed 36 periods, inserted 2 (visible via
    `orion_active_entries`), and wrote 3 audit rows.
- Storage (rolled back): a CR writes only to their own folder; students
  can't upload; another user can't read a CR's file; an admin can.
- Extraction on real files:
  - Semester 5 institute PDF: 36/36 periods identical to the live data,
    3.4 s, no model;
  - Semester 3 PDF for a Semester 5 CR: refused, with the classes it
    contains listed;
  - photo of a two-class page: the CR's class picked, 30 periods,
    ambiguous cells ("QC", "IEG 311/313") left as errors to fix;
  - notice photo: QUIZ, 14 Oct 10:30, auto-publishable, 2.2 s.
- `tests/test_cr_workflow.py`: 69 offline tests; the full suite is 437 passing.

## Known limits

- Vision is Gemini's free tier: a dense timetable photo takes 15–35 s,
  and past the daily quota the CR is told to type the notice or edit by
  hand. The frontend proxy is a Vercel function, so its max duration must
  allow ~60 s. Check the project's Functions setting before relying on
  photo uploads in production.
- A CR must have a complete academic profile. Their class key must match
  the timetable's spelling of the department, or the admin sees "no
  current timetable found for this class".
- An upload whose draft is abandoned leaves its original in the bucket.
  It's private, but there is no clean-up job yet.
- CRs can't edit or withdraw a live announcement themselves; an admin can
  take it down.
