# ORION --- AI-Powered Campus Assistant

> A centralized, intelligent campus information and assistance platform
> for students, faculty, Class Representatives (CRs), and
> administrators.

## 1. Project Overview

ORION is an AI-powered campus assistant designed to make institutional,
academic, and campus-life information accessible through a single
conversational interface.

Instead of forcing users to search through college websites, PDFs,
circulars, notices, emails, timetable files, screenshots, or multiple
communication channels, ORION provides a unified knowledge layer over
campus information.

The system combines:

-   Structured relational data for deterministic facts.
-   Document storage for source files.
-   OCR and document/table extraction for PDFs and images.
-   Vector search for semantic retrieval.
-   Retrieval-Augmented Generation (RAG) for grounded AI answers.
-   Role-based access control.
-   CR submission and administrator approval workflows.
-   Data lifecycle and expiry rules.
-   Personalization based on the authenticated user's academic context.

The most important architectural principle is:

> **Do not use the LLM as the source of truth. Use the database and
> approved knowledge base as the source of truth, and use the LLM to
> understand intent, retrieve relevant information, reason over
> retrieved information, and present the answer naturally.**

------------------------------------------------------------------------

## 2. Product Goals

ORION should:

1.  Centralize campus information.
2.  Make information discoverable using natural language.
3.  Provide accurate, source-grounded answers.
4.  Personalize answers according to the authenticated user.
5.  Support structured and unstructured institutional data.
6.  Allow CRs to contribute information without bypassing administrative
    control.
7.  Automatically handle information expiry and replacement.
8.  Protect sensitive and unnecessary personal information.
9.  Provide useful faculty, course, club, event, mess, timetable, and
    document discovery.
10. Remain inexpensive to operate during the prototype phase.

------------------------------------------------------------------------

## 3. Non-Goals

The prototype should not attempt to become a complete college ERP.

Do not build unnecessary functionality such as:

-   Fee payment.
-   Banking.
-   Official grade management.
-   Medical record management.
-   Payroll.
-   Hostel administration unless explicitly added later.
-   Attendance management unless an approved integration exists.
-   Storage of sensitive student records.
-   Autonomous modification of institutional records by the LLM.

If a requested feature falls outside the current scope, preserve the
existing architecture and document it as future scope instead of
silently expanding the product.

------------------------------------------------------------------------

## 4. Users and Roles

### Student

Students are primarily consumers of campus information.

They can:

-   Ask ORION questions.
-   View their timetable.
-   View academic calendar information.
-   View exam schedules.
-   Browse courses.
-   Search faculty.
-   Search institute documents.
-   View announcements relevant to them.
-   View clubs and events.
-   View mess schedules.
-   Receive personalized recommendations.

Students must not directly modify institutional information.

### Faculty

Faculty users can:

-   View relevant academic information.
-   View their schedules.
-   Maintain permitted profile information.
-   Be discoverable through faculty search.
-   View research interests, subjects, office location, office hours,
    and achievements where publicly available or institutionally
    approved.

Faculty availability should be inferred from schedules where reliable
schedule data exists.

### Class Representative (CR)

CRs are controlled data contributors.

They can submit:

-   Timetable PDFs.
-   Timetable images.
-   Mess schedules.
-   Announcements.
-   Notices.
-   Screenshots of emails or institutional information.
-   Other approved batch/class information.

A CR submission is never automatically authoritative.

### Administrator

Administrators are trusted data managers.

They can:

-   Approve submissions.
-   Reject submissions.
-   Edit approved data.
-   Archive data.
-   Manage users and roles.
-   Manage announcements.
-   Manage faculty data.
-   Review OCR output.
-   Manage data lifecycle.
-   Inspect audit logs.

------------------------------------------------------------------------

## 5. Core Product Areas

### 5.1 AI Chat

The primary interaction surface.

Users can ask questions in natural language, for example:

-   "What classes do I have tomorrow?"
-   "Where is my next class?"
-   "Who teaches Machine Learning?"
-   "Who works in NLP?"
-   "Recommend a faculty member for Computer Vision."
-   "What is today's mess menu?"
-   "What exams do I have next week?"
-   "Show the latest announcement for my batch."
-   "Find the document about academic regulations."

The chatbot must distinguish between:

-   Structured factual queries.
-   Semantic document queries.
-   Hybrid queries.
-   Recommendations.
-   Unsupported or ambiguous requests.

### 5.2 Timetable

Supports:

-   Daily view.
-   Weekly view.
-   Course.
-   Faculty.
-   Room.
-   Section/batch.
-   Schedule validity.

Timetable data should be represented structurally after extraction.

### 5.3 Academic Calendar

Contains:

-   Semester dates.
-   Holidays.
-   Registration deadlines.
-   Academic events.
-   Important institutional dates.

### 5.4 Exams

Contains:

-   Course.
-   Date.
-   Time.
-   Venue.
-   Examination type.
-   Batch/section.
-   Status.

Exam information should become inactive/expired after the relevant
examination period.

### 5.5 Courses

Contains:

-   Course code.
-   Course name.
-   Credits.
-   Department.
-   Faculty.
-   Prerequisites.
-   Syllabus/resources where approved.

### 5.6 Faculty Directory

Contains approved/public information such as:

-   Name.
-   Department.
-   Subjects.
-   Research interests.
-   Publications.
-   Achievements.
-   Office.
-   Office hours.
-   Schedule.

ORION can answer availability questions using schedule data.

It must not fabricate a faculty member's location.

### 5.7 Clubs and Events

Club information can include:

-   Club name.
-   Description.
-   Faculty coordinator.
-   Student lead.
-   Sub-leads.
-   Upcoming events.
-   Registration links.
-   Announcements.

### 5.8 Mess

Supports:

-   Daily menu.
-   Weekly menu.
-   Meal timings.
-   Uploaded schedule/menu documents.

### 5.9 Institute Documents

Documents may include:

-   Academic regulations.
-   Circulars.
-   Forms.
-   Policies.
-   Official notices.
-   Approved institutional documents.

Documents are indexed for semantic retrieval but remain linked to their
source metadata.

### 5.10 Announcements

Announcements may be:

-   Batch-specific.
-   Department-specific.
-   Institution-wide.
-   Event-specific.

Each announcement should have an explicit lifecycle.

------------------------------------------------------------------------

## 6. Data Ingestion Architecture

The ingestion pipeline is:

``` text
PDF / Image / Screenshot / Text
              |
              v
       File Validation
              |
              v
       OCR / Extraction
              |
              v
       Table Extraction
              |
              v
       Metadata Detection
              |
              v
      Sensitive Data Filter
              |
              v
       Human Verification
              |
              v
       CR Approval Queue
              |
              v
       Administrator Review
              |
          Approved?
         /        \
       No          Yes
       |            |
    Rejected        v
                Normalize
                    |
              Structured DB
                    +
               Vector Index
                    |
                    v
              ORION Retrieval
```

For administrator-originated trusted data, the workflow may be shortened
where appropriate, but all important mutations should still be
auditable.

------------------------------------------------------------------------

## 7. Structured vs Unstructured Data

Use PostgreSQL (or an equivalent relational database) for deterministic
information.

Examples:

-   Users.
-   Roles.
-   Courses.
-   Faculty.
-   Timetable entries.
-   Rooms.
-   Announcements.
-   Events.
-   Clubs.
-   Mess schedules.
-   Academic calendar.
-   Exam schedules.

Use vector search for semantic information such as:

-   Institute documents.
-   OCR-derived text.
-   Notices.
-   Circulars.
-   Faculty profile documents.
-   Long-form institutional content.

Do not put every database field into the vector database just because
embeddings are available.

------------------------------------------------------------------------

## 8. AI Routing

The backend should contain a routing/orchestration layer.

Conceptually:

``` text
User Query
    |
    v
Authentication + User Context
    |
    v
Intent / Query Classification
    |
    +--------------------+
    |                    |
Structured Query      Semantic Query
    |                    |
    v                    v
SQL / Domain APIs     Vector Search
    |                    |
    +---------+----------+
              |
              v
       Context Validation
              |
              v
          LLM / RAG
              |
              v
       Grounded Response
```

Examples:

### Structured

"What classes do I have at 10 AM?"

Use timetable data.

### Semantic

"What are the rules for course withdrawal?"

Use document retrieval.

### Hybrid

"Who teaches courses related to NLP and when can I meet them?"

Use faculty data + research information + timetable/availability.

The router should prefer deterministic sources whenever the answer is
deterministic.

------------------------------------------------------------------------

## 9. RAG Requirements

The RAG system should:

1.  Identify the relevant knowledge domain.
2.  Apply metadata filters before/while searching.
3.  Retrieve relevant chunks.
4.  Respect batch, department, role, and validity constraints.
5.  Provide source references when appropriate.
6.  Avoid answering from unsupported model memory.
7.  Say when information is unavailable or stale.

Never allow the LLM to silently invent:

-   Faculty schedules.
-   Room numbers.
-   Exam dates.
-   Timetable entries.
-   Official deadlines.
-   Announcements.
-   Registration links.

------------------------------------------------------------------------

## 10. Data Expiry and Validity

Every time-sensitive record should have lifecycle metadata.

Recommended fields:

``` text
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

  Data                  Lifecycle
  --------------------- ----------------------------------------------
  Announcement          Explicit expiry date
  Event                 Expires after event
  Exam                  Expires after exam period
  Timetable             Valid until replaced
  Mess menu             Daily/weekly validity
  Batch group link      Default expiry after 6 months unless renewed
  Faculty achievement   Long-lived/manual update
  Institute document    Manual/version-controlled
  Club event            Expires after completion

Expired data must not be returned as current information.

Archive rather than hard-delete records when audit/history is important.

------------------------------------------------------------------------

## 11. Sensitive Information

The ingestion system must detect and reject or redact unnecessary
sensitive information before it enters the knowledge base.

Examples include:

-   Government identification numbers.
-   Personal financial information.
-   Medical information.
-   Passwords.
-   Authentication tokens.
-   Private contact information.
-   Confidential internal communications.
-   Student disciplinary information.
-   Unnecessary personally identifiable information.

The system should follow a minimum-data principle:

> Store only information necessary for ORION's intended functionality.

------------------------------------------------------------------------

## 12. Advertisement and Irrelevant Content Handling

ORION should reject or exclude pure advertisements and irrelevant
promotional content.

However, useful information embedded inside a notice should not be
discarded solely because the document contains promotional language.

The ingestion pipeline should classify content into categories such as:

-   Official announcement.
-   Academic information.
-   Event.
-   Club information.
-   Timetable.
-   Administrative document.
-   Informational notice.
-   Advertisement.
-   Irrelevant/noise.

Pure advertisements should not enter the searchable institutional
knowledge base.

Information should expire based on relevance, not simply because it was
uploaded.

------------------------------------------------------------------------

## 13. CR Approval Workflow

CRs should never directly modify authoritative records.

``` text
CR
 |
 v
Upload
 |
 v
Validation
 |
 v
OCR / Extraction
 |
 v
Preview
 |
 v
Submit
 |
 v
Pending Approval
 |
 v
Admin Review
 |
 +------+
 |      |
Reject Approve
 |      |
 v      v
Reason  Publish
```

Every approval/rejection should be logged.

Rejected submissions should show a reason to the CR and allow
resubmission when appropriate.

------------------------------------------------------------------------

## 14. Required UI Screens

### Public/Auth

1.  Splash.
2.  Onboarding.
3.  Login.
4.  Role selection when applicable.

### Student

5.  Home dashboard.
6.  AI chat.
7.  Chat history.
8.  Timetable.
9.  Academic calendar.
10. Exams.
11. Courses.
12. Faculty directory.
13. Faculty details.
14. Clubs.
15. Club details.
16. Events.
17. Event details.
18. Mess schedule.
19. Institute documents.
20. Document viewer.
21. Announcements.
22. Notifications.
23. Global search.
24. Search results.
25. Profile.
26. Settings.

### CR

27. CR dashboard.
28. Upload.
29. OCR preview/verification.
30. Submission review.
31. Upload history.
32. Submission details.

### Admin

33. Admin dashboard.
34. Approval queue.
35. Submission review.
36. User management.
37. Faculty management.
38. Announcement management.
39. Data management.
40. Analytics.
41. Audit logs.

### Shared States

42. Loading.
43. Empty state.
44. Error.
45. Offline.
46. 404. 

------------------------------------------------------------------------

## 15. UX Principles

ORION should feel like a modern AI product, not a legacy college ERP.

Design principles:

-   AI-first.
-   Clean.
-   Fast.
-   Friendly.
-   Accessible.
-   Minimal cognitive load.
-   Mobile responsive.
-   Strong visual hierarchy.
-   Consistent navigation.
-   Clear status indicators.
-   Human-readable errors.
-   Progressive disclosure.

The main student experience should make the chatbot easy to access while
still providing dedicated screens for frequently used structured
information.

------------------------------------------------------------------------

## 16. Suggested Technology

The architecture may use:

### Frontend

-   Next.js / React.
-   TypeScript.
-   Tailwind CSS or equivalent.
-   Component library where appropriate.

### Backend

-   Python.
-   FastAPI.
-   Background workers where necessary.

### Database

-   PostgreSQL.
-   pgvector where practical.

### Authentication

-   Supabase Auth, OAuth, or equivalent.

### Storage

-   Supabase Storage, Google Cloud Storage, or equivalent.

### OCR

-   PaddleOCR.
-   Tesseract.
-   Cloud OCR when justified.

### LLM

Use an appropriate production API or local/open-source model depending
on cost, latency, and quality requirements.

### Deployment

The prototype should prioritize low/no-cost infrastructure.

Avoid introducing paid infrastructure unless there is a clear technical
reason.

------------------------------------------------------------------------

## 17. Repository Expectations

A clean project structure should separate concerns.

Example:

``` text
orion/
├── README.md
├── AGENTS.md
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── database/
│   └── decisions/
├── frontend/
├── backend/
├── ingestion/
├── ai/
├── tests/
├── scripts/
└── infrastructure/
```

The exact structure may differ depending on the current implementation.
Agents must inspect the existing repository before reorganizing it.

------------------------------------------------------------------------

## 18. Development Philosophy

Prioritize:

1.  Correctness.
2.  Security.
3.  Data integrity.
4.  Maintainability.
5.  Simplicity.
6.  Low operating cost.
7.  User experience.

Do not over-engineer the prototype.

Prefer a small number of reliable services over a large microservice
architecture.

------------------------------------------------------------------------

## 19. Definition of Done

A feature is not complete merely because the UI exists.

A feature is considered complete when:

-   UI works.
-   Backend/API works where applicable.
-   Database model exists where applicable.
-   Authorization is implemented.
-   Validation exists.
-   Error states exist.
-   Loading states exist.
-   Empty states exist.
-   Tests cover important behavior.
-   Documentation is updated.
-   Existing functionality remains intact.

------------------------------------------------------------------------

## 20. Important Rules for Contributors and Agents

Before changing the project:

1.  Inspect the repository.
2.  Read `AGENTS.md`.
3.  Identify the existing architecture.
4.  Reuse existing components and utilities.
5.  Do not duplicate functionality.
6.  Do not rewrite working systems without a reason.
7.  Preserve existing API contracts unless a change is required.
8.  Never bypass authorization.
9.  Never allow the LLM to directly mutate authoritative data.
10. Never expose sensitive information.
11. Keep database and vector knowledge synchronized.
12. Add tests for meaningful logic.
13. Update documentation when architecture changes.

------------------------------------------------------------------------

## 21. Current Product Priority

The prototype should prioritize:

### Phase 1

-   Authentication.
-   Student dashboard.
-   AI chat.
-   PostgreSQL.
-   Basic RAG.
-   Timetable.
-   Faculty.
-   Courses.
-   Announcements.

### Phase 2

-   CR upload.
-   OCR.
-   Admin approval.
-   Document ingestion.
-   Mess schedules.
-   Academic calendar.
-   Exams.

### Phase 3

-   Clubs.
-   Events.
-   Faculty recommendations.
-   Faculty availability.
-   Personalization.
-   Analytics.

### Phase 4

-   Optimization.
-   Notifications.
-   Mobile experience.
-   Integrations.

------------------------------------------------------------------------

## 22. Guiding Principle

ORION should answer one fundamental question:

> **"What does this student need to know right now, and what is the most
> reliable source for that answer?"**

The system should optimize for trustworthy, relevant, current
information rather than simply producing fluent AI responses.

# ORION Campus Companion

A campus assistant for IIIT Kottayam: a React/TanStack Start frontend, a
**FastAPI backend**, and Supabase (Postgres 17 + pgvector + GoTrue) as the
source of truth. The AI chat answers from real institutional data — routed to
SQL or vector retrieval first, then phrased by Gemini — never from model memory.

> **Status: 2026-09-21.** Runs on localhost only; nothing is deployed yet.
> What's built and what isn't: [`tasks-done.md`](tasks-done.md).
> Running log: [`Work-done.md`](Work-done.md).
> Hosting requirements and options:
> [`docs/backend-requirements.md`](docs/backend-requirements.md).

## Architecture

```
browser --httpOnly cookie--> TanStack Start SSR --fetch--> FastAPI (backend/)
                                                              | caller's JWT
                                                              v
                                                     Supabase (Postgres + RLS)
scripts/*.py (service-role) ---------------------------------> Supabase
```

The frontend never talks to Supabase directly. It calls the FastAPI service
through `src/lib/api-client.ts`; that service forwards the caller's own JWT, so
Row Level Security governs every read and write. The service-role key lives
only in the Python ingestion scripts.

## Running it

Both halves must run together.

```bash
# 1. API  (http://localhost:8000)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000

# 2. Frontend  (http://localhost:8080)
npm install
npm run dev
```

Configuration comes from one repo-root `.env` (see `.env.example`), read by
both sides. Required: `SUPABASE_URL`, `SUPABASE_ANON_KEY`. Optional but
expected: `GEMINI_API_KEY` (without it the chat degrades to retrieval-only and
says so), `API_BASE_URL`, `FRONTEND_ORIGIN`, `COOKIE_SECURE`,
`VITE_API_BASE_URL`. `SUPABASE_SECRET_KEY` is needed **only** for the ingestion
scripts.

```bash
npm run build      # production build
npm run lint       # eslint
npx tsc --noEmit   # typecheck
.venv/bin/python -m pytest tests -q   # 142 tests
```

## API surface

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/logout` · `GET /auth/me` · `POST /auth/register` (Google is the only sign-in method) |
| Google OAuth (frontend-driven) | `POST /auth/oauth/google/set-session` |
| Timetable | `GET /timetable/day` `/timetable/week` `/timetable/next` |
| Directory & campus | `GET /faculty` · `GET /mess/today` `/mess/week` · `GET /announcements` |
| CR | `POST /cr/access-request` · `GET /cr/access-request/status` · `GET`/`POST /cr/announcements` |
| Admin | `GET /admin/cr-requests` · `POST /admin/cr-requests/{id}/review` · `GET /admin/announcements` · `POST /admin/announcements/{id}/review` |
| AI | `POST /ai/ask` |

Sessions are httpOnly cookies set by the API (`SameSite=Lax`), so the browser
never holds a Supabase token — and the frontend and API must share a
registrable domain in any real deployment.

## Data pipelines (Python)

Ingestion is deliberately a separate, human-approved, idempotent step — every
run is audited in `ingestion_runs`:

```bash
# read-only inspection
.venv/bin/python scripts/inspect_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"

# dry run: extract -> normalize -> validate -> preview + validation JSON
.venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"

# audited import (needs SUPABASE_SECRET_KEY)
.venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf" \
  --import --approved-by admin@example.com
```

Other pipelines: `ingest_academic_calendar.py`, `ingest_classroom_details.py`,
`ingest_mess_menu.py`, `ingest_hostel_wardens.py`, `ingest_documents.py`
(PDF/OCR → chunks → Gemini embeddings), `rebuild_faculty.py`,
`reembed_gemini.py` (resumable vector backfill), `eval_retrieval.py`. OCR needs the
`tesseract` binary installed.

Details: [`docs/timetable.md`](docs/timetable.md),
[`docs/query-router.md`](docs/query-router.md),
[`docs/auth.md`](docs/auth.md) (database-side auth rules; its frontend sections
describe an architecture that was replaced on 2026-09-21).

## Live data (2026-09-21)

1,263 timetable entries (Sem 3/5/7) · 43 courses · 185 faculty · 30 rooms ·
30 academic-calendar events · 124 mess-menu rows · 78 hostel wardens ·
17 documents / 1,269 embedded chunks. Empty: `departments`, `exams`,
`ingestion_jobs`.

## Screens

Live data: `/login`, `/register`, `/timetable`, `/faculty`, `/mess`,
`/announcements`, `/cr`, the AI chat, and parts of `/dashboard`, `/admin`,
`/search`.

Still mock (`src/lib/mock-data.ts`): `/calendar`, `/clubs`, `/courses`,
`/documents`, `/exams`, `/profile`, `/notifications`.

Roles are `STUDENT`, `CR`, `ADMIN` (`FACULTY` exists in the schema but has no
signup path yet), assigned server-side — never chosen by the client. Admins can
enter every portal.

## Project structure

```
backend/
  main.py            FastAPI app
  app/api/           routers (auth, oauth, registration, cr, admin,
                     timetable, faculty, mess, announcements, ai)
  app/core/          config, cookies, redirects
  app/services/      GoTrue HTTP + Supabase client factories
  query/             router / retrieval / context / Gemini client
  timetable/         PDF extraction -> normalization -> validation -> import
src/
  routes/            file-based routes (one file per page)
  lib/api-client.ts  the only path from frontend to data
  components/        ui/ (shadcn), layout/, ai/, pixel/, shared/
scripts/             ingestion + verification CLIs
supabase/migrations/ 20 SQL migrations
tests/               142 Python tests
```

## Notes

- Timetable day/next-class behaviour is pinned to **IST** in SQL
  (`20260921000004_timetable_ist_timezone_fix.sql`) — don't reintroduce a
  process-clock dependency.
- Embeddings are Gemini `gemini-embedding-2` (768-dim) via
  `backend/query/embeddings.py` — one API call per semantic/hybrid question,
  none for structured ones; no local model in the API. Corpus and faculty
  vectors are stored in pgvector. Runbook (backfill/resume/verify/rollback):
  [`docs/embeddings.md`](docs/embeddings.md).
- To connect more real data, follow the pipeline pattern in
  `docs/timetable.md` rather than extending `src/lib/mock-data.ts`.
