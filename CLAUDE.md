# CLAUDE.md — ORION AI-Powered Campus Assistant

> Persistent engineering context for Claude Code / AI coding agents.
> Current project state: **2026-09-21** (§7, §10, §11, §15, §16, §17 re-measured
> that day against the live database and the merged tree, commit `146bb9a`).
>
> **Architecture changed on 2026-09-21.** ORION now has a real **FastAPI
> service** under `backend/` that the frontend calls over HTTP; the TypeScript
> query/data layer (`src/lib/query/`, `chat-api.ts`, `timetable-api.ts`,
> `supabase-server.ts`) was deleted in favour of the Python implementation, and
> sessions are httpOnly cookies set by that API. Deployment requirements:
> `docs/backend-requirements.md`. Current status: `tasks-done.md`.

## 1. Mission

ORION is an AI-powered campus assistant for students, faculty, Class Representatives (CRs), and administrators. It provides one conversational knowledge layer over institutional information including timetables, academic calendars, exams, courses, faculty, rooms, mess menus, announcements, clubs/events, regulations, policies, notices, PDFs, images, and OCR-derived content.

**Core rule:** PostgreSQL and the approved knowledge base are the source of truth. The LLM is a reasoning/interface layer, never the source of institutional facts.

For deterministic facts, use structured PostgreSQL. For semantic document questions, use retrieval. For questions requiring both, use hybrid retrieval. Never substitute model memory for institutional data.

---

## 2. Repository and infrastructure

- GitHub repository: `JohnsonOduri/orion-campus-nest`
- Default branch: `main`
- Repository visibility: private
- Supabase project: `ORION`
- Supabase project ref: `dgklugpgrnxhyjkvnacp`
- Supabase region: `ap-south-1`
- PostgreSQL: 17.x
- Current Supabase status: active/healthy

Before changing anything:

1. Read `README.md`.
2. Read `AGENTS.md`.
3. Read `docs/timetable.md`.
4. Inspect the repository tree and git status.
5. Inspect relevant `backend/`, `scripts/`, `src/`, tests, and migrations.
6. Inspect the **actual hosted Supabase schema** before writing SQL.
7. Reuse existing architecture; do not treat the repo as greenfield.

---

## 3. Product goals

ORION should:

1. Centralize campus information.
2. Make institutional information discoverable with natural language.
3. Provide grounded, accurate answers.
4. Personalize using authenticated academic context.
5. Support structured and unstructured information.
6. Convert PDFs/images/screenshots into usable data.
7. Let CRs contribute without bypassing administrator approval.
8. Handle validity and expiry.
9. Support timetable/course/faculty/room/exam/mess/document/announcement discovery.
10. Keep prototype infrastructure close to zero cost where practical.

ORION is **not** a college ERP. Do not add fees, payroll, medical records, grades, banking, or other out-of-scope systems unless explicitly requested.

---

## 4. Roles

### STUDENT
Consumers of campus information. Can ask questions, view own timetable/calendar/exams, browse courses/faculty/clubs/events/mess/documents, and receive recommendations. Cannot directly mutate authoritative institutional data.

### FACULTY
Can view relevant academic information and maintain permitted profile information. Approved/public data may include research interests, subjects, office, office hours, achievements, and schedules.

### CR
Controlled data contributor. Can submit timetable files, mess menus, announcements, notices, screenshots, and batch/class information. A CR submission is never authoritative until approved.

One deliberate exception (decided 2026-09-28, `docs/cr-workflow.md`): an
**academic** class notice (quiz, exam, assignment, class update, deadline)
that a CR posts for **their own class** goes live without review. The rule
is enforced in the `announcements` insert policy (not only the API), capped
at ~2 months, blocked when sensitive data is detected, audit-logged, and an
admin can take it down. One-off class changes (cancelled / rescheduled /
extra class on a date) are academic notices too and apply to every schedule
answer (`backend/query/schedule.py`). Weekly timetable changes and exam
schedules always need admin approval; an admin's own submissions are
approved immediately through the same RPCs. Every CR notice, pending or
live, is locked to the CR's own class (RLS). Roles are granted by admins
(`admin_set_role`, also pre-authorising an email);
`oduri.johnson@gmail.com` stays ADMIN.

### ADMIN
Trusted data manager. Can approve/reject submissions, manage authoritative data, users/roles, faculty, announcements, documents, OCR verification, lifecycle, and audit logs.

---

## 5. Source-of-truth matrix

| Query/data | Primary source |
|---|---|
| Next class | PostgreSQL timetable |
| Today/week timetable | PostgreSQL timetable |
| Faculty teaching a course | PostgreSQL faculty + timetable |
| Class room | PostgreSQL timetable/rooms |
| Exam date/time | PostgreSQL exams |
| Academic deadline/event | PostgreSQL academic_calendar |
| Mess menu | PostgreSQL mess_menus |
| Current announcement | PostgreSQL announcements |
| Faculty research interests | Structured faculty + approved semantic content |
| Regulations/policies | RAG over approved documents |
| Long institutional documents | RAG |
| Faculty + availability | Hybrid faculty + timetable |
| Faculty recommendation | Faculty/research data + semantic retrieval + optional schedule context |

Never route every query to RAG or an LLM.

---

## 6. Target architecture

```text
USER
 |
 v
Authentication / Session
 |
 v
Authenticated Academic Context
 |
 v
QUERY ROUTER
 /          |           STRUCTURED SEMANTIC    HYBRID
 |           |           |
SQL       pgvector    SQL + vector
 \           |           /
  +----------+----------+
             |
             v
      Context Validation
             |
             v
        LLM / Generator
             |
             v
    Grounded Answer + Sources
```

Runtime shape as actually deployed today (all on localhost):

```text
browser --httpOnly cookie--> TanStack Start SSR --fetch--> FastAPI (backend/)
                                                              | caller's JWT
                                                              v
                                                     Supabase (Postgres + RLS)
scripts/*.py (service-role) ---------------------------------> Supabase
```

Ingestion:

```text
PDF / Image / Screenshot / Text
        |
        v
File validation
        |
        v
OCR / extraction / table parsing
        |
        v
Metadata extraction
        |
        v
Sensitive-data filtering
        |
        v
Content classification
        |
        v
Human verification
        |
        v
CR submission / Admin approval
        |
        v
Normalization
        |
        +------------------+
        |                  |
        v                  v
 Structured DB       Documents + pgvector
```

---

# 7. COMPLETED: Semester 3 timetable vertical slice

Source:

`Data/Structured/Semester 3_TimeTable_Odd_2026.pdf`

Verified:

- 17 pages
- 608 final records
- 608 valid
- 0 rejected
- 0 duplicates
- 0 warnings
- 15 courses
- 37 faculty discovered
- 430 `timetable_entry_faculty` links
- 9 timetable periods
- slots 8/9 share the printed 5:00–7:00 PM range and are marked derived
- Saturday full-grid sports activity is emitted once per section
- no false faculty tokens such as `(T)`, `ECLABI`, `ICS`, `LAB`
- current timetable source is `Semester 3_TimeTable_Odd_2026.pdf`

The reference documentation is `docs/timetable.md`.

Existing implementation:

```text
backend/timetable/
  model.py
  extractor.py
  normalizer.py
  validator.py
  repository.py
  service.py

scripts/
  inspect_timetable.py
  ingest_timetable.py
  import_hosted.py
  verify_import.py
  supabase_sql.py
  create_test_students.py
  probe_supabase.py
  probe_schema.py

backend/app/            # FastAPI service (added 2026-09-21)
  main.py
  api/{auth,oauth,registration,cr,admin,timetable,faculty,mess,announcements,ai,deps}.py
  core/{config,cookies,redirects}.py
  services/{gotrue_http,supabase_clients}.py

backend/cr_ingest/      # CR uploads: rules, vision OCR, timetable drafts (2026-09-28)
  rules.py  vision.py  timetable_draft.py  pipeline.py

backend/query/          # routing / retrieval / context / Gemini client
  router.py
  retrieval.py
  context.py
  service.py
  llm_client.py
  embeddings.py         # the ONLY Gemini embedding caller (docs/embeddings.md)

src/lib/
  api-client.ts         # the ONLY way the frontend reaches data now
  timetable.ts

supabase/migrations/    # 23 files as of 2026-09-22
```

Pipeline:

```text
PDF -> extractor -> normalizer -> validator -> preview/validation JSON
    -> hosted adapter/import -> Supabase -> RPCs -> API -> frontend
```

Timetable is authoritative **structured** data. Do not replace it with RAG.

---

## 8. Timetable extraction rules

The PDF is positional and must be processed layout-aware.

Existing behavior:

- `pdfplumber` with geometry-first extraction.
- Period columns detected from digit-anchored headers.
- Word/PDF header artifacts tolerated.
- Cross-noon ranges handled correctly.
- Break columns detected structurally and never treated as classes.
- Day rows assigned using vertical overlap.
- Continuation rows attach to the preceding day.
- Per-page legends resolve course codes and faculty initials.
- Whole-grid activities are handled separately.
- Saturday merged sports cells become one record per section.
- Faculty initials are resolved only from supported evidence.
- Unknown courses/faculty are reported, never guessed.
- Exact duplicates use deterministic `source_uid`.

Do not replace this with naive text dumping.

---

## 9. Timetable normalization and validation

Canonical data includes:

```text
day
slot
start_time
end_time
course
faculty
entry_type
semester
programme
department
batch
section
source
validity
```

Entry types:

```text
class
lab
tutorial
seminar
project
club_activity
sports
break
other
```

Important:

- `(T)` means tutorial marker, not faculty initials.
- `(EC LAB I)`-style labels are not faculty initials.
- Never guess faculty mappings.
- Preserve multiple teachers using `timetable_entry_faculty`.
- `ord=0` represents the primary teacher where applicable.
- Validation rejects; it does not silently repair.

Validation includes:

- valid weekday
- start < end
- valid entry type
- resolvable teaching course
- resolvable faculty
- no impossible duplicates
- no invalid section/day overlaps
- context consistency
- valid source
- validity dates

Directory semantics:

```text
known_courses=None -> no directory available; cross-check skipped
known_courses={}    -> directory explicitly empty; teaching records fail checks
```

Do not change this distinction casually.

---

# 10. LIVE SUPABASE STATE

Measured **2026-09-21** by direct SQL against `dgklugpgrnxhyjkvnacp`.

```text
profiles                 7      (3 STUDENT, 2 CR, 2 ADMIN)
student_profiles         5

departments              0

faculty                185      (125 with email)
courses                 43

rooms                   30
room_allocations        26

timetable_periods       26
timetable_entries     1263      (608 S3 + 477 S5 + 178 S7)
timetable_entry_faculty 838

academic_calendar       30
exams                    0
mess_menus             124      (August 2026 only — now stale)
announcements            1      (status rejected)
hostel_wardens          78

documents               17
document_versions       17
document_chunks       1269      (384-dim MiniLM `embedding` on all rows; 768-dim Gemini `embedding_gemini` on 992 — backfill in progress, docs/embeddings.md)

ingestion_jobs           0
ingestion_runs          25
approval_requests        2      (cr_access_request, both approved)
audit_logs               3      (2 CR approvals, 1 announcement rejection)
```

`timetable_entries.room_id` is NULL for all 1,263 rows — the timetable PDFs
print no room per class period.

Public RPCs live on the project (all now captured in `supabase/migrations/`):

```text
orion_resolve_user        orion_student_context    orion_active_entries
orion_day_timetable       orion_week_timetable     orion_next_class
orion_entry_json          match_document_chunks    is_admin
handle_new_user           hook_restrict_signup_by_email_domain
prevent_role_self_escalation                       update_updated_at
complete_registration     get_my_profile
submit_cr_access_request  review_cr_access_request
submit_announcement       review_announcement
```

# 11. ACTUAL HOSTED SCHEMA — DO NOT ASSUME OLD COLUMN NAMES

The hosted schema is not identical to every earlier/local design. Always inspect it.

### courses

```text
id
course_code
course_name
credits
programme
specialisation
cohort
semester
prerequisites
syllabus_summary
status
created_at
updated_at
```

Do not assume `code` or `name`.

### rooms

```text
id
room_no
room_type
capacity
status
created_at
```

Do not assume `room_code`.

### timetable_entries

```text
id
course_id
faculty_id
room_id
day_of_week
slot_index
start_time
end_time
semester
programme
department
batch
section
entry_type
valid_from
valid_until
status
source_id
approved_at
approved_by
created_at
updated_at
source_uid
source_page
source_text
lab_batch
```

There is **no `branch` column** in the hosted table.

### faculty

```text
id
full_name
initials
department_id
email
office_location
office_hours
research_interests
status
created_at
updated_at
```

Additional columns added 2026-09-21: `phone`, `designation`, `profile_url`,
and `category` (**`text[]`** — a person can be both HOD and teaching faculty).

Current faculty state (2026-09-21):

```text
faculty rows      185
with email        125
categories        176 faculty / 17 administrative / 7 professional_support / 5 hod
```

Rebuilt from the institute directory CSVs by `scripts/rebuild_faculty.py`.
`department_id` is still unlinked because `departments` has 0 rows, and
`research_interests` is populated for only a minority of rows.

### academic_calendar

Uses `event_date`; do not assume `end_date`.

### mess_menus

Does not currently have `week_label`.

### documents

Uses `status` for lifecycle. Do not assume `approval_status`.

### ingestion_jobs

Uses `document_id`, `job_type`, `status`, etc. Do not assume `source_file`.

When a query gives PostgreSQL `42703 undefined_column`, inspect the actual schema instead of changing the schema just to satisfy the query.

---

# 12. Supabase table map

```text
profiles
departments
faculty
courses
rooms
room_allocations

timetable_entries
timetable_entry_faculty
timetable_periods

student_profiles

academic_calendar
exams
mess_menus
announcements

documents
document_versions
document_chunks

ingestion_jobs
ingestion_runs
approval_requests
audit_logs
```

RLS is enabled on the public tables. Do not disable it as a shortcut.

---

# 13. Supabase security model

## Normal user traffic

Use a request-scoped Supabase client carrying the caller's JWT.

Do **not** use service-role for ordinary user requests.

## Service role

Service-role bypasses RLS and is reserved for trusted server-side operations such as:

- ingestion
- controlled admin tooling
- maintenance
- integration tests

Never expose it in frontend/browser code or `NEXT_PUBLIC_*` variables. Never commit it.

## Google sign-in token handling

**Google is the only sign-in method** (removed 2026-09-22: password
signup/login, `/auth/signup` and `/auth/login`, no longer exist — the
account itself is created automatically on first Google sign-in via
`handle_new_user()`, same as before). Do not re-add a password login form
without discussing it — the whole session/cookie model below assumes
exactly one sign-in path.

The browser drives the OAuth/PKCE handshake itself (`src/lib/supabase-browser.ts`,
`src/routes/login.tsx`, `src/routes/auth.callback.tsx`), then POSTs the
resulting tokens to `POST /auth/oauth/google/set-session` exactly once,
which sets the same httpOnly cookies. This was chosen over the previous
fully backend-driven flow (`/auth/oauth/google/authorize` →
`/auth/oauth/google/callback`) because that design required the FastAPI
service to be running just to *start* the redirect to Google — a real
usability problem, not a hypothetical one.

Consequence, stated plainly rather than glossed over: for the duration of
the handshake, both tokens sit in the browser tab's `sessionStorage`
(never `localStorage` — a redirect-surviving PKCE flow needs *some*
persistent-across-navigation storage, and `sessionStorage` is the
narrowest option that still works; verified against
`@supabase/auth-js`'s `GoTrueClient` source, not assumed). Any XSS active
in that exact window could read them. `auth.callback.tsx` calls
`supabase.auth.signOut({ scope: "local" })` immediately after the
`set-session` POST succeeds, to shrink that window to "during the
handshake only" rather than "for as long as the tab stays open" — but it
does not eliminate it. Do not extend this pattern to any other auth path
without the same tradeoff being explicit.

## Session refresh (added 2026-09-29)

Supabase access tokens last an hour. Until this was built nothing ever read
`orion_refresh_token` back, so an hour into a session every call failed and
the user read the literal string **"JWT expired"** in the AI chat. Two
things were wrong and both are fixed:

- `backend/main.py` mapped *every* PostgREST `APIError` to **400**, so an
  expired token was indistinguishable from a validation error and nothing
  downstream could react. PGRST300/301/302 (and any message mentioning JWT)
  now return **401**. `42501` is deliberately excluded — that is an RLS
  privilege denial where refreshing changes nothing.
- `POST /auth/refresh` trades the refresh cookie for a new pair via GoTrue.
  `src/lib/api-client.ts` calls it once on a 401 and replays the request; a
  401 means Supabase rejected the JWT before executing anything, so the
  replay is safe even for a POST.

Supabase **rotates** the refresh token on every use, so concurrent refreshes
would spend the rotation on one of them and sign the user out — api-client
funnels all callers through a single in-flight promise. Refresh is
browser-only: during SSR there is no cookie jar to write the new pair back
into, so a 401 there falls through to the route guards. Session cookies also
now carry a 30-day `max_age` (they were session cookies, so closing the
browser ended a session whose refresh token was still valid).

## Identity rule

For normal callers:

```text
auth.uid() is authoritative
client-supplied p_user_id is ignored
```

Only trusted service-role / `orion_admin` tooling may explicitly act on behalf of another user.

Do not regress to:

```sql
coalesce(p_user_id, auth.uid())
```

for normal client calls.

## RLS

Prefer `SECURITY INVOKER`.

Do not add `SECURITY DEFINER` merely to bypass a permission error.

Never use user-editable `user_metadata` for authorization decisions.

---

## Department matching and roll numbers (added 2026-09-29)

Every semester's PDF spelled the same department differently — measured
live: sem 3 `CSE WITH SPECIALISATION IN AI AND DATA SCIENCE`, sem 5 `AI AND
DATA SCIENCE`, sem 7 `CSE WITH SPECIALIZATION IN AI & DATA SCIENCE` — and
the timetable RPCs compared `student_profiles.department` to
`timetable_entries.department` with exact `=`. A student therefore matched
their own semester and got a silently **empty** timetable in the next one.

Fixed by matching on a key, not a string: `orion_dept_key()` /
`orion_section_key()` (with `orion_dept_label()` / `orion_section_label()`
for display), mirroring `dept_key()` in `backend/cr_ingest/exam_draft.py`.
`orion_active_entries`, `orion_next_class`, `orion_day_timetable` and
`orion_week_timetable` all use them, and `orion_class_options` returns one
canonical name per department.

**`timetable_entries.department` is deliberately NOT rewritten**:
`source_uid` (`backend/timetable/model.py`) embeds the branch string, so
rewriting the column would change every natural key and a re-import of the
same PDF would insert duplicates instead of upserting.

`orion_parse_roll()` reads the institute's own encoding —
`2024BCS0086` = 2024 intake, `BCS` branch, serial 86 — where
`BCS`→CSE, `BCD`→AI&DS, `BCY`→Cyber Security, `BEC`→ECE, and
**batch = serial % 4 + 1** (86 % 4 = 2 → batch 3 → section `III`).
`complete_registration` derives department, section and admission year from
it and **ignores what the form posted**, because the roll number is a record
and a dropdown is a guess; it falls back to the posted values only when the
roll number doesn't parse. `src/lib/roll.ts` mirrors this for display only —
keep the two in step.

Institute addresses carry the same roll number
(`asharani24bcs86@iiitkottayam.ac.in` → `2024BCS0086`, serial not
zero-padded), so `rollContradictsEmail()` warns when the typed roll and the
signed-in address disagree on branch or serial — a real one-letter slip
(`BCD` for `BCS`) otherwise registers a student into another department's
timetable silently.

**Email parsing is advisory only and must stay that way.** It is a warning,
never a gate, and it is confined to `src/lib/roll.ts` + `register.tsx` — the
login path (`login.tsx`, `auth.callback.tsx`, `supabase-browser.ts`,
`/auth/oauth/google/set-session`) never parses an address, so no identity can
be locked out by it. Most institute addresses carry no roll number at all:
**0 of 125 faculty addresses** do (they are name-based, e.g. `amenon@`, `rkrishnan@`),
nor do admins (`oduri.johnson@gmail.com`, `orion-test-admin@`), nor students
whose address was renamed. Both helpers return null/false whenever either
side is unreadable, so "can't tell" means "stay quiet" — locked in by
`src/lib/roll.test.ts`'s "identities that carry no roll number" block.
Likewise a non-B.Tech or legacy roll (`MT24CS001`, `PHD2024001`) simply
parses to null and `complete_registration` keeps whatever the dropdowns
picked (`derived_from_roll: false`) — verified end-to-end. Do not turn either
check into a hard requirement.

Registration gotcha worth keeping: department/section are only *required* of
the form when the roll number can't supply them (`superRefine` in
`register.tsx`). They were unconditionally required once, which made the form
unsubmittable — their inputs aren't rendered in the derived case, so the
semester dropdown's cascade-reset blanked them and the "Required" error had
nowhere to appear. The button simply did nothing.

# 14. Timetable RPC behavior

Existing conceptual RPCs:

```text
orion_student_context
orion_active_entries
orion_day_timetable
orion_week_timetable
orion_next_class
```

`orion_student_context` reads the authenticated student's:

```text
semester
programme
department
batch
section
```

from `student_profiles`.

`orion_next_class` uses a day-offset model:

```text
offset 0 -> same day; ongoing class still counts
offset 1..6 -> remaining days of current week
offset 7 -> same weekday next week
```

Validity is evaluated against the occurrence date.

Only `status='active'` is considered.

`break` is always excluded.

`sports` and `club_activity` are excluded unless `include_activities=true`.

Do not hard-code weekdays.

The implementation pins relevant day/time behavior consistently to UTC.

---

# 15. Existing API implementation

**The API is a FastAPI service in `backend/`** (`uvicorn main:app`), not a
TanStack Start route handler. Routers:

```text
auth           /auth/logout /auth/me /auth/refresh   (Google is the only
               sign-in method; no /auth/signup or /auth/login — removed
               2026-09-22. /auth/refresh added 2026-09-29 — see §13)
oauth          /auth/oauth/google/set-session   (frontend-driven; browser
               drives the Google/PKCE handshake via supabase-js, POSTs the
               resulting tokens here once — see §13)
registration   /auth/register                     -> complete_registration
cr             /cr/access-request [+ /status]  /cr/announcements [GET, POST, /preview]
               /cr/uploads [+ /url]  /cr/timetable/{current,check,submit,submissions}
               /cr/exams/{current,check,submit,submissions}  /cr/class-changes/preview  /cr/classes
admin          /admin/cr-requests [+ /{id}/review]
               /admin/exam-submissions [+ /{id}/review]  /admin/users  /admin/roles  /admin/role-grants
               /admin/announcements [+ /{id}/review, /live, /{id}/archive]
               /admin/timetable-submissions [+ /{id}/review]
timetable      /timetable/day  /timetable/week  /timetable/next
faculty        /faculty
mess           /mess/today  /mess/week
announcements  /announcements
ai             /ai/ask  /ai/conversations [+ /{id}/messages, DELETE /{id}]
campus         /calendar /exams /courses /courses/mine /documents /me/academic
health         /health
```

Rules that must not be regressed:

- **Every router forwards the caller's own JWT.** No router uses the
  service-role key to serve a user request; RLS is the real boundary and
  `backend/app/api/deps.py` adds a fast 401/403 on top.
- **Sessions are httpOnly cookies set by this service** (`orion_access_token`,
  `orion_refresh_token`, `SameSite=Lax`, `Secure` via `COOKIE_SECURE`) — the
  browser never holds a Supabase token. Consequence: the frontend and the API
  must be served from the same registrable domain, or the cookie is not sent.
- CORS is locked to one origin (`FRONTEND_ORIGIN`) with credentials enabled.
- PostgREST `APIError`s (from RPC-level `raise exception`) are mapped to a
  clean 400, not an opaque 500.
- The frontend reaches all of this through `src/lib/api-client.ts`, which
  forwards the incoming `Cookie` header during SSR.
- **Query understanding is layered and each layer is separately testable**
  (2026-09-24, docs/query-router.md): `followup` (text rewrite, then
  plan-level slot inheritance) → `router.classify` → `tempo` (relative
  dates resolved ONCE onto `QueryPlan.resolved_date`) → retrieval →
  `compose` (relevance floor before any passage is quoted). Rules that
  must not regress: a structured-domain question never falls through to
  document search; retrieval never re-parses a date phrase the router
  already resolved; a document passage below the relevance floor is not
  shown at all. Failures are attributed per stage by
  `scripts/eval_pipeline.py` (ROUTER / ENTITY_RESOLUTION /
  DATE_RESOLUTION / RETRIEVAL / ANSWER_GROUNDING); every answer logs a
  trace, and `ORION_DEBUG_TRACE=1` returns it from `/ai/ask` (dev only).
  Added 2026-09-28 (docs/query-router.md top): `lexicon` spelling
  correction toward campus vocabulary runs first in `router.classify`;
  `intents` (TF-IDF classifier) is consulted only when the regex rules
  find nothing; fuzzy faculty names (`campus.match_faculty_name`) never
  guess between two people. Misrouted phrasing → add examples to
  `intents.EXAMPLES`, don't bolt on another regex.
  Time questions are answered by constraint, not by dumping the day
  (`query/timeq.py`); mess serving times live in `mess_meal_timings`.
- **Voice output goes through `ttsService` (`src/lib/ai/tts.ts`) only.** UI
  code never calls `speechSynthesis` directly. As of 2026-09-23 there is no
  backend TTS at all: `KokoroBrowserProvider` (`src/lib/ai/tts-providers.ts`)
  runs Kokoro (82M params, ONNX) entirely client-side via `kokoro-js`
  (WebGPU preferred, WASM fallback), lazily loaded once per tab on first
  mic/speaker use; `BrowserTTSProvider` (SpeechSynthesis) is the automatic
  fallback. Voice/speed are hard-coded (`af_heart`, speed 1) — no per-user
  config, no server involved, no `TTS_PROVIDER`/`KOKORO_*` env vars
  (docs/tts.md).

`src/lib/query/`, `src/lib/chat-api.ts`, `src/lib/timetable-api.ts` and
`src/lib/supabase-server.ts` **no longer exist** — `backend/query/` is the one
implementation of routing/retrieval/context. Do not recreate the TS port.

# 16. Existing verification

Last run **2026-09-21** on the merged tree (commit `146bb9a`):

```text
.venv/bin/python -m pytest tests -q   => 142 passed
npx tsc --noEmit                      => clean
npm run build                         => passes
```

Update 2026-09-28: `pytest` 368 passed; `scripts/eval_pipeline.py` 100/100
(incl. 60 cases from `AI-Tests/`, 9/60 before); `run_ai_task.py` 173
questions, 0 errors. Results: `AI-Tests-results.md`.

Update 2026-09-22 (evening): `pytest` 262 passed, `npm test` 23 passed, build
passes; the AI question bank (`AI-task.md`, 134 questions) runs end-to-end via
`scripts/run_ai_task.py` with 0 errors. Earlier the same day: `npm test` (Vitest) now covers the speech sanitizer and
the `AudioManager` (interrupts, stale audio, Kokoro→browser fallback); pytest
adds `tests/test_tts_router.py` and `tests/test_ai_router.py`.

Original note — test coverage was Python-side only: extraction, normalization, validation,
idempotency, expiry, timetable retrieval, next-class behaviour, activities,
identity isolation, query routing, context, service. **There are no tests for
the FastAPI routers** (auth, cookies, role gating, CR/admin review) and none
for the frontend.

There are known pre-existing repo-wide formatting/lint issues in untouched
areas. Do not launch a broad formatting rewrite just to fix unrelated legacy
files.

# 17. NOT COMPLETE YET

Do not claim the system is finished. As of 2026-09-21:

### Deployed anywhere
- **Not yet — configured but not applied.** `render.yaml` (repo root, added
  2026-09-22) defines the one Python web service for `backend/`, torch-free,
  health-checked at `/health`. It has not been created/deployed on Render in
  this session (no `RENDER_API_KEY`/dashboard access here) — the manual steps
  are in `docs/backend-requirements.md` §7. Cookie, CORS and OAuth redirect
  configuration are still localhost defaults until real Render/custom-domain
  URLs are filled into the dashboard env vars. See `docs/backend-requirements.md`
  before provisioning anything — the `SameSite=Lax` session cookie constrains
  where the frontend and API may live relative to each other (confirmed:
  `onrender.com` is on the Public Suffix List, so two different `onrender.com`
  services are different "sites" and will NOT share Lax cookies).

### CR document upload / OCR pipeline
- **Built 2026-09-28 for timetables and class announcements**
  (`docs/cr-workflow.md`, `backend/cr_ingest/`, bucket `cr-uploads`):
  upload → OCR/extraction → CR edits → timetable changes need admin
  approval (`review_cr_timetable`), academic notices for the CR's own
  class go live immediately (enforced by RLS, audit-logged, admin can take
  down). Still not built: regulation/policy *documents* (RAG corpus) from
  CRs, and clean-up of abandoned uploads.

### Structured data
- `exams` = 0 rows until an exam schedule is approved — the upload/review flow exists (docs/cr-workflow.md round 3); the sample Semester V end-sem PDF reads correctly but hasn't been published.
- `departments` = 0; `faculty.department_id` unlinked.
- `mess_menus` covers August 2026 only — that month has passed.
- `timetable_entries.room_id` NULL for all 1,263 rows.
- `courses` has only code/name/credits; curriculum fields unpopulated.

### RAG / AI
- Generation is live (Gemini `gemini-3.5-flash-lite` via `POST /ai/ask`), but
  there is **no reranking, no streaming, and no post-generation grounding
  check**, and the authenticated student's cohort is not consistently applied
  to semantic retrieval.
- Embeddings moved to Gemini `gemini-embedding-2` (768-dim) on 2026-09-22;
  faculty research vectors are stored (`faculty.research_embedding`), no
  longer re-embedded per request. **Backfill incomplete**: 992/1,269 chunks
  and 0/146 faculty rows embedded (free-tier daily cap) — run
  `scripts/reembed_gemini.py` and keep `ORION_EMBEDDING_PROVIDER=minilm`
  until it finishes. The MiniLM column/RPC remain as the rollback path
  (docs/embeddings.md).

### AI answers (2026-09-22)
- **Gemini is optional now.** Every answer is composed from Supabase rows or a
  quoted document clause (`backend/query/compose.py`, `documents.py`). Document
  search is **hybrid** since 2026-09-28: Postgres full-text
  (`search_document_chunks`) fused with vector search
  (`search_document_chunks_semantic`), and vector similarity vetoes passages
  that only share words with the question. The vector side is an enhancement:
  if Gemini fails or `ORION_VECTOR_SEARCH=off`, full-text alone answers. Keep
  it that way: never make an answer depend on the LLM or the embedding API. See
  `docs/query-router.md` (top) and `production-tasks.md`.

### UI
- Live (2026-09-22): every page — no route imports mock data any more
  (`src/lib/mock-data.ts` deleted). Earlier list kept below for history.
- Live: `/timetable`, `/faculty`, `/mess`, `/announcements`, `/cr`, `/login`,
  `/register`, the AI chat.
- Still mock: `/calendar`, `/clubs`, `/courses`, `/documents`, `/exams`,
  `/profile`, `/notifications`, plus parts of `/dashboard`, `/admin`,
  `/search`, `/ai`.

### Process
- `docs/decisions/` does not exist, though `backend/app/core/config.py` already
  cites `docs/decisions/orion-auth-plan.md`.
- Hosted Supabase migration *tracking* is still empty even though the migration
  files now match the live schema.

# 18. Recommended implementation order

## Phase 1 — Finish structured data

1. Import/normalize faculty JSON.
2. Process Semester 5 timetable.
3. Process Semester 7 timetable.
4. Process Classroom Details.
5. Populate rooms and room allocations.
6. Process Academic Calendar.
7. Populate academic_calendar.
8. Process exams.
9. Process mess menu.
10. Populate/normalize departments.
11. Verify foreign keys, source IDs, validity, lifecycle, and query behavior.

## Phase 2 — Document ingestion

1. Upload/storage.
2. PDF/image extraction.
3. OCR.
4. Classification.
5. Sensitive-data detection/redaction.
6. Metadata.
7. Versioning.
8. Logical chunking.
9. Embeddings.
10. pgvector.
11. Retrieval filters.

## Phase 3 — CR workflow

```text
CR upload
 -> validate
 -> OCR/extract
 -> confidence check
 -> classify
 -> sensitive-data check
 -> preview
 -> submit
 -> approval_requests
 -> admin review
 -> approve/reject
 -> publish
 -> audit_logs
```

CR uploads must never directly modify authoritative tables.

## Phase 4 — Query router

Classify:

```text
STRUCTURED
SEMANTIC
HYBRID
RECOMMENDATION
UNSUPPORTED / AMBIGUOUS
```

Examples:

```text
"What is my next class?"
=> STRUCTURED

"What are the rules for course withdrawal?"
=> SEMANTIC

"Which faculty work on NLP and when can I meet them?"
=> HYBRID

"Recommend a faculty member for computer vision."
=> RECOMMENDATION
```

## Phase 5 — Grounded generation

```text
query
 -> route
 -> retrieve
 -> validate
 -> context
 -> generate
 -> grounding check
 -> answer
```

For deterministic results, return structured results directly when practical instead of spending an LLM call.

## Phase 6 — Product integration

Integrate dashboard, chat, timetable, calendar, exams, courses, faculty, mess, documents, announcements, CR workflows, and admin approval.

---

# 19. RAG design

Use PostgreSQL + pgvector for the prototype unless scale proves otherwise.

`document_chunks` contains:

```text
id
document_id
version_id
chunk_index
content
embedding
page_start
page_end
section_title
metadata
confidence_score
created_at
```

Useful metadata:

```text
document_id
source_id
document_type
category
programme
specialisation
cohort
department
role
valid_from
valid_until
status
page
section
confidence
```

Do not vectorize every relational record.

Chunk long documents by logical sections where possible. An initial target of roughly 500–800 tokens is reasonable, but semantic boundaries matter more than an arbitrary size.

---

# 20. Critical RAG rule: cohort isolation

The corpus includes different regulation cohorts, including:

```text
UG Regulations 26 onwards
UG Regulations 21-25
```

These must remain cohort-aware.

Never retrieve a rule from one cohort and present it as applying to another.

RAG filters must respect:

- cohort
- programme
- specialisation
- department
- role
- validity
- approval status

If evidence is insufficient, say so.

---

# 21. Data lifecycle

Time-sensitive records should use:

```text
created_at
updated_at
valid_from
valid_until
status
source_id
approved_at
approved_by
```

Examples:

| Data | Lifecycle |
|---|---|
| Timetable | Until superseded |
| Exam | Through exam period |
| Academic event | Relevant date/range |
| Mess menu | Daily/weekly |
| Announcement | Explicit expiry |
| Club event | Until completion |
| Batch group link | Normally 6 months unless renewed |
| Regulation | Version-controlled |
| Faculty achievement | Manual update/review |

Expired information must not be returned as current and must be filtered out of current RAG retrieval.

---

# 22. Sensitive data

Reject/redact unnecessary:

- government IDs
- passwords
- API keys
- authentication tokens
- financial information
- medical information
- unnecessary private contact data
- confidential communications
- disciplinary information
- unnecessary PII

Minimum-data principle:

> If ORION does not need the field, do not store it.

Do not log secrets or sensitive document contents unnecessarily.

---

# 23. Content classification

Potential categories:

```text
OFFICIAL
ACADEMIC
ANNOUNCEMENT
EVENT
TIMETABLE
CLUB
DOCUMENT
ADVERTISEMENT
IRRELEVANT
```

Pure advertisements should not become institutional knowledge.

Do not reject an official notice merely because it contains promotional language if it also contains useful institutional information.

---

# 24. Faculty data

Structured faculty:

```text
name
initials
department
email
office
office hours
status
```

Semantic faculty information:

```text
research interests
publications
achievements
areas of expertise
```

Faculty availability is derived from:

```text
faculty profile
+
current date/time
+
timetable
+
validity
```

Never claim a current physical location unless reliable data supports it.

Safer response:

> I don't have enough current schedule information to determine their availability.

---

# 25. Personalization

May use:

- authenticated user
- semester
- programme
- department
- batch
- section
- courses
- approved interests
- club memberships

Do not infer sensitive characteristics.

Personalization never overrides authorization.

Academic context should come from trusted server-side data, not arbitrary query parameters.

---

# 26. Frontend direction

ORION should feel like a modern AI product rather than a legacy college ERP.

Qualities:

- AI-first
- clean
- premium
- friendly
- fast
- responsive
- accessible
- strong visual hierarchy
- useful information density
- clear loading/error/empty states

Reuse existing design components/tokens before creating new ones.

---

# 27. API rules

Every protected endpoint must:

- authenticate
- authorize
- validate input
- use server-side identity
- enforce ownership
- return consistent errors
- avoid leaking internals

Never trust:

- client-side role checks
- hidden UI buttons
- request-body role fields
- request-body ownership
- client-supplied user IDs

---

# 28. Database rules

Use PostgreSQL for deterministic data.

Use pgvector for semantic data.

Avoid a separate vector DB unless technically justified.

For schema changes:

1. Inspect current hosted schema.
2. Inspect existing migrations.
3. Understand consumers.
4. Prefer additive/idempotent changes.
5. Test.
6. Verify using SQL.
7. Update documentation.

Never modify production schema just to accommodate an incorrect query.

---

# 29. Supabase operating rules

When implementing Supabase-specific functionality, verify current Supabase documentation because APIs/features evolve.

After changes:

- verify behavior with a real query/test
- preserve RLS
- check security/performance implications
- verify Data API access if new tables are exposed
- keep migrations version-controlled

Do not weaken authorization to make development easier.

---

# 30. Cost strategy

This is a prototype.

Prefer:

```text
Supabase PostgreSQL
+
pgvector
+
serverless/container backend
+
managed object storage
```

Avoid unnecessary:

- GPU servers
- always-on worker fleets
- dedicated vector DB
- multiple redundant cloud services

Reduce LLM spend with:

- deterministic SQL routing
- metadata filtering
- small context
- caching where safe
- smaller models for classification
- no LLM call when SQL can answer directly

---

# 31. Testing requirements

Test:

### Structured
- timetable
- context resolution
- expiry
- rooms
- exams
- announcements

### Security
- authentication
- authorization
- role restrictions
- user isolation
- service-role-only operations

### Ingestion
- extraction
- OCR artifacts
- normalization
- validation
- confidence
- duplicates
- idempotency

### CR
- upload
- pending
- approve
- reject
- audit

### RAG
- metadata filters
- cohort isolation
- expiry
- grounding
- source/page attribution
- no-answer behavior

### Router
Representative routing:

```text
next class -> structured
regulations -> semantic
faculty + availability -> hybrid
faculty recommendation -> recommendation
unsupported -> safe response/clarification
```

---

# 32. Observability and auditability

Track, where useful:

- API failures
- authentication failures
- ingestion failures
- OCR failures
- approval actions
- routing decisions
- retrieval failures
- latency
- model/API failures

Never log credentials, tokens, secrets, or unnecessary personal data.

Important mutations should answer:

```text
Who changed it?
What changed?
When?
What source caused it?
Who approved it?
What was the previous version?
```

---

# 33. Git rules

Keep commits focused:

```text
feat: import semester 5 timetable
feat: add academic calendar ingestion
feat: add document chunking pipeline
fix: filter expired RAG documents
fix: enforce authenticated timetable identity
feat: add CR approval flow
```

Never commit secrets, credentials, or unnecessary personal data.

Before a PR:

- run relevant tests
- run build/typecheck
- inspect diff
- check security implications
- update docs

---

# 34. Common schema/query pitfalls

Do not assume:

```text
timetable_entries.branch       # DOES NOT EXIST
courses.code                   # DOES NOT EXIST
courses.name                   # DOES NOT EXIST
rooms.room_code                # DOES NOT EXIST
academic_calendar.end_date     # DOES NOT EXIST
mess_menus.week_label          # DOES NOT EXIST
documents.approval_status      # DOES NOT EXIST
ingestion_jobs.source_file     # DOES NOT EXIST
```

Use the actual hosted schema.

---

# 35. First task for every new Claude session

```text
1. Read CLAUDE.md.
2. Read README.md.
3. Read AGENTS.md.
4. Inspect git status.
5. Inspect relevant source files.
6. Inspect relevant Supabase schema.
7. Determine what already exists.
8. State a minimal implementation plan.
9. Implement only the requested scope.
10. Run relevant tests.
11. Verify database changes if applicable.
12. Update documentation / Work-done if appropriate.
13. Summarize changed files and verification.
```

Do not immediately code after reading this file.

---

# 36. Immediate roadmap

Updated 2026-09-21 — the original structured-data ordering is largely done.
Unless the user asks for something else, prioritize:

1. **Deploy** (see `docs/backend-requirements.md`): one warm container in
   ap-south-1 for the FastAPI service, the frontend on the same registrable
   domain, `COOKIE_SECURE=true`, production redirect URL allowlisted.
2. **CR document upload → OCR → admin approval** — the last big unbuilt slice,
   and the reason a second (worker) container will be needed.
3. **AI answer quality**: apply the student's cohort to semantic retrieval;
   add a grounding check. (Stored faculty embeddings: done 2026-09-22 with the
   Gemini embedding migration.)
4. **Finish UI wiring** (`/calendar`, `/courses`, `/exams`, `/documents`,
   `/clubs`, `/notifications`, and the mock remnants elsewhere).
5. **Data gaps**: a current mess menu, an exams source, `departments` + the
   department-spelling decision, room↔timetable.
6. **Tests for the FastAPI layer** — currently zero — and the `docs/decisions/`
   ADR log.

The Semester 3 timetable pipeline remains the reference implementation for
future structured ingestion.

# 37. Definition of done

A feature is done only when:

- correct source of truth is used
- authorization is enforced
- validation exists
- errors are handled
- tests exist
- relevant tests pass
- database changes are verified
- no secrets are exposed
- documentation is updated
- validity/expiry is considered
- auditability is preserved where required
- representative real data is tested where practical

---

# 38. Golden rule

Before implementing any ORION feature, answer:

```text
1. What is the authoritative source?
2. Who may modify it?
3. Who may read it?
4. How long is it valid?
5. How do we prove the answer is grounded?
```

If those five questions cannot be answered, the feature design is incomplete.

**Optimize ORION for correctness, security, freshness, explainability, and usefulness — not merely for sounding intelligent.**
