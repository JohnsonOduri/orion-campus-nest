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

### 1.1 Authentication — ✅ **Done (Google-only, domain-restricted, role-based)** — added 2026-09-13
- Real Google OAuth sign-in (`src/routes/login.tsx`), no email/password/student-ID form anymore. Google was already enabled on the Supabase project (verified via Management API); this work wired the frontend and added the authorization rules around it.
- **Domain restriction enforced in the database** (a Postgres Before-User-Created Auth Hook, `hook_restrict_signup_by_email_domain` — migration `20260913000001_auth_signup_and_role_security.sql`): only `%@iiitkottayam.ac.in` plus one explicit test exception (`oduri.johnson@gmail.com`) can sign up; everything else gets a clean `403` from the real signup endpoint before an account is even created. Verified live with real HTTP calls (not simulated) against all three cases.
- **Role assignment**: `handle_new_user()` sets `ADMIN` for the test exception, `STUDENT` for everyone else — verified live. `ADMIN` is the one role allowed into every portal (satisfies "admin needs both admin and CR access" without a multi-role schema change).
- **A real privilege-escalation gap was found and fixed**: the pre-existing `profiles_update_own` RLS policy let any authenticated user PATCH their own `role` column with no restriction. Fixed with a `BEFORE UPDATE` trigger (`prevent_role_self_escalation`) — verified live: a student's direct attempt to set their own role to `ADMIN` now fails with `400`.
- **CR access is admin-approved, never self-service**: a student requests via `approval_requests` (`submission_type='cr_access_request'`); an admin approves/rejects via a new SECURITY DEFINER RPC, `review_cr_access_request`, which is the *only* path that flips `profiles.role` to `CR`, always writes `audit_logs`. New RLS policies (`admin_select_all_approval_requests`, `admin_update_all_approval_requests`, `profiles_select_admin_all`, `profiles_update_admin_all`) let an admin see/manage this — previously an admin couldn't even SELECT another user's profile. UI: "Request CR access" in the account menu (student), a real "CR access requests" queue in `/admin` (approve/reject buttons, `src/lib/admin-api.ts`).
- **Onboarding** (`/complete-profile`, new route): collects full name, admission year, programme/branch, semester, batch — writes to `student_profiles` (RLS previously had **no INSERT/UPDATE policy at all**, only SELECT-own; added `students_insert_own_profile`/`students_update_own_profile`) and mirrors `full_name`/`admission_year` into `profiles`. This is exactly the data `orion_student_context` reads for chat/timetable personalization (docs/query-router.md) — a signed-in user with an incomplete profile is redirected here automatically before reaching any portal.
- **Sessions**: cookie-based via `@supabase/ssr` (`src/lib/supabase-browser.ts`, `src/lib/supabase-server.ts`'s new `getSupabaseSessionClient`) — works across page loads and server functions on both mobile and desktop browsers without manual token forwarding. `src/routes/auth/callback.tsx` exchanges the OAuth code, decides the destination server-side (role + profile-completeness), and redirects in one hop.
- **Route guards**: `src/components/auth/auth-gate.tsx`, wired into `AppShell` (single integration point covers every page that uses it) — unauthenticated → `/login`; incomplete profile → `/complete-profile`; wrong role → sent to their own portal; `ADMIN` always passes. Explicitly a UX convenience, not the security boundary — every data path is independently RLS/`is_admin()`-protected regardless (verified directly, not just through the UI).
- Zustand store (`src/store/orion.ts`) no longer holds a client-chosen `role` — removed the now-dead `role`/`setRole`/`userName` fields; role comes only from the server-verified `useAuth()` hook.
- **Verified two ways**: direct HTTP calls against the real Supabase project (signup restriction, role assignment, self-escalation block, onboarding RLS, CR request/approval, audit log) **and** a real headless-Chromium browser session against the running dev server (Google redirect correctness, role-based access across `/dashboard`/`/admin`/`/cr`, onboarding redirect + real form submission). Full write-up and every verification table: `docs/auth.md`.
- **Not done**: SSR-level route guards (client-side only for now, see `docs/auth.md` §3/§7); the `FACULTY` role has no signup path or portal yet; production redirect URL not yet added to the Supabase Auth allowlist (dev-only `localhost:8080` for now).

### 1.2 Student Dashboard — 🟡 Partial
- UI complete (`src/routes/dashboard.tsx`) with today's classes, attendance charts, announcements — **all from mock data**, not live queries.
- **Needed:** wire dashboard's "today's classes" to the already-live `orion_day_timetable` RPC; announcements panel needs the `announcements` table populated + queried (table exists, 0 rows).

### 1.3 AI Chat — 🟡 **Partial (routing/retrieval/context wired to the live UI, still no LLM)** — updated 2026-09-11
- `src/components/ai/ai-chat.tsx` now calls a real backend (`askOrion` server function, `src/lib/chat-api.ts`) instead of a canned 1.1s-delay response. Still **no LLM call anywhere** — the chat renders the `GroundedContext` directly (facts, cited snippets, honest warnings), per the explicit instruction that created this layer.
- **New:** `src/lib/query/` — a TypeScript port of `backend/query/` (router/retrieval/context), since the frontend is a Node/Vite app that can't call into a Python process per-request. Verified numerically equivalent to the Python implementation (embeddings match to 6+ decimal places; identical similarity scores on the same live queries). Query-time embeddings run in Node via `@huggingface/transformers` (`Xenova/all-MiniLM-L6-v2`, server-side only, confirmed absent from the client bundle).
- **Verified in a real headless-Chromium browser session** (Playwright, `npm run dev`), not just curl/unit tests: all three required queries sent through the actual chat UI produced the correct route badge (`STRUCTURED · LIVE DB` / `SEMANTIC · DOCUMENTS` / `HYBRID · FACULTY + SCHEDULE`), the correct grounded content, and the honest office-hours warnings — zero console errors, zero failed (`>=400`) network requests.
- **Temporary auth scaffolding** (`getTestStudentClient` in `chat-api.ts`): there is still no login flow anywhere in the app (§1.1 below), so a browser request never carries a real JWT. The chat signs in as the already-provisioned test student (`scripts/create_test_students.py`) to exercise the router against real data instead of only ever demo mode — never a client-identity shortcut (the browser doesn't choose who this resolves to; RLS/`orion_resolve_user` still governs everything), but it must be replaced once real auth exists. Every such response is flagged and the UI shows an explicit "test student session" badge, matching the existing demo-mode transparency rule.
- Full write-up: `docs/query-router.md` §7.
- **Fix (2026-09-11, post-deploy user testing):** real usage surfaced that "tell me what my classes are on monday" fell through to UNSUPPORTED — the router only recognized "today"/"this week", not a named weekday. Added `DAY_OF_WEEK_TIMETABLE` intent (both `backend/query/` and `src/lib/query/`, kept in lockstep): resolves the nearest upcoming occurrence of the named weekday and calls the existing `orion_day_timetable` RPC for that date — no new RPC, no hard-coded weekday. Also verified as part of this fix: a user typing their own academic context into the message ("I am from batch 3 2024 BCS 66") has zero effect on routing or retrieval — personalization still comes only from the authenticated profile (new test: `test_client_supplied_batch_is_never_parsed_into_the_plan`). The generic UNSUPPORTED message was also made less cold (suggests the three supported question types instead of a bare "no information" reply). Re-verified live in a real browser with the user's exact reported queries — 0 console errors, 0 failed requests, correct output.
- **Needed next:** wire `backend/query/llm_client.py`/a TS equivalent into the flow for actual grounded generation with citation rendering (still deliberately not done); replace the test-student auth scaffolding with real session lookup once §1.1 (Authentication) exists; apply the authenticated student's cohort to `semanticSearch` instead of leaving it unfiltered.

### 1.4 PostgreSQL — ✅ **Done (schema layer)**
- Live Supabase Postgres 17.6 project provisioned, `pgvector` extension installed.
- Full relational schema exists for nearly every product area (see **Supabase Schema Snapshot** below) — courses, faculty, rooms, timetable, academic_calendar, exams, mess_menus, announcements, documents (+ versions/chunks), ingestion_jobs, approval_requests, audit_logs, student_profiles, profiles, ingestion_runs.
- RLS enabled on every table. `orion_resolve_user` identity pattern (never trust client-supplied user ids) implemented and used throughout the timetable RPCs.
- ⚠️ Migrations are **only tracked as raw files in `supabase/migrations/`** — `list_migrations` against the live project returns empty, meaning the migration history table itself isn't in sync/recorded on the hosted project (schema was applied via the Management API / SQL runner per `docs/timetable.md` §13, not `supabase db push`). Worth reconciling so future `supabase migration` commands don't drift.

### 1.5 Basic RAG — 🟡 **Partial** — updated 2026-09-11
- Document corpus (17 docs, 1269 chunks, see 2.4) is live and semantically searchable.
- **New:** Query Router / Retrieval / Context layer (`backend/query/`) — deterministic STRUCTURED/SEMANTIC/HYBRID/UNSUPPORTED routing (no LLM), retrieval wrapping the existing `orion_*` RPCs and the `document_chunks` pgvector corpus via a new `match_document_chunks` RPC, and a grounding-ready `GroundedContext` builder. Full write-up: `docs/query-router.md`.
- Verified end-to-end against live Supabase with a real authenticated test-student JWT (request-scoped client, RLS-enforced — never service-role): "What is my next class?" (STRUCTURED), "What are the attendance requirements?" (SEMANTIC), "Which faculty work in NLP and when can I meet them?" (HYBRID) — all three grounded in real, cited data. Run: `.venv/bin/python scripts/verify_query_router.py`.
- 17 new offline pytest tests (router classification + context has-answer invariant), part of the standard suite (104 total, was 87).
- **Not done:** no LLM/generation call anywhere in this layer by design (this slice stops at `GroundedContext`); `llm_client.py` scaffolds a cost-conscious Gemini integration (`gemini-2.0-flash-lite`, small `max_output_tokens`, refuses to call when there's nothing to ground on) but is not imported by anything yet. Cohort filtering exists in `semantic_search` but nothing calls it with a real student's cohort yet. No reranking step.

### 1.6 Timetable — ✅ **Done (Semesters 3, 5, 7)** — updated 2026-09-11
- Full vertical slice: PDF → layout-aware extraction (pdfplumber) → normalization → strict validation → preview JSON → idempotent Supabase import → authenticated RPC queries → REST API.
- Live data: **956** timetable entries (608 S3 + 170 S5 + 178 S7), **34** courses, **55** faculty, **26** periods, **614** entry↔faculty links — confirmed live in Supabase.
- Extractor/normalizer/validator hardened while processing S5/S7 (see `docs/timetable.md` §14 update and commit history):
  - header-cell text now comes from whole pdfplumber words (center-point match), not `page.crop().extract_text()` — the crop path was silently corrupting boundary text (a stray column letter bleeding into the next header cell; digits merging, e.g. "4:25" → "4:625"). Fixes apply to every source, not just S5.
  - a slot missing its printed time on one page is backfilled only from an identical time printed for the same slot elsewhere in the *same* document (never invented) — flagged `[derived]` same as an intra-page shared range.
  - `SECTION_HEADER_RE` now accepts "BATCH I" (no dash) alongside "BATCH-I" (S7's title style).
  - `CREDITS_RE` tolerates a stray space inside "[n-n- n]" (was leaking the credits string into one course's name).
  - a course named "BTP-I" in the legend classifies as `entry_type='project'` (no faculty required) instead of misclassified `'class'`.
  - a legend row with a name but no parenthesized initials now derives initials deterministically from the name (same mechanical transform `hosted_adapter.py` already used from `people.json`, now shared via `model.initials_from_name`), guarded against same-page collisions.
  - **new validator rule** `course_code_conflict`: rejects (never silently first-wins) every record whose course_code names two genuinely different courses in one source — catches real institutional data errors instead of corrupting the `courses` table on import. Punctuation/whitespace-only variants (comma differences across pages) are normalized first so this doesn't false-positive.
  - **new safety fix in `scripts/import_hosted.py`**: it previously read the preview JSON's full record list (every extracted record, valid or not) with no validation filter at all — a real gap that only stayed invisible because S3 had zero rejects. It now loads the sibling `*_validation.json` and excludes every failed `source_uid` before import.
- RPCs: `orion_resolve_user`, `orion_student_context`, `orion_active_entries`, `orion_day_timetable`, `orion_week_timetable`, `orion_next_class` — all `security invoker`.
- API: `/api/timetable`, `/api/timetable/today`, `/api/timetable/week`, `/api/timetable/next` (`src/routes/api/timetable/$.tsx`).
- 87 passing Python tests (`tests/test_*.py`); re-verified after every extractor/validator change above, plus S3's 608/608 re-extraction confirmed byte-identical to the already-live data (no regression).
- Full write-up: `docs/timetable.md`.
- **Gap:** `src/routes/timetable.tsx` (the actual UI page) — needs verification it's wired to `timetable-api.ts` and not still mock-only (see Verification Tasks below). `student_profiles` only has 2 rows (test students) — no real student onboarding populates it yet.
- **Known data-quality holdouts requiring a human/institutional decision (not imported, not guessed):**
  - **Semester 5** (15 records excluded): course code `IEG 311` legitimately names two different electives across batches in the source PDF — "DIGITAL SIGNAL PROCESSING" (Batch I) vs "QUANTUM COMPUTING for ENGINEERS" (Batch III), each with different faculty. `courses` is keyed by code alone; importing either name would silently mask the other. Needs the institution to confirm the correct distinct codes.
  - **Semester 7** (22 records excluded): on Batch III pages, the grid cells print course code "CSS 411" but that same page's own legend defines "ICS 411" for the identical subject ("Cryptography and Network Security", Dr. Goutam Mali). Needs confirmation of which code is correct before those Batch III Cryptography sessions can be imported.
  - Both are flagged by the new `course_code_conflict` / `course_resolves` validator rules and listed in the respective `*_validation.json` reports; nothing was guessed or silently repaired.

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
- DB scaffolding exists and matches AGENTS.md §8 exactly: `documents` (with `extraction_status`, `extraction_confidence`, `sensitive_data_flag`, `submitted_by`, `status` pending→active/superseded/expired/rejected/archived), `approval_requests` (approval_status pending/approved/rejected, `rejection_reason`, `reviewed_by`), `ingestion_jobs` (job_type, status, attempts, error_message), `document_versions`, `audit_logs` — **all present**; `documents`/`document_versions` are now populated (§2.4) but only via trusted server-side scripts, never through this (still nonexistent) CR upload path. `approval_requests`/`ingestion_jobs`/`audit_logs` remain 0 rows.
- `src/routes/cr.tsx` (CR dashboard) is mock-data UI only; no upload form, no OCR preview screen, no submission-history screen wired to `documents`/`approval_requests`.
- **Needed:** file upload (Supabase Storage bucket not yet created — see Storage below), OCR pipeline trigger, preview UI, submit → `approval_requests` insert, CR upload-history view.

### 2.2 OCR — 🟡 **Partial (tooling proven, not wired into a CR pipeline)** — updated 2026-09-11
- `tesseract` (via `pytesseract`) is installed locally and used in `scripts/ingest_documents.py` for the 3 scanned anti-ragging PDFs — confidence-scored per chunk, low-confidence content (<60%) excluded rather than stored as noise (see §2.4). This proves the OCR path end-to-end but only as a one-off trusted-admin script, not a CR-facing pipeline.
- **Needed:** wire into `ingestion_jobs` (status tracking, retries), a CR-facing upload → OCR → preview flow, and a Hindi (`hin.traineddata`) or other non-English language pack if that corpus gap (§2.4) needs closing.

### 2.3 Admin Approval — ⬜ **Not started**
- `src/routes/admin.tsx` (admin dashboard) is mock-data UI only; no approval-queue screen wired to `approval_requests`.
- Backend logic for approve/reject (with reason, audit log write) does not exist yet — only the timetable pipeline has an analogous manual `--approved-by` CLI gate (`ingestion_runs`), not a UI-driven queue.
- **Needed:** admin approval-queue UI, approve/reject actions writing to `approval_requests` + `audit_logs`, publish step that flips `documents.status` and (for structured content) writes into the relevant table.

### 2.4 Document Ingestion (vector KB) — ✅ **Done (initial corpus)** — updated 2026-09-11
- New pipeline `scripts/ingest_documents.py`: extract (text layer or OCR) → sensitive-data screen → chunk → embed → Supabase, following README §6/AGENTS.md §9.
- **Embeddings:** no embedding-capable API key was configured anywhere in `.env` (only Supabase + Google OAuth keys) — rather than block or fabricate, switched to a local, free model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim). `document_chunks.embedding` was originally a fixed `vector(1536)` (OpenAI's dimension); resized via migration `20260911010000_document_chunks_embedding_384_local_model.sql` (table was empty, so a safe in-place type change, not a data migration). Verified with a live cosine-similarity query — top hit for "What is the attendance requirement?" was exactly `R.6.0 Attendance, Condonation and Course Feedback` at 66.5% similarity.
- **OCR:** used for the 3 scanned anti-ragging PDFs (no text layer). Only the `eng` tessdata is installed — the bilingual `UGC Regulations- Anti-Ragging - 2009.pdf` has Hindi-language pages that OCR as gibberish through the English model (verified: Hindi pages score 34-43% confidence vs 82-93% for English pages on the same document). Per-chunk OCR confidence is stored in `confidence_score`; anything below 60% is **excluded from the corpus entirely** rather than stored as noise — pages 3-29 of that document were dropped this way. **Known gap:** that document's Hindi content is not searchable; a real answer needs the source PDF directly. No `hin.traineddata` is installed and none was added (would need a `brew`/manual install decision).
- **Sensitive data:** the committee-roster OM (`OM-Anti Ragging Committee-Squad-Jan2024.pdf`) is flagged `sensitive_data_flag=true` and passed through phone-number redaction (regex on 10-digit Indian mobile numbers) before storage; that particular document had no matching numbers in its OCR'd text, so redaction was a verified no-op, not a false negative. Names/designations of committee members are kept (public governance-role info, not personal data, per AGENTS.md §11's minimum-data principle).
- **Cohort-aware metadata:** every chunk carries `document_type, category, programme, specialisation, cohort, department, classification, valid_from, valid_until` in `metadata` JSONB. Verified live: the 9 curriculum PDFs split cleanly into `cohort='ADM2026'` (5 programmes, 798 chunks) vs `cohort='21-25'` (4 programmes, 376 chunks) — a 2026-cohort student's query and a 21-25 cohort's query hit disjoint chunk sets, per CLAUDE.md §20's cohort-isolation rule.
- **Live: 17 documents, 17 versions, 1269 chunks.** Idempotent (upsert on `(document_id, version_id, chunk_index)`), audited via `ingestion_runs`.
- **Deliberately excluded:** `recruiterscorner.pdf` (14MB placement/marketing deck) — `Data/analysis.md` flagged it as needing a product-owner decision; applied README §12's default ("pure advertisements should not enter the searchable institutional knowledge base") rather than decide unilaterally. Not ingested; can be added later with an explicit decision.
- **Corpus indexed:** 9 curriculum/syllabi (CSE/AI&DS/ECE/BMC/Cyber, both ADM2026 and 21-25 cohorts where applicable), 2 UG Regulations books (26-onwards and 21-25), 2 procedures (transcript verification, educational verification), 3 anti-ragging documents (2009 UGC regs [English portion only], the circular letter, the Jan-2024 committee OM), and Hostel Rules and Regulations (July 2026) — the latter pulled from `Data/Structured/` since it's prose, not a table, despite living in that folder.
- The retrieval/grounding layer now exists and is tested (`backend/query/`, `src/lib/query/`, §1.5) — semantic retrieval wraps this corpus via `match_document_chunks`. Reranking and citation-rendered generation are still not built.

### 2.5 Mess Schedules — ✅ **Done (August 2026 only)** — updated 2026-09-11
- `Data/Structured/august_menu .pdf` ingested via new `scripts/ingest_mess_menu.py` (text layer extracted cleanly with pdfplumber — the CID/UTF-16 concern originally flagged for this file in `Data/analysis.md` did not materialize). Source table is one row per weekday (a recurring weekly pattern); materialized onto every actual calendar date in August 2026 by weekday match (mechanical `calendar` arithmetic, not a guess) since `mess_menus.menu_date` has no day-of-week/recurrence column. Live: **124 rows** (31 days × 4 meals: breakfast/lunch/snacks/dinner). Idempotent, audited.
- Only August 2026 exists; no other month's menu PDF is in `Data/Structured/`. `src/routes/mess.tsx` still needs wiring to live data (still mock-data UI).

### 2.6 Academic Calendar — ✅ **Done** — updated 2026-09-11
- `Data/Structured/Odd 2026-27_academic_calendar.pdf` ingested via new `scripts/ingest_academic_calendar.py`. The page's single pdfplumber table has two parts: a Jul–Dec month grid (merged cells, ambiguous multi-event cells — deliberately not parsed) and a clean "Sl No | Academic Highlights | Dates" summary with exact DD-MM-YYYY dates already printed — used as the sole source of truth. Live: **30 events** (2026-07-10 through 2027-01-04), `event_type` assigned by mechanical keyword match on the printed name (exam/registration/meeting/deadline/etc., nullable — never invented), `applies_to_semester` left `NULL` since the calendar's own title covers three semesters at once ("Sem III,V,VII") and the column can only hold one. Idempotent, audited.
- `src/routes/calendar.tsx` still needs wiring to live data (still mock-data UI).

### 2.7 Exams — ⬜ **Not started**
- `exams` table exists (course_id FK, exam_type, exam_date, start/end_time, room_id FK, semester, batch, valid_from/until, status) — **0 rows**, fully joined to the already-live `courses`/`rooms` tables.
- No source exam-schedule PDF currently in `Data/` — needs a data source before ingestion can start.
- `src/routes/exams.tsx` is mock-data UI only.

### 2.8 Rooms / Classroom allocation — ✅ **Done** — updated 2026-09-11
- `Data/Structured/Classroom Details_ODD_Sem _July_Nov_2026.pdf` ingested via new `scripts/ingest_classroom_details.py` (single clean pdfplumber table, no naive text dump). Live: **30 rooms** (`room_type` = `large_classroom`/`small_classroom`/`lab`, no capacity printed in source so left `NULL`), **26 room_allocations** (large classrooms keyed by numeric `batch` "1".."5" exactly as printed — *not* converted to the timetable's Roman-numeral batch notation, since the two documents were never shown to use the same scheme; small classrooms keyed by `department` instead, no batch given for those rows). Idempotent (fetch→diff on natural keys), audited via `ingestion_runs`.
- One PDF annotation ("BC 302 (Temporary)") was stripped from the room identity rather than treated as a second physical room — `room_no` is unique and the schema has no field to carry a "temporary" note; flagged as a preview warning instead of silently dropped.
- Not yet wired into "where is my next class" — `timetable_entries.room_id` is still `NULL` for all 988 entries (the timetable PDFs print no room per class period; only this separate classroom-details document has room data, at batch/department granularity, not per class).

### 2.9 Hostel Wardens — ✅ **Done** — added 2026-09-11
- New table `public.hostel_wardens` (migration `20260911000001_add_hostel_wardens.sql`) — not in the original schema; added specifically for this PDF on request, since README §3 lists hostel administration as out of scope "unless explicitly added." One row per (person, hall) pair (a warden team commonly covers 2-4 halls).
- `Data/Structured/Wardens Team July 2026 - Students Copy.pdf` ingested via new `scripts/ingest_hostel_wardens.py`. Live: **78 rows** across all 16 halls (hostel_warden/standby_warden/assistant_warden per hall, plus chief_warden/associate_dean/hostel_manager/security_officer with no hall). The page's "Important E-Mail address" block (IT Support / Outpass — bare addresses, no named person) is explicitly skipped rather than fabricated into a person row. Idempotent, audited.
- Not yet exposed anywhere in the UI or the query router — no "who is the warden for hall X" intent exists yet.

### 2.10 Data quality pass on already-live tables — done 2026-09-11
Triggered by "test supabase and refine the data" — found and fixed real defects, not just added new data:
- **Semester 5's Cyber Security batch was silently dropped on the first import.** Its title prints "...BATCH [Adm-2024]" with no trailing batch letter (only one batch exists for that branch), which didn't match `SECTION_HEADER_RE`. Fixed (`model.py`): a bare "BATCH" now defaults `batch="1"` — not a guess, since there's only one batch to label. Recovered 32 real entries (Sem 5: 170 → 202 imported).
- The `page.crop().extract_text()` boundary-corruption bug fixed earlier for header cells was also present in day-grid **body** cells (`_extract_cells`) — caused a genuine "Coding Club Activities" cell to read as "Coding Club **B** Activities" on one row (bled a stray break-column letter), which in turn made two real activity records look like an overlap conflict and get wrongly rejected. Fixed by switching `_extract_cells` to the same word-based extraction as the header path.
- Enriched **28 of 55** faculty rows with email/office_location/research_interests from `Data/processed/people.json`, matched by deterministic initials (`model.initials_from_name`) with an unambiguity check (initials colliding between two different people.json entries → neither used) plus a name-token overlap sanity check — which correctly caught and rejected 2 false initials matches ("Dr. Alkha Mohan" ≠ "Dr. Avinash Kumar Mittal"; "Dr. P. Victer Paul" ≠ "Dr. Vineeth Palliyembil"). New script: `scripts/enrich_faculty.py`.
- Normalized `room_allocations.department`: "AI & DS" / "AI&DS" (pure whitespace variance, same source PDF, different pages) → "AI&DS" everywhere; fixed at the source in `ingest_classroom_details.py` so a future re-run doesn't revert it.
- **Left alone, flagged for the user, not merged:** `timetable_entries.department` has three different spellings across the three semester PDFs for what may be the same programme — "CSE WITH SPECIALISATION IN AI AND DATA SCIENCE" (Sem3, British spelling), "CSE WITH SPECIALIZATION IN AI & DATA SCIENCE" (Sem7, American + "&"), and a bare "AI AND DATA SCIENCE" (Sem5, no "CSE WITH..." prefix at all). Could not verify from the PDFs alone whether these are the same academic track or genuinely distinct; user chose to leave as-is rather than risk a wrong merge.
- Reviewed the other 4 PDFs in `Data/Structured/` not covered by SQL tables: NIRF engineering/overall reports (government ranking compliance data, outside ORION's declared scope) and Hostel Rules and Regulations (prose policy document — belongs in the future RAG/document pipeline, not a SQL table, per README §7/§9).

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
| Real authentication end-to-end | ✅ | Done 2026-09-13 — Google-only, domain-restricted, role-based, verified live (§1.1, `docs/auth.md`). RLS now actually matters client-side (verified: self-role-escalation blocked, admin-only policies enforced). CR upload attribution / admin approval actor tracking still blocked on §2.1/§2.3 (CR upload workflow, admin approval UI) themselves being unbuilt — auth is no longer what's blocking them. |
| `departments` table population | ⬜ | 0 rows; `faculty.department_id` unlinked |
| Migration history reconciliation | 🟡 | Local `supabase/migrations/*.sql` files exist and match the live schema in substance, but `list_migrations` on the hosted project is empty — hosted schema was applied via direct SQL/Management API, not `supabase db push`, so migration tracking is out of sync |
| Security advisors (from `get_advisors`) | 🟡 | 1) `ingestion_runs` has RLS enabled but **no policies** (currently inaccessible to all non-service roles — likely intentional but should be confirmed/documented); 2) `handle_new_user()` is `SECURITY DEFINER` and publicly executable via RPC (`anon`+`authenticated`) — should be reviewed, it's meant to run only via the `auth.users` insert trigger, not be directly callable; 3) leaked-password protection is disabled in Supabase Auth settings — should be enabled |
| Performance advisors | 🟡 | `student_profiles` RLS policy re-evaluates `auth.<fn>()` per row (should wrap in `(select auth.<fn>())`); 29 unused indexes (expected — tables are still empty, will resolve once populated); `documents` table has two overlapping SELECT policies for `authenticated` role (`public_documents_select` + `submitter_view_own_documents`) — worth consolidating |
| Testing (non-timetable) | 🟡 | AGENTS.md §25 requires tests for auth, role permissions, expiry handling, announcement filtering, CR approval/rejection, OCR normalization, sensitive-data filtering, RAG retrieval filters, faculty availability. Query-router tests now exist (17, offline — routing rules + grounding invariant); still missing: auth/role/expiry/announcement/CR/OCR-normalization/sensitive-data tests. 107 Python tests total. |
| `docs/decisions/` ADR log | ⬜ | AGENTS.md §31 asks for architecture decisions to be recorded here; directory doesn't exist yet |

---

## Supabase Schema Snapshot (live project "ORION", `dgklugpgrnxhyjkvnacp`) — updated 2026-09-11

Populated tables: `profiles` (2), `faculty` (61, 28 with email/office/research from `people.json`), `courses` (41), `timetable_entries` (988), `timetable_entry_faculty` (~640), `timetable_periods` (26), `student_profiles` (2), `ingestion_runs` (20), `rooms` (30), `room_allocations` (26), `academic_calendar` (30), `mess_menus` (124), `hostel_wardens` (78, new table — migration `20260911000001_add_hostel_wardens.sql`), `documents` (17), `document_versions` (17), `document_chunks` (1269, embedding dim resized 1536→384 — migration `20260911010000_document_chunks_embedding_384_local_model.sql`).

Empty (schema-ready, 0 rows): `departments`, `exams`, `announcements`, `ingestion_jobs`, `approval_requests`, `audit_logs`.

Extensions installed: `pgvector` (0.8.2), `pgcrypto`, `uuid-ossp`, `pg_stat_statements`, `supabase_vault`, `plpgsql`. RLS is enabled on every table listed above.

---

## Immediate Verification Tasks (before further build-out)

These aren't new features — they're checks needed to know the true state of Phase 1 UI wiring, since most of this audit was done from static code + DB inspection, not a running app (the AI chat panel is now the exception — verified live, §1.3):

1. Confirm `src/routes/timetable.tsx`, `faculty.tsx`, `courses.tsx` actually call `src/lib/timetable-api.ts` / equivalent live queries rather than only `mock-data.ts` (the API layer exists and works per `docs/timetable.md`, but route-level wiring wasn't traced file-by-file in this audit) — same gap as before, still unverified. `mess.tsx` and `calendar.tsx` now have live data to wire to as well (§2.5, §2.6).
2. Run `npm run dev` and click through `/dashboard`, `/timetable`, `/faculty`, `/courses` to see whether real Supabase data (41 courses, 61 faculty, 988 entries) or mock data renders.
3. Decide and document (in `docs/decisions/`) whether `ingestion_runs`' policy-less RLS is intentional (service-role-only access) before it's flagged again by advisors.

---

## What Should Be Implemented Next (prioritized, as of 2026-09-13)

Ordered by what unblocks the most other work, not by original CLAUDE.md §36 sequence (structured data + RAG corpus + query router + real authentication are now done, changing what's next).

### 1. Wire the query router's chat to the now-real session (quick, unblocks everything else here)
- `src/lib/chat-api.ts`'s `getTestStudentClient()` scaffolding (clearly flagged `usedTestStudent`/"test student session" badge) should now read the real cookie session via `getSupabaseSessionClient` (docs/auth.md §2) instead of always signing in as the test student — real auth exists now, this was the one thing blocking it.
- Once that's done, pass the authenticated student's real `student_profiles` context (cohort, department, semester) into `semanticSearch`/hybrid retrieval instead of the hardcoded test account's.

### 2. Grounded generation (the LLM step deliberately not built yet)
- Wire `backend/query/llm_client.py` (Python reference) / a TS equivalent into the query flow. The scaffolding already exists: cheapest-tier Gemini model, small token cap, refuses to call when `has_answer` is False.
- Render citations properly in the generated answer (not just as a bullet-pointed fact list, which is what the chat shows today).
- Add a grounding-validation step (does the generated text actually stay within the retrieved facts/snippets?) before returning it.

### 3. CR upload → OCR → admin approval workflow (Phase 2, entirely unbuilt)
- File upload UI + Supabase Storage bucket (doesn't exist yet).
- OCR pipeline trigger reusing the now-proven `tesseract`/`pytesseract` path from `scripts/ingest_documents.py`, wired into `ingestion_jobs` instead of being a one-off admin script.
- Admin approval-queue UI writing to `approval_requests` + `audit_logs`.
- This is the only way non-engineers (CRs/admins) can add data going forward — everything live today was loaded by an engineer running a script.

### 4. Remaining structured-data gaps
- Two blocked timetable conflicts still need institutional confirmation before ~25 more Semester 5/7 records can import: the `IEG 311` code naming two different electives, and the `CSS 411`/`ICS 411` mismatch on Semester 7 Batch III (docs/timetable.md-adjacent, see §1.6 above).
- `exams` — no source PDF exists at all; needs a data source before any ingestion can start.
- `departments` table (0 rows) — deferred because populating it means resolving the same ambiguity as the `timetable_entries.department` spelling variants (§2.10) that the user chose to leave alone; revisit together.
- Room/timetable join — `timetable_entries.room_id` is `NULL` for all 988 entries (source PDFs print no room per class period); would need either a new room-per-class data source or accepting batch/department-level room info as a lower-precision answer.

### 5. Remaining document-ingestion gaps
- `recruiterscorner.pdf` — needs an explicit product-owner decision (marketing content), not a default.
- Hindi-language pages of the 2009 UGC anti-ragging regulations are unsearchable (only `eng` tessdata installed) — install `hin.traineddata` and re-run `scripts/ingest_documents.py --only "UGC Regulations"` if that content matters.
- Reranking step (README §9) doesn't exist — single-pass cosine similarity only.

### 6. Testing and process debt
- No tests yet for auth, role permissions, expiry handling, announcement filtering, CR approval/rejection, OCR normalization, sensitive-data filtering, faculty availability (AGENTS.md §25) — most of these can't be written meaningfully until the features they cover exist (items 1 and 4 above).
- `docs/decisions/` ADR log doesn't exist — AGENTS.md §31 asks for architecture decisions to be recorded there (e.g. the local-embeddings-instead-of-API decision, the test-student auth scaffolding decision, both made this session without a formal ADR).
- Security/performance advisor items in the Cross-Cutting Gaps table above are still open (`ingestion_runs` policy-less RLS, `handle_new_user()` SECURITY DEFINER reachability, leaked-password protection, `student_profiles` RLS per-row re-evaluation, overlapping `documents` SELECT policies).
