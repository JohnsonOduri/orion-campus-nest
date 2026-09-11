# ORION — Phase & Task Breakdown (Done vs. Not Done)

> Cross-referenced against `AGENTS.md` §21 (Current Product Priority), `README.md`
> (product spec), `Data/analysis.md` / `Data/Contents.md` (ingestion plan), and the
> live Supabase project **"ORION"** (`dgklugpgrnxhyjkvnacp`, ap-south-1).
> Status markers: ✅ done · 🟡 partial · ⬜ not started.
> When a task moves state, update `work-done.md` with a dated entry **and** flip
> the marker here — the two files must stay in sync.

---

## Phase 0 — Frontend Prototype Shell

| Task | Status | Notes |
|---|---|---|
| React 19 + TypeScript + TanStack Start/Router scaffold | ✅ | Vite 8, file-based routing (`src/routes/`) |
| Design system (Tailwind v4 + shadcn/ui + Radix + lucide) | ✅ | `src/components/ui/` |
| App shell (sidebar/topbar/mobile nav/theme toggle) | ✅ | `src/components/layout/app-shell.tsx` |
| Zustand store (role, user, onboarding, theme, sidebar, AI panel) | ✅ | `src/store/orion.ts`, persisted to `localStorage` |
| All 46 required UI screens click-through (README §14) | ✅ | Every route file exists in `src/routes/`: landing, login, onboarding, role, dashboard, timetable, calendar, courses, faculty, exams, mess, clubs, announcements, events, documents, ai, search, notifications, profile, settings, cr, admin |
| Pixel-art decoration system | ✅ | `src/components/pixel/pixel-art.tsx` |
| Mock dataset backing every screen | ✅ | `src/lib/mock-data.ts` (175 lines — courses, faculty, mess, clubs, exams, etc.) |
| Floating AI chat panel | 🟡 | `src/components/ai/ai-chat.tsx` — UI only, canned responses from mock data, **no LLM/RAG call** |

**Everything in Phase 0 is UI-only.** No screen except Timetable is backed by a real API/DB.

---

## Phase 1 — Auth, Student Dashboard, AI Chat, PostgreSQL, Basic RAG, Timetable, Faculty, Courses, Announcements

### 1.1 Authentication — ⬜ **Not started**
- `/login` route exists but is **UI only**: email/student-ID tabs, no `supabase.auth.*` call anywhere in `src/` (verified — zero matches).
- No session/JWT wiring in the frontend; no protected-route logic; no role-based redirect after login.
- `profiles` table exists in Supabase (id, full_name, email, role, department, admission_year, semester, section, batch) with RLS enabled, FK to `auth.users`, and a `handle_new_user()` trigger function — **but it currently has a security-definer/anon-exec advisor warning** (see Supabase Findings below) and is not yet exercised by any real signup flow from the app.
- **Needed:** wire Supabase Auth (email/password or OTP) into `/login`, `/onboarding`, `/role`; session persistence; route guards per role (STUDENT/FACULTY/CR/ADMIN); replace store's simulated role with the authenticated user's `profiles.role`.

### 1.2 Student Dashboard — 🟡 Partial
- UI complete (`src/routes/dashboard.tsx`) with today's classes, attendance charts, announcements — **all from mock data**, not live queries.
- **Needed:** wire dashboard's "today's classes" to the already-live `orion_day_timetable` RPC; announcements panel needs the `announcements` table populated + queried (table exists, 0 rows).

### 1.3 AI Chat — ⬜ **Not started (no RAG)**
- `src/components/ai/ai-chat.tsx` is a floating panel with hardcoded/canned responses.
- No query router, no LLM call, no embeddings pipeline, no context assembly, no citation handling — none of AGENTS.md §16/README §8-9 is implemented.
- **DB is ready for this**: `document_chunks` table has a `vector` column (pgvector 0.8.2 installed under `extensions` schema) with an HNSW index (`chunks_embedding_hnsw_idx`, currently unused/empty) and a `metadata` JSONB GIN index — the storage layer for RAG exists but is **empty and unconnected**.
- **Needed:** backend routing/orchestration layer (structured vs semantic vs hybrid per AGENTS.md §4), embedding generation + population of `document_chunks`, retrieval + reranking, LLM call, citation/validation step, wiring into `/ai` route and the chat panel.

### 1.4 PostgreSQL — ✅ **Done (schema layer)**
- Live Supabase Postgres 17.6 project provisioned, `pgvector` extension installed.
- Full relational schema exists for nearly every product area (see **Supabase Schema Snapshot** below) — courses, faculty, rooms, timetable, academic_calendar, exams, mess_menus, announcements, documents (+ versions/chunks), ingestion_jobs, approval_requests, audit_logs, student_profiles, profiles, ingestion_runs.
- RLS enabled on every table. `orion_resolve_user` identity pattern (never trust client-supplied user ids) implemented and used throughout the timetable RPCs.
- ⚠️ Migrations are **only tracked as raw files in `supabase/migrations/`** — `list_migrations` against the live project returns empty, meaning the migration history table itself isn't in sync/recorded on the hosted project (schema was applied via the Management API / SQL runner per `docs/timetable.md` §13, not `supabase db push`). Worth reconciling so future `supabase migration` commands don't drift.

### 1.5 Basic RAG — ⬜ **Not started** (see 1.3 — same gap, DB scaffolding ready, no pipeline)

### 1.6 Timetable — ✅ **Done (Semester 3 only)**
- Full vertical slice: PDF → layout-aware extraction (pdfplumber) → normalization → strict validation → preview JSON → idempotent Supabase import → authenticated RPC queries → REST API.
- Live data: 608 timetable entries, 15 courses, 37 faculty, 9 periods, 430 entry↔faculty links (`timetable_entry_faculty`) — all confirmed live in Supabase right now.
- RPCs: `orion_resolve_user`, `orion_student_context`, `orion_active_entries`, `orion_day_timetable`, `orion_week_timetable`, `orion_next_class` — all `security invoker`.
- API: `/api/timetable`, `/api/timetable/today`, `/api/timetable/week`, `/api/timetable/next` (`src/routes/api/timetable/$.tsx`).
- 87 passing Python tests (`tests/test_*.py`) covering extraction, normalization, validation, idempotency, service queries.
- Full write-up: `docs/timetable.md`.
- **Gap:** `src/routes/timetable.tsx` (the actual UI page) — needs verification it's wired to `timetable-api.ts` and not still mock-only (see Verification Tasks below). `student_profiles` only has 2 rows (test students) — no real student onboarding populates it yet.
- **Not done:** Semester 5 and Semester 7 timetables (PDFs present in `Data/Structured/`, never run through the pipeline — see Phase 2).

### 1.7 Faculty — 🟡 Partial
- `faculty` table live with 37 rows (name, initials, department_id, email, office_location, office_hours, research_interests, status) — populated **only as a side-effect of timetable ingestion** (faculty legend resolution), not as a standalone faculty-directory ingestion.
- `departments` table exists but **0 rows** — `faculty.department_id` FK is currently unpopulated/unlinked for the imported faculty.
- `src/routes/faculty.tsx` UI exists — needs verification against mock vs. live data (see Verification Tasks).
- **Needed:** populate `departments`; enrich faculty records with office hours/research interests from `Data/Unstructured/` curriculum PDFs or manual seed; wire faculty directory UI + faculty availability logic (AGENTS.md §18) to real schedule data via existing timetable RPCs.

### 1.8 Courses — 🟡 Partial
- `courses` table live with 15 rows, but only the fields the timetable ingestion populates (course_code, course_name, credits) — `programme`, `specialisation`, `cohort`, `semester`, `prerequisites`, `syllabus_summary` columns exist but are **not populated** (these are meant to come from the 9 curriculum PDFs in `Data/Unstructured/`, not yet ingested — see Phase 2).
- `src/routes/courses.tsx` UI exists — needs verification against mock vs. live data.

### 1.9 Announcements — ⬜ **Not started (data layer only)**
- `announcements` table exists with full lifecycle columns (category, department, batch, target_role, published_at, valid_from/valid_until, status enum draft/pending/active/expired/rejected/archived, submitted_by, approved_by) — **0 rows**, no ingestion or admin-authoring flow wired.
- `src/routes/announcements.tsx` is mock-data UI only.
- **Needed:** admin authoring UI → `announcements` table; expiry-aware query; student-facing filtered view (batch/department/role).

---

## Phase 2 — CR Upload, OCR, Admin Approval, Document Ingestion, Mess Schedules, Academic Calendar, Exams

### 2.1 CR Upload workflow — ⬜ **Not started**
- DB scaffolding exists and matches AGENTS.md §8 exactly: `documents` (with `extraction_status`, `extraction_confidence`, `sensitive_data_flag`, `submitted_by`, `status` pending→active/superseded/expired/rejected/archived), `approval_requests` (approval_status pending/approved/rejected, `rejection_reason`, `reviewed_by`), `ingestion_jobs` (job_type, status, attempts, error_message), `document_versions`, `audit_logs` — **all present, all 0 rows.**
- `src/routes/cr.tsx` (CR dashboard) is mock-data UI only; no upload form, no OCR preview screen, no submission-history screen wired to `documents`/`approval_requests`.
- **Needed:** file upload (Supabase Storage bucket not yet created — see Storage below), OCR pipeline trigger, preview UI, submit → `approval_requests` insert, CR upload-history view.

### 2.2 OCR — ⬜ **Not started**
- No OCR code in the repo (`backend/` only has `timetable/`, which uses text-layer extraction via pdfplumber, not image OCR).
- `Data/analysis.md` §4.4 identifies the OCR pilot corpus: 3 scanned anti-ragging PDFs (~57 pages) plus fallback for `august_menu.pdf` / `Wardens Team...pdf` (CID/UTF-16-encoded text layers, not scans, but need a real PDF text library rather than OCR).
- **Needed:** Tesseract/PaddleOCR integration (per README §16), confidence scoring + low-confidence flagging (AGENTS.md §10), wire into `ingestion_jobs`.

### 2.3 Admin Approval — ⬜ **Not started**
- `src/routes/admin.tsx` (admin dashboard) is mock-data UI only; no approval-queue screen wired to `approval_requests`.
- Backend logic for approve/reject (with reason, audit log write) does not exist yet — only the timetable pipeline has an analogous manual `--approved-by` CLI gate (`ingestion_runs`), not a UI-driven queue.
- **Needed:** admin approval-queue UI, approve/reject actions writing to `approval_requests` + `audit_logs`, publish step that flips `documents.status` and (for structured content) writes into the relevant table.

### 2.4 Document Ingestion (vector KB) — ⬜ **Not started**
- Target tables ready (`documents`, `document_versions`, `document_chunks` w/ pgvector + HNSW index) but **empty**.
- None of the 27 PDFs in `Data/Unstructured/` or the non-timetable `Data/Structured/` files have been ingested. `Data/analysis.md` has already scoped exactly what should happen per file (chunking strategy, cohort/programme metadata, sensitive-data screening for the anti-ragging OM).
- **Needed:** chunking + embedding pipeline, metadata enrichment (cohort/programme/department/doc_type/validity), sensitive-data redaction step, load into `document_chunks`.

### 2.5 Mess Schedules — ⬜ **Not started**
- `mess_menus` table exists (menu_date, meal, items, valid_from/until, status, source_id) — **0 rows**.
- Source file `Data/Structured/august_menu .pdf` is CID/UTF-16 encoded — naive extraction fails; needs `pdfplumber`/`PyMuPDF` (per `Data/analysis.md` §2.6) or OCR fallback.
- `src/routes/mess.tsx` is mock-data UI only.

### 2.6 Academic Calendar — ⬜ **Not started**
- `academic_calendar` table exists (event_name, event_date, event_type, applies_to_semester, valid_from/until, status) — **0 rows**.
- Source `Data/Structured/Odd 2026-27_academic_calendar.pdf` needs a month-grid-aware parser (positional layout, per `Data/analysis.md` §2.4).
- `src/routes/calendar.tsx` is mock-data UI only.

### 2.7 Exams — ⬜ **Not started**
- `exams` table exists (course_id FK, exam_type, exam_date, start/end_time, room_id FK, semester, batch, valid_from/until, status) — **0 rows**, fully joined to the already-live `courses`/`rooms` tables.
- No source exam-schedule PDF currently in `Data/` — needs a data source before ingestion can start.
- `src/routes/exams.tsx` is mock-data UI only.

### 2.8 Rooms / Classroom allocation — ⬜ **Not started (table ready)**
- `rooms` and `room_allocations` tables exist (both 0 rows) — same shape as `Data/analysis.md` §2.5 describes for `Classroom Details_ODD_Sem_July_Nov_2026.pdf`. Not yet ingested; would directly improve "where is my next class" answers once joined with timetable.

---

## Phase 3 — Clubs, Events, Faculty Recommendations, Faculty Availability, Personalization, Analytics

All ⬜ **Not started.**

- No `clubs` / `events` tables exist in the live schema at all (not even scaffolded) — `src/routes/clubs.tsx` and `src/routes/events.tsx` are pure mock-data UI.
- Faculty recommendation logic (semantic match on research interests) needs both the vector pipeline (Phase 1.3/2.4) and populated `faculty.research_interests` (currently null for all 37 rows).
- Faculty availability logic (AGENTS.md §18: current time + schedule → likely activity) is **not implemented** — would compose `orion_active_entries`/`orion_next_class` with a "where is faculty X right now" query; straightforward given the timetable RPCs already exist, but no route/function does this yet.
- Personalization beyond the already-live `orion_student_context` (semester/programme/branch/batch/section resolution used by timetable) doesn't extend to courses/announcements/clubs yet.
- Analytics (`src/routes/admin.tsx` analytics section) is mock-data only; no `analytics` tables or aggregation queries exist.
- Audit logs table (`audit_logs`) exists and is schema-ready but **nothing writes to it yet** except the timetable's separate `ingestion_runs` audit table — general-purpose audit logging (approvals, admin edits) is not wired.

---

## Phase 4 — Optimization, Notifications, Mobile Experience, Integrations

All ⬜ **Not started.**

- `src/routes/notifications.tsx` is mock-data UI only; no `notifications` table exists in the schema.
- Mobile responsiveness exists at the CSS/layout level (Tailwind responsive classes, mobile nav in `app-shell.tsx`) as part of the Phase 0 shell, but no mobile-specific feature work (push notifications, offline mode) has started.
- No third-party integrations (attendance systems, payment, etc.) — correctly out of scope per README §3 (Non-Goals) unless explicitly requested later.

---

## Cross-Cutting Gaps (apply across all phases)

| Area | Status | Notes |
|---|---|---|
| Supabase Storage buckets | ⬜ | No bucket for CR uploads / document source files created yet — needed before file upload UI can work |
| Real authentication end-to-end | ⬜ | Blocks: personalized dashboard, CR upload attribution, admin approval actor tracking, RLS actually mattering client-side |
| `departments` table population | ⬜ | 0 rows; `faculty.department_id` unlinked |
| Migration history reconciliation | 🟡 | Local `supabase/migrations/*.sql` files exist and match the live schema in substance, but `list_migrations` on the hosted project is empty — hosted schema was applied via direct SQL/Management API, not `supabase db push`, so migration tracking is out of sync |
| Security advisors (from `get_advisors`) | 🟡 | 1) `ingestion_runs` has RLS enabled but **no policies** (currently inaccessible to all non-service roles — likely intentional but should be confirmed/documented); 2) `handle_new_user()` is `SECURITY DEFINER` and publicly executable via RPC (`anon`+`authenticated`) — should be reviewed, it's meant to run only via the `auth.users` insert trigger, not be directly callable; 3) leaked-password protection is disabled in Supabase Auth settings — should be enabled |
| Performance advisors | 🟡 | `student_profiles` RLS policy re-evaluates `auth.<fn>()` per row (should wrap in `(select auth.<fn>())`); 29 unused indexes (expected — tables are still empty, will resolve once populated); `documents` table has two overlapping SELECT policies for `authenticated` role (`public_documents_select` + `submitter_view_own_documents`) — worth consolidating |
| Testing (non-timetable) | ⬜ | AGENTS.md §25 requires tests for auth, role permissions, expiry handling, announcement filtering, CR approval/rejection, OCR normalization, sensitive-data filtering, RAG retrieval filters, faculty availability — **none of these exist yet**; only the timetable slice is tested (87 tests) |
| `docs/decisions/` ADR log | ⬜ | AGENTS.md §31 asks for architecture decisions to be recorded here; directory doesn't exist yet |

---

## Supabase Schema Snapshot (live project "ORION", `dgklugpgrnxhyjkvnacp`)

Populated tables: `profiles` (2), `faculty` (37), `courses` (15), `timetable_entries` (608), `timetable_entry_faculty` (430), `timetable_periods` (9), `student_profiles` (2), `ingestion_runs` (3).

Empty (schema-ready, 0 rows): `departments`, `rooms`, `room_allocations`, `academic_calendar`, `exams`, `mess_menus`, `announcements`, `documents`, `document_versions`, `document_chunks`, `ingestion_jobs`, `approval_requests`, `audit_logs`.

Extensions installed: `pgvector` (0.8.2), `pgcrypto`, `uuid-ossp`, `pg_stat_statements`, `supabase_vault`, `plpgsql`. RLS is enabled on every table listed above.

---

## Immediate Verification Tasks (before further build-out)

These aren't new features — they're checks needed to know the true state of Phase 1 UI wiring, since this audit was done from static code + DB inspection, not a running app:

1. Confirm `src/routes/timetable.tsx`, `faculty.tsx`, `courses.tsx` actually call `src/lib/timetable-api.ts` / equivalent live queries rather than only `mock-data.ts` (the API layer exists and works per `docs/timetable.md`, but route-level wiring wasn't traced file-by-file in this audit).
2. Run `npm run dev` and click through `/dashboard`, `/timetable`, `/faculty`, `/courses` to see whether real Supabase data (15 courses, 37 faculty, 608 entries) or mock data renders.
3. Decide and document (in `docs/decisions/`) whether `ingestion_runs`' policy-less RLS is intentional (service-role-only access) before it's flagged again by advisors.
