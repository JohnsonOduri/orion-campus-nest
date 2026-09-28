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

---

# Round 3 — exams, class changes, admin publishing, roles, registration

Migration `20260928190000_exams_class_changes_roles_registration.sql` (applied
to the live project, recorded as `exams_class_changes_roles_registration`).

## Exam timetables

- Recognised before class timetables (`exam_draft.looks_like_exam_schedule`):
  exam words + several dates + course codes. Before this change, an exam PDF
  was treated as an announcement.
- Read without a model when the PDF has a text layer
  (`backend/cr_ingest/exam_draft.py`):
  - **Grid layout** — dates × departments, as in
    `AI-Tests/END_EXAM SEM V-OCT_ODD_2026.pdf`. All 33 exams read correctly.
  - **List layout** — date / time / course columns.
  - **Plain text** lines.
  - Photos and scans go through vision (`kind: "exam_timetable"`).
- Quirks handled, never silently:
  - An impossible end time ("09.30 AM-12.30 AM") is read as 12:30 PM, with
    a visible note.
  - "A / B" in one cell becomes alternative exams (`alt_group`).
  - "FN"/"AN" sessions are read as 9:30–12:30 / 2:00–5:00.
  - Printed department names are mapped to ORION's spelling for that
    semester (`dept_key`).
- Scope:
  - A CR's upload keeps their own department's rows.
  - A file for another semester can't be submitted.
  - An admin picks the semester, and optionally a department; with no
    department, every department is included.
- Checks:
  - **Errors (block submitting):** missing date, time or course code;
    end before start.
  - **Warnings (don't block):**
    - past dates;
    - codes not in the catalogue (saved with the name as printed);
    - duplicates;
    - clashes within a department (alternatives excepted).
- `submit_exam_schedule` → `approval_requests` (`exam_schedule`) →
  `review_exam_schedule` (admin). On approval, that semester + exam type +
  department's earlier exams are superseded, the new rows are inserted, and
  an audit row is written. Exam rows expire after their date.
- Students: `/exams` and the AI ("my exam schedule", "when is my AI exam",
  "next exam") read the approved rows for their semester + department. If
  none exist, they show the calendar's exam window.

## Class changes

- **One-off** (cancelled, rescheduled or extra class on a date):
  - A class-update notice carries structured changes.
    `class_changes.extract` reads them from the text (course by code, name
    or acronym, e.g. "DAA", "TOC").
  - The CR confirms them in the Announcement tab.
  - They're checked against the class's weekly timetable (e.g. "your
    timetable has no ICS 211 on Tuesday").
  - They're posted atomically with the notice (`post_class_update`,
    SECURITY INVOKER). RLS allows only the CR's own class, dates within 90
    days, and admin-only edits. They're audit-logged, and they're withdrawn
    if the admin takes the notice down.
- **Applied everywhere:** `backend/query/schedule.py` applies them to:
  - today / a day / a date;
  - free time;
  - the working-day check;
  - next class (worked out day by day when a change is in the coming week);
  - the `/timetable` day and week views (cancelled periods struck through,
    extra/moved classes marked).
- **Permanent** ("from now on…", "every Tuesday", "revised timetable"):
  - Not a class change. The composer says so and opens the timetable editor
    pre-filled with the current timetable.
  - A CR's edit goes to the admin as before.

## Admin publishing

- Admins use the same page (`/cr`, titled "Publish & uploads") with a class
  picker.
- Timetable and exam submissions by an admin are approved immediately
  through the same RPCs, so the audit trail is identical.
- Admin notices can go to everyone or to one class.
- `orion_submission_class(p_target)` uses the target only for an ADMIN.
  A CR's target is ignored (verified live: a CR sending another class's
  target was saved for their own class).

## Roles

- Admin page → People & roles:
  - search users;
  - set STUDENT / CR / ADMIN (`admin_set_role`);
  - grant a role to an email that hasn't signed in yet (`role_grants`,
    applied by `handle_new_user` on first sign-in).
- `oduri.johnson@gmail.com` is always ADMIN and can't be changed. The last
  admin can't be removed. A pending CR request is settled by the grant.

## Registration and profile

- Dropdowns from `orion_class_options()` (the classes that have a
  timetable): programme → semester → department → section. "Batch" and
  "section" are one field.
- Admission year: a dropdown up to the current year, also enforced in SQL.
- Roll number: required, 6–15 letters/digits, unique. The admission year is
  suggested from its prefix.
- The profile shows the roll number and admission year.

## CR notices are batch-specific

Every CR notice — pending or live — must carry exactly the CR's own
semester / department / batch / section (RLS). Only admins post campus-wide.

## Verification (2026-09-28)

- Live, rolled back: 18 checks.
  - CR pending notice without a class, or for another section: blocked.
    Own class: allowed.
  - Class update for another section: blocked. A CR editing a change:
    0 rows.
  - CR exams for another department: blocked. CR approving: blocked.
    CR granting admin: blocked.
  - A CR's target ignored; an admin's target used.
  - Admin approval writes linked exam rows.
  - Pre-authorising an email and promoting a student both work. Demoting
    the default admin is blocked.
  - Admin archiving works. Audit rows written.
- Registration, live and rolled back: a future year, a bad roll number and
  a duplicate roll number are all rejected; a valid registration stores
  both new fields.
- A temporary extra class, inserted and then deleted, showed up in "classes
  on 11 October" and "do I have class on the 11th?".
- A student is refused (403) on every new CR/admin endpoint.
- `tests/test_exams_changes_roles.py` (32 tests). Suite: 537 passing.
  Evaluation 142/142. Broad bank: 0 errors, the same 7 flags.
