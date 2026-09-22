# ORION — Phase & Task Breakdown (Done vs. Not Done)

> Cross-referenced against `AGENTS.md` §21, `README.md`, `Data/analysis.md` /
> `Data/Contents.md`, the merged working tree (commit `146bb9a`), and the live
> Supabase project **"ORION"** (`dgklugpgrnxhyjkvnacp`, ap-south-1).
> Status markers: ✅ done · 🟡 partial · ⬜ not started · 🔴 broken/blocking.
> When a task moves state, add a dated entry to `Work-done.md` **and** flip the
> marker here — the two files must stay in sync.
>
> **Last full re-audit: 2026-09-21**, immediately after merging `origin/main`
> (5 commits: FastAPI backend, real Gemini generation, faculty directory
> rebuild, IST timezone fix, login/register). Every row count below came from a
> direct SQL query that day; every "mock vs live" claim came from reading the
> route file.
>
> Backend runtime requirements and hosting analysis:
> [`docs/backend-requirements.md`](docs/backend-requirements.md).

---

## Architecture as of this audit

The project changed shape on 2026-09-21. It is no longer a frontend talking to
Supabase directly:

```
browser ──httpOnly cookie──> TanStack Start SSR ──fetch──> FastAPI (backend/)
                                                              │ caller's JWT
                                                              ▼
                                                     Supabase (Postgres + RLS)
scripts/*.py (service-role) ─────────────────────────────────────▶ Supabase
```

- **`backend/` is now a real FastAPI service** (`uvicorn main:app`): routers for
  `auth`, `oauth`, `registration`, `cr`, `admin`, `timetable`, `faculty`,
  `mess`, `announcements`, `ai`.
- **The TypeScript query layer is gone.** `src/lib/query/`, `chat-api.ts`,
  `timetable-api.ts` and `supabase-server.ts` were deleted; `backend/query/`
  (Python) is now the single implementation, called over HTTP.
- **Sessions are httpOnly cookies set by FastAPI**, not Supabase tokens in the
  browser.
- The frontend-direct-Supabase auth stack from the old local branch was removed
  during the merge; it is preserved on `backup/frontend-auth-9b8c915`.

---

## Phase 0 — Frontend Prototype Shell

| Task | Status | Notes |
|---|---|---|
| React 19 + TypeScript + TanStack Start/Router scaffold | ✅ | Vite 8, file-based routing (`src/routes/`) |
| Design system (Tailwind v4 + shadcn/ui + Radix + lucide) | ✅ | `src/components/ui/` |
| App shell (sidebar/topbar/mobile nav/theme toggle) | ✅ | `src/components/layout/app-shell.tsx` — role-aware from the real profile (`src/hooks/use-profile.ts`) |
| Zustand store | ✅ | `src/store/orion.ts` — no longer holds a client-chosen role |
| All required UI screens click-through | ✅ | every route file exists |
| Pixel-art decoration system | ✅ | `src/components/pixel/pixel-art.tsx` |
| Mock dataset backing the unwired screens | 🟡 | `src/lib/mock-data.ts` — still the source for 7 whole routes (table below) |
| Floating AI chat panel | ✅ | `src/components/ai/ai-chat.tsx` → `POST /ai/ask`, real grounded answers |

---

## UI wiring — what actually renders live data (verified 2026-09-21)

| Route | Data source |
|---|---|
| `/login`, `/register` | ✅ live (`api-client` → FastAPI auth) |
| `/timetable` | ✅ live (`/timetable/day`, `/week`, `/next`) |
| `/faculty` | ✅ live (`/faculty`, 185 rows, category-aware) |
| `/mess` | ✅ live (`/mess/today`, `/week`) |
| `/announcements` | ✅ live (`/announcements`) |
| `/cr` | ✅ live (`/cr/*`) |
| `/admin` | 🟡 live for CR requests + announcement review; the rest mock |
| `/dashboard` | 🟡 live timetable + profile; announcements/attendance mock |
| `/search` | 🟡 live faculty + announcements; courses/documents/events mock |
| `/ai` | 🟡 chat panel live; the page's conversation list is mock |
| `/calendar`, `/clubs`, `/courses`, `/documents`, `/exams`, `/profile`, `/notifications` | ⬜ mock only |

This is the biggest change since the last audit: timetable, faculty and mess
data that had existed in the database for days is finally on screen.

---

## Phase 1 — Auth, Dashboard, AI Chat, PostgreSQL, RAG, Timetable, Faculty, Courses, Announcements

### 1.1 Authentication — ✅ **Done (FastAPI + Supabase GoTrue)**
- **Google is the only sign-in method** (`/auth/signup`/`/auth/login`
  password endpoints removed 2026-09-22): the browser drives the OAuth/PKCE
  handshake itself (`src/lib/supabase-browser.ts`), then POSTs the resulting
  tokens once to `/auth/oauth/google/set-session` — chosen over a fully
  backend-driven flow because that required the FastAPI service to be
  running just to start the Google redirect.
- **Sessions are httpOnly cookies** set by the API (`orion_access_token`,
  `orion_refresh_token`, `SameSite=Lax`, `Secure` via `COOKIE_SECURE`).
  Google sign-in's tokens do pass through `sessionStorage` briefly during
  the handshake (unavoidable for a redirect-based OAuth flow) before being
  actively wiped once the cookie handoff completes — see CLAUDE.md §13.
- Database-side rules (captured in
  `20260913000001_capture_live_auth_drift.sql`): domain-restricted signup hook,
  `handle_new_user()` role assignment, `prevent_role_self_escalation` trigger,
  `is_admin()`, and 8 RLS policies. `docs/auth.md` still describes these rules
  accurately; its *frontend* sections describe the removed architecture.
- Registration completes through `complete_registration` (`POST /auth/register`),
  writing `student_profiles` — the context every timetable RPC reads.
- Role checks happen twice by design: a fast 401/403 in
  `backend/app/api/deps.py`, with RLS/`is_admin()` as the real boundary beneath.
- **Not done:** `FACULTY` has no signup path or portal; only `localhost` is in
  the Supabase redirect allowlist.

### 1.2 Student Dashboard — 🟡 Partial
- Live: today's classes (`/timetable/day`) and the real profile.
- Still mock: announcements panel and attendance charts (no attendance data
  source exists, and attendance is out of scope per README §3).

### 1.3 AI Chat — ✅ **Done (real grounded generation)**
- `POST /ai/ask`: route → retrieve → build `GroundedContext` → **Gemini
  `gemini-3.5-flash-lite`** (256 output tokens) → answer, returned with the
  facts and cited snippets that produced it.
- Routes: STRUCTURED / SEMANTIC / HYBRID / SMALL_TALK / UNSUPPORTED, with
  structured intents for next class, day/week timetable, named weekday,
  class-at-time, faculty-for-course, course info, faculty lookup, mess today.
- Cost discipline: no LLM call when `has_answer` is false, none for small talk,
  no retry loop. If Gemini is unconfigured or failing the endpoint degrades to
  retrieval-only (`generation_available: false`) instead of erroring.
- The old hardcoded test-student fallback is **gone** — identity comes from the
  same cookie-derived request-scoped client as every other router.
- **Not done:** no streaming; no reranking; no post-generation grounding check
  (the prompt constrains the model, nothing verifies the output).

### 1.4 PostgreSQL — ✅ **Done (schema layer)**
- Postgres 17 + pgvector, RLS on every table, `orion_resolve_user` identity
  pattern throughout.
- **Migration history is now captured in-repo** (20 files), including functions
  that previously existed only on the hosted project. Hosted
  `list_migrations` is still empty (schema applied via direct SQL), so
  `supabase db push` still needs reconciling before it can be trusted.

### 1.5 RAG — 🟡 **Partial**
- 17 documents / 17 versions / **1,269 chunks**, 384-dim local MiniLM
  embeddings, retrieved through `match_document_chunks` with cohort / category /
  document-type / validity filters.
- Generation is now wired (§1.3), so retrieve → ground → answer is complete
  end-to-end for the first time.
- **Not done:** reranking; the authenticated student's cohort is not passed into
  semantic retrieval consistently; no grounding validation.
- **Performance defect:** `faculty_research_search` re-embeds every faculty
  research-interest string on **every request** instead of storing vectors
  (`backend/query/retrieval.py`).

### 1.6 Timetable — ✅ **Done (Semesters 3, 5, 7)**
- PDF → layout-aware extraction → normalization → strict validation → preview
  JSON → idempotent import → RPCs → FastAPI → UI. Live: **1,263 entries**
  (608 S3 + 477 S5 + 178 S7), 26 periods, 43 courses, **838** entry↔faculty links.
- Semester 5 grew 202 → 477 in the 2026-09-19 re-import; the `IEG 311` and
  `CSS 411` code conflicts that previously blocked ~37 records now resolve to
  single rows (`IEG 311` = Digital Signal Processing, `CSS 411` = Cryptography
  and Network Security).
- **IST timezone fix** (`20260921000004_timetable_ist_timezone_fix.sql`) — day
  and next-class behaviour pinned to IST, with the chat's ongoing/next-class
  phrasing corrected alongside it.
- **Gap:** `room_id` is NULL for all 1,263 entries — the PDFs print no room per
  class period, so "where is my next class" still cannot be answered precisely.

### 1.7 Faculty — ✅ **Done (directory)** / 🟡 (research enrichment)
- Rebuilt 2026-09-21 from the official institute directory CSVs via
  `scripts/rebuild_faculty.py`: **185 rows**, 125 with email, new
  `phone` / `designation` / `profile_url` columns and a **`category` text[]**
  (a person can be both HOD and teaching faculty): 176 faculty, 17
  administrative, 7 professional support, 5 HOD.
- `/faculty` renders it live and category-aware.
- **Still missing:** `departments` is 0 rows so `faculty.department_id` is
  unlinked; `research_interests` is populated for only a minority of rows,
  which caps faculty recommendation quality.

### 1.8 Courses — 🟡 Partial
- 43 rows, but only the fields timetable ingestion fills (code, name, credits).
  `programme`, `specialisation`, `cohort`, `semester`, `prerequisites`,
  `syllabus_summary` are empty — they belong to the 9 curriculum PDFs, which
  are in the RAG corpus but never parsed into structured rows.
- `/courses` is still mock-only.

### 1.9 Announcements — ✅ **Done (workflow)** / 🟡 (content)
- Full CR → admin path is live and has been exercised: `submit_announcement`,
  `review_announcement`, `POST /cr/announcements`, `GET /admin/announcements`,
  `POST /admin/announcements/{id}/review`, an RLS insert policy, and an
  `announcement_rejected` row in `audit_logs` from a real 2026-09-19 rejection.
- `/announcements` renders live data.
- Only **1 row** exists (the rejected test announcement) — no real content yet.

---

## Phase 2 — CR Upload, OCR, Admin Approval, Documents, Mess, Calendar, Exams

### 2.1 CR Upload workflow — 🟡 **Partial**
- ✅ CR access requests and CR announcement submission, end-to-end.
- ⬜ **Document/file upload does not exist**: no Supabase Storage bucket, no
  upload form, no OCR preview screen, `ingestion_jobs` is 0 rows.
- This is what keeps ORION engineer-operated: everything in the database was
  loaded by someone running a script.

### 2.2 OCR — 🟡 **Partial (proven, not wired)**
- `tesseract`/`pytesseract` works and is used by `scripts/ingest_documents.py`
  (per-chunk confidence; <60% excluded rather than stored as noise).
- Not wired into `ingestion_jobs`, retries, or any CR-facing flow. Only `eng`
  tessdata is installed.

### 2.3 Admin Approval — 🟡 **Partial**
- ✅ CR access review and announcement review, both writing `audit_logs`
  (3 rows: 2 CR approvals, 1 announcement rejection).
- ⬜ No document/ingestion approval queue — §2.1 produces nothing to review.

### 2.4 Document Ingestion (vector KB) — ✅ **Done (initial corpus)**
- 17 documents / 17 versions / 1,269 chunks; cohort-aware metadata
  (`ADM2026` 798 chunks vs `21-25` 376 — disjoint, per CLAUDE.md §20).
- Sensitive-data screening and phone-number redaction applied; the committee
  roster is flagged `sensitive_data_flag=true`.
- **Known gaps:** Hindi pages of the 2009 UGC anti-ragging regulations are
  unsearchable (no `hin.traineddata`); `recruiterscorner.pdf` deliberately
  excluded pending a product-owner decision.

### 2.5 Mess Schedules — ✅ **Done (August 2026 only)** — now on screen
- 124 rows (31 days × 4 meals), served by `/mess/today` and `/mess/week`, with a
  dedicated RLS select policy (`20260919000001_mess_menus_select_policy.sql`).
- **Only August 2026 exists** — that month has passed, so the live menu is
  effectively stale; no other month's PDF is in `Data/Structured/`.

### 2.6 Academic Calendar — ✅ **Done (data)** / ⬜ (UI)
- 30 events (2026-07-10 → 2027-01-04). `/calendar` is still mock-only and there
  is no calendar endpoint on the API.

### 2.7 Exams — ⬜ **Not started**
- `exams` exists, **0 rows**; no source document in `Data/`. `/exams` is
  mock-only. Blocked on data, not on code.

### 2.8 Rooms / Classroom allocation — ✅ **Done (data)** / ⬜ (use)
- 30 rooms, 26 allocations. Not joined to the timetable (§1.6), not exposed in
  the UI or the query router.

### 2.9 Hostel Wardens — ✅ **Done (data)** / ⬜ (use)
- 78 rows across 16 halls. No endpoint, no UI, no router intent.

### 2.10 Data quality — ✅ ongoing
- Earlier passes fixed real defects (the silently dropped Cyber Security batch,
  the `page.crop()` text-corruption bug in header *and* body cells, faculty
  enrichment false matches, room department normalization).
- **Still open:** `timetable_entries.department` holds three spellings of what
  may be one programme ("CSE WITH SPECIALISATION IN AI AND DATA SCIENCE" /
  "CSE WITH SPECIALIZATION IN AI & DATA SCIENCE" / "AI AND DATA SCIENCE") —
  deliberately not merged without institutional confirmation.
- **New:** the `IEG 311` / `CSS 411` resolutions (§1.6) are in the data but the
  reasoning is recorded nowhere. Write it down — the `course_code_conflict`
  validator exists precisely to stop unrecorded choices like this.

---

## Phase 3 — Clubs, Events, Faculty Recommendations, Availability, Personalization, Analytics

Mostly ⬜ **Not started.**

- No `clubs` / `events` tables exist; `/clubs` is mock-only.
- Faculty recommendation: retrieval code exists (`faculty_research_search`,
  HYBRID route) but is capped by sparse `research_interests`.
- Faculty availability is **teaching-schedule-derived only** and labelled as
  such — never presented as confirmed office hours. That restraint is correct
  (AGENTS.md §18); do not "improve" it away.
- Analytics: no tables, no aggregation; the admin analytics panel is mock.

---

## Phase 4 — Optimization, Notifications, Mobile, Integrations

All ⬜ **Not started.** No `notifications` table; `/notifications` is mock.
Mobile responsiveness exists at the CSS level only. No third-party integrations
(correctly out of scope).

---

## Cross-Cutting Gaps

| Area | Status | Notes |
|---|---|---|
| **Deployment** | 🔴 | Nothing is deployed; the app runs on localhost only and the cookie/CORS/OAuth configuration is localhost-specific. Requirements and options: [`docs/backend-requirements.md`](docs/backend-requirements.md). **The `SameSite=Lax` session cookie means frontend and API must share one registrable domain** — decide that before provisioning anything. |
| Supabase Storage buckets | ⬜ | None created; blocks §2.1 |
| `departments` table | ⬜ | 0 rows; `faculty.department_id` unlinked; blocked on the same spelling ambiguity as §2.10 |
| Migration history reconciliation | 🟡 | 20 migration files now capture the live schema (big improvement), but hosted `list_migrations` is still empty |
| Secrets management | 🟡 | One repo-root `.env` feeds both the Python and JS sides; deployment needs per-environment variables |
| Security advisors | 🟡 | `ingestion_runs` has RLS with no policies (probably intentional, undocumented); `handle_new_user()` is `SECURITY DEFINER` and directly callable by `anon`/`authenticated`; leaked-password protection disabled |
| Performance advisors | 🟡 | `student_profiles` RLS re-evaluates `auth.<fn>()` per row; overlapping `documents` SELECT policies; plus the faculty re-embedding defect (§1.5) |
| Testing | 🟡 | **142 Python tests pass** (`.venv/bin/python -m pytest tests -q`), covering extraction / normalization / validation / idempotency / timetable queries / router / context / service. **Zero** tests for the FastAPI routers (auth, cookies, role gating, CR/admin review), OCR normalization, sensitive-data filtering, or expiry |
| `docs/decisions/` ADR log | ⬜ | Still missing — and `backend/app/core/config.py` already cites `docs/decisions/orion-auth-plan.md`, a file that does not exist |
| Frontend tests | ⬜ | None |

---

## Supabase Snapshot (live, measured 2026-09-21)

```text
profiles                 7   (3 STUDENT, 2 CR, 2 ADMIN)
student_profiles         5
faculty                185   (125 with email; 176 faculty / 17 admin / 7 support / 5 HOD)
courses                 43
rooms                   30      room_allocations        26
timetable_periods       26      timetable_entries     1263
timetable_entry_faculty 838
academic_calendar       30      mess_menus             124
announcements            1      hostel_wardens          78
documents               17      document_versions       17
document_chunks       1269   (384-dim)
ingestion_runs          25      approval_requests        2      audit_logs    3
departments              0      exams                    0      ingestion_jobs 0
```

Extensions: `pgvector` 0.8.2, `pgcrypto`, `uuid-ossp`, `pg_stat_statements`,
`supabase_vault`, `plpgsql`. RLS enabled on every table.

---

## What Should Be Implemented Next (prioritized, 2026-09-21)

### 1. Deploy something
Every item below is easier to validate against a real deployment, and the
current configuration (localhost cookies, one allowlisted redirect URL, a shared
`.env`) is what stands in the way. Start from
[`docs/backend-requirements.md`](docs/backend-requirements.md) §5: one warm
container in ap-south-1 for the API, the frontend on the same registrable
domain, `COOKIE_SECURE=true`, and the production redirect URL added to Supabase.

### 2. CR document upload → OCR → approval (the last big unbuilt slice)
Supabase Storage bucket → upload UI → `ingestion_jobs` queue → worker reusing
the proven `tesseract` path → preview/confirm → admin publish + `audit_logs`.
This needs the second container from Option C, so decide it alongside item 1.

### 3. Close the loop on AI answer quality
- Store faculty research-interest embeddings instead of re-embedding the whole
  directory per request (§1.5) — correctness-neutral, pure cost/latency win.
- Pass the authenticated student's cohort into semantic retrieval every time.
- Add a post-generation grounding check, and streaming if wanted.

### 4. Finish the UI wiring
`/calendar` (30 events live, no endpoint yet), `/courses`, `/exams`,
`/documents`, `/clubs`, `/notifications`, plus the mock remnants inside
`/dashboard`, `/admin`, `/search` and `/ai`.

### 5. Data gaps
- A September-onward mess menu (August 2026 is the only month loaded, and it
  has passed).
- `exams` — needs a source document before anything can be built.
- `departments` plus the timetable department-spelling decision, together.
- Record the `IEG 311` / `CSS 411` resolutions.
- Room↔timetable join, or an explicit decision to accept batch-level precision.

### 6. Testing and process debt
- No tests exist for the FastAPI layer at all — auth/cookie/role gating is the
  highest-risk untested code in the project.
- Create `docs/decisions/` and write the ADRs the code already cites (the auth
  plan, local embeddings, cookie sessions, consolidating on Python over the TS
  port).
- Work through the open Supabase security/performance advisor items.
