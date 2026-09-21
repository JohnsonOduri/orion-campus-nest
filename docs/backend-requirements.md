# ORION — Backend Functional Requirements & Deployment Profile

> Purpose: state exactly what ORION's backend does at runtime, so a hosting
> choice can be made on evidence instead of habit.
>
> Status date: **2026-09-21**, written against the merged tree (commit
> `146bb9a`) and measured against the live Supabase project
> `dgklugpgrnxhyjkvnacp` ("ORION", **ap-south-1**). Nothing here is projected
> from a design document.
>
> Related: [`docs/timetable.md`](timetable.md) · [`docs/query-router.md`](query-router.md) ·
> [`docs/auth.md`](auth.md) (database-side auth rules) ·
> [`tasks-done.md`](../tasks-done.md) · [`Work-done.md`](../Work-done.md)

---

## 1. What has to be deployed

ORION is **three deployable units plus a managed platform**. They have
genuinely different runtime shapes and should not be forced into one box.

| Unit | What it is | Today |
|---|---|---|
| **U1 — Frontend** | TanStack Start / React 19 SSR app (Vite 8, Nitro output) | `npm run dev`, localhost:8080 |
| **U2 — API** | **FastAPI** service (`backend/`, `uvicorn main:app`) — auth, OAuth, registration, CR, admin, timetable, faculty, mess, announcements, AI | localhost:8000 |
| **U3 — Ingestion** | Python CLI scripts (`scripts/*.py`) — PDF/CSV → validate → import | run by hand on a laptop |
| **P — Platform** | Supabase: Postgres 17 + pgvector + GoTrue auth (+ Storage, unused so far) | live, ap-south-1 |

U2 is the thing this document is really about: it is where every functional
requirement below lands, and it is the unit whose dependencies decide which
hosting options are actually viable.

```
browser ──httpOnly cookie──> U1 (SSR) ──fetch + forwarded Cookie──> U2 (FastAPI)
                                                                     │ caller's JWT
                                                                     ▼
                                                              P (Supabase, RLS)
U3 (scripts, service-role key) ─────────────────────────────────────▶ P
```

---

## 2. Functional requirements

### FR-1 — Authentication and session transport *(built)*

- Email/password signup + login (`POST /auth/signup`, `/auth/login`,
  `/auth/logout`, `GET /auth/me`) and **Google OAuth with PKCE**
  (`GET /auth/oauth/google/authorize` → `/auth/oauth/google/callback`),
  both against Supabase GoTrue.
- Signup is restricted to `@iiitkottayam.ac.in` **in the database** by a
  Before-User-Created auth hook; role assignment, role-escalation blocking and
  CR approval are database functions, not application code
  (`20260913000001_capture_live_auth_drift.sql`, `docs/auth.md`).
- **Sessions are httpOnly cookies set by U2** (`orion_access_token`,
  `orion_refresh_token`, plus a short-lived `orion_oauth_pkce_verifier`),
  `SameSite=Lax`, `Secure` controlled by `COOKIE_SECURE`. The browser never
  holds a Supabase token in JS.

**Deployment consequences — these are hard constraints, not preferences:**

1. **U1 and U2 must be served from the same registrable domain**
   (e.g. `orion.example.edu` + `api.orion.example.edu`). With `SameSite=Lax`,
   a browser will not send the session cookie to an API on a *different* site,
   so a split like `vercel.app` frontend + `onrender.com` API **silently breaks
   every authenticated request**. The alternatives are `SameSite=None; Secure`
   (weaker, needs an explicit code change) or putting U2 behind the same domain
   via a path prefix/proxy.
2. `COOKIE_SECURE=true` and HTTPS are mandatory outside local dev.
3. CORS is locked to exactly one origin with credentials enabled
   (`FRONTEND_ORIGIN`) — every preview deployment on a new URL needs that
   variable set, or it will fail CORS *and* cookies.
4. The Google redirect URL (`API_BASE_URL/auth/oauth/google/callback`) must be
   added to the Supabase Auth allowlist per environment. Only `localhost` is
   allowlisted today.
5. U2 holds **no** service-role key in any current router — every request runs
   on the caller's own JWT under RLS. Keep it that way.

### FR-2 — Structured query serving *(built)*

Deterministic questions are answered by SQL, never by a model. Live endpoints:

| Endpoint | Backed by |
|---|---|
| `GET /timetable/day`, `/week`, `/next` | `orion_day_timetable`, `orion_week_timetable`, `orion_next_class` (all `SECURITY INVOKER`) |
| `GET /faculty` | `faculty` (185 rows) |
| `GET /mess/today`, `/week` | `mess_menus` (124 rows) |
| `GET /announcements` | `announcements` |
| `GET /admin/cr-requests`, `POST …/review` | `approval_requests` + `review_cr_access_request` |
| `GET /admin/announcements`, `POST …/review` | `review_announcement` |
| `POST /cr/access-request`, `POST /cr/announcements` | `submit_cr_access_request`, `submit_announcement` |
| `POST /auth/register` | `complete_registration` |

Live data served: **1,263 timetable entries**, 26 periods, 43 courses,
185 faculty (176 teaching / 17 administrative / 7 professional support / 5 HOD;
125 with email), 30 rooms, 26 room allocations, 30 calendar events,
124 mess rows, 78 hostel wardens.

**Deployment consequence:** stateless and cheap; latency is dominated by the
round trip to Supabase. **Deploy U2 in or near ap-south-1 (Mumbai)** — every
one of these endpoints pays that hop, some of them twice (profile lookup +
query).

### FR-3 — Semantic retrieval with in-process embeddings *(built — the binding constraint)*

- Corpus: **17 documents / 17 versions / 1,269 chunks**, 384-dim vectors,
  searched through the `match_document_chunks` RPC with cohort / category /
  document-type / validity filters.
- **Query embeddings are computed inside U2**, not bought from an API:
  `backend/query/retrieval.py` lazily loads
  `sentence-transformers/all-MiniLM-L6-v2`. This was a deliberate zero-cost
  decision, and it is what makes U2 heavy.

Measured footprint:

| Item | Value |
|---|---|
| `backend/requirements.txt` closure | **~1.1 GB installed** (`sentence-transformers` → `torch` dominates) |
| Model weights | ~90 MB, downloaded on first use, then cached on disk |
| Resident memory once loaded | several hundred MB above baseline Python |
| First request after a cold start | seconds (torch import + model load) |
| Warm embedding latency | tens of ms |

**Deployment consequences:**

1. U2 needs **≥2 GB RAM** and a **long-lived, warm process**. A scale-to-zero
   platform re-pays the torch import and model load on every cold start.
2. The image is ~1–2 GB. Platforms with small bundle/image limits are out.
3. The model cache must survive restarts (a writable cache dir or a
   bake-into-image step), or every deploy re-downloads it.
4. **Known inefficiency, worth fixing before it becomes a hosting argument:**
   the faculty hybrid search (`faculty_research_search`) re-embeds *every*
   faculty research-interest string **on every request** instead of using
   stored vectors. That is CPU burned per query and grows with the directory.

### FR-4 — Grounded generation *(built)*

- `POST /ai/ask` routes the question (STRUCTURED / SEMANTIC / HYBRID /
  SMALL_TALK / UNSUPPORTED), retrieves, builds a `GroundedContext`, then calls
  **Gemini `gemini-3.5-flash-lite`** over plain REST with `max_output_tokens`
  defaulting to 256.
- Cost discipline is in the code: no LLM call when there is nothing to ground
  on, no LLM call for small talk (router-authored reply), no retry loop.
- If Gemini is unconfigured or failing, the endpoint **degrades to
  retrieval-only** and says so (`generation_available: false`) rather than
  erroring.

**Deployment consequences:** outbound HTTPS to
`generativelanguage.googleapis.com` must be allowed; `GEMINI_API_KEY` is a
server-only secret; a chat request is retrieval + generation in one
**synchronous** call, so the platform's request timeout must comfortably exceed
it (**≥30 s**). Responses are not streamed today — adding streaming later is a
code change, not a platform change, but the timeout headroom matters now.

### FR-5 — Request concurrency model *(built, needs a deliberate setting)*

Every FastAPI handler is a plain `def`, not `async def` — Starlette therefore
runs each one in a threadpool. Combined with FR-3's CPU-bound embedding step,
throughput is bounded by CPU, not by I/O waiting.

**Deployment consequence:** size for **1–2 uvicorn workers with ≥2 GB each**,
not for many tiny replicas — each replica pays the full model memory cost.
This is fine: real load is a few dozen students, not thousands.

### FR-6 — Ingestion pipeline *(built as scripts, not as a service)*

Proven path: `PDF/CSV → layout-aware extraction → normalization → strict
validation → preview + validation JSON → human approval → idempotent import →
ingestion_runs audit row`. 25 audited runs to date, covering three timetable
PDFs, classroom details, academic calendar, mess menu, hostel wardens,
17 documents, and the faculty directory rebuild (`scripts/rebuild_faculty.py`).

| Dependency | Why | Weight |
|---|---|---|
| `pdfplumber` | geometry-first extraction (never naive text dump) | small |
| `pytesseract` + the **`tesseract` system binary** | scanned PDFs with no text layer | system package + per-language tessdata |
| `sentence-transformers` / `torch` | corpus embeddings | ~1.1 GB (shared with U2) |
| `supabase` (service-role) | trusted writes | small |

**Deployment consequences:** U3 is the **only** unit that holds the
service-role key, and it runs minutes-long jobs. It can stay a laptop workflow
for now; the moment FR-7 lands it must become a separate worker container with
`tesseract` in the image — deliberately *not* the same process as U2, so the
service-role key never sits in the request-serving unit.

### FR-7 — CR upload → OCR → admin approval *(partly built; the main gap)*

Built: CR access requests and the **announcement** submit → admin review path
(`/cr/*`, `/admin/*`, with `audit_logs` written on every decision).

Missing, and it is the whole document half of the product:

1. Supabase **Storage bucket does not exist** — no file can be uploaded yet.
2. `ingestion_jobs` is **0 rows** — no queue, no worker, no retry/status.
3. No OCR preview/confirm screen; no publish step that turns an approved
   document into authoritative rows.

**Deployment consequence:** this needs object storage with signed uploads, a
job queue or polling worker, and the FR-6 dependency stack in a container that
can run for minutes. **This is the requirement that forces a second deployable
unit.**

### FR-8 — Lifecycle and scheduled work *(partly built)*

- Every time-sensitive row carries `valid_from` / `valid_until` / `status`, and
  queries filter on them (the timetable RPCs evaluate validity against the
  occurrence date).
- Not built: a sweeper that expires stale announcements/menus/events, and
  re-indexing when a source document is superseded.

**Deployment consequence:** one daily **cron/scheduled trigger**. Cheap
anywhere; just make sure the platform has one.

### FR-9 — Time handling *(built — do not regress)*

`20260921000004_timetable_ist_timezone_fix.sql` pins timetable day/time
behaviour to **IST**. "What's my next class?" is wrong by hours if a container
runs on UTC local time and any new code reads the process clock.

**Deployment consequence:** set `TZ` explicitly and keep time logic in SQL.
Anything new that computes "now" must go through the same path.

### FR-10 — Cohort isolation *(enforced in data)*

`UG Regulations 26 onwards` vs `21-25` must never bleed together; chunks carry
`cohort` (`ADM2026` 798 chunks, `21-25` 376). Any cache added later **must key
on cohort**, or it will break this rule silently.

### FR-11 — Observability and audit *(partial)*

- `ingestion_runs` (25) audits imports; `audit_logs` (3) records approvals
  (2 CR approvals, 1 announcement rejection — all real).
- Gemini failures log to stderr and degrade gracefully.
- Missing: structured request logging, auth-failure and routing-decision
  metrics, latency.

**Deployment consequence:** logs must be retained long enough to debug an
overnight ingestion job — minutes of retention is not enough. Never log
tokens, credentials, or document contents.

### FR-12 — Secrets

| Secret | Needed by | Must never reach |
|---|---|---|
| `SUPABASE_SECRET_KEY` (service role) | U3 only | U1, U2, any browser bundle |
| `SUPABASE_ANON_KEY` | U2 (request-scoped clients) | — public by design |
| `GEMINI_API_KEY` | U2 | browser |
| `GOOGLE_CLIENT_SECRET` | Supabase dashboard | repo, browser |
| `API_BASE_URL`, `FRONTEND_ORIGIN`, `COOKIE_SECURE`, `VITE_API_BASE_URL` | per-environment config | — |

All of these currently come from **one repo-root `.env`** read by both the
Python and JS sides. A real deployment needs per-environment variables, not a
shared file.

---

## 3. Non-functional requirements

| Requirement | Target | Driven by |
|---|---|---|
| Region | ap-south-1 / Mumbai, co-located with Supabase | FR-2 |
| U2 memory | ≥2 GB, warm | FR-3 |
| U2 image size | 1–2 GB tolerated | FR-3 |
| Request timeout | ≥30 s | FR-4 |
| Cold starts | avoid for U2 | FR-3 |
| Same-site frontend + API domain | mandatory | FR-1 |
| HTTPS + `COOKIE_SECURE=true` | mandatory | FR-1 |
| Worker (when FR-7 starts) | container, ≥2 GB, minutes-long jobs, `tesseract`, service-role key | FR-6/FR-7 |
| Cron | daily | FR-8 |
| Timezone | IST pinned | FR-9 |
| Concurrency | tens of users; 1–2 workers | FR-5 |
| Cost | near-zero prototype; no GPU, no always-on fleet, no separate vector DB | CLAUDE.md §30 |

Current scale, for honesty about sizing: **7 profiles** (3 STUDENT, 2 CR,
2 ADMIN), 5 student profiles. This is a one-small-box problem.

---

## 4. Screening test for any candidate platform

1. Long-lived container, ≥2 GB RAM, no forced scale-to-zero — **FR-3**.
2. 1–2 GB image accepted, with a persistent or baked model cache — **FR-3**.
3. Available in/near ap-south-1 — **FR-2**.
4. Can serve U1 and U2 under **one registrable domain** — **FR-1**.
5. ≥30 s request timeout — **FR-4**.
6. Per-environment secrets, HTTPS, settable `TZ` — **FR-1/FR-9/FR-12**.
7. A second container/job runner + cron for U3/FR-7 — **FR-6/FR-7**.
8. Log retention in days, not minutes — **FR-11**.
9. ~free at this scale.

Requirements 1, 2 and 4 are where most default answers ("just put it on
serverless") fail.

---

## 5. Options

### Option A — One container for U2, static/SSR frontend on the same domain *(recommended now)*

U2 as a container on Fly.io / Render / Railway / a small VM in Mumbai; U1
deployed so it shares the registrable domain (subdomain or path proxy);
Supabase unchanged; U3 stays a laptop workflow.

- ✅ Satisfies FR-1 through FR-5, FR-9, FR-12 as the code stands today.
- ✅ Warm process, no cold-start penalty, model cache persists, generous timeouts.
- ✅ Cheapest honest answer: one small always-on instance.
- ❌ FR-7 (CR document uploads) still impossible — no worker, no bucket.

### Option B — Serverless functions for U2

- ✅ Zero-ops, free tier, per-branch previews.
- ❌ FR-3 is disqualifying as written: torch + model in a function is too large
  and too cold-start-sensitive.
- ⚠️ FR-1's `SameSite=Lax` cookie rule usually breaks here, because the
  function host is a different site from the frontend host.
- **Viable only after Option D.**

### Option C — Option A + a worker container *(the target once FR-7 starts)*

Adds a second container consuming `ingestion_jobs`, with `tesseract` installed
and the service-role key scoped to it alone, plus a Supabase Storage bucket and
a daily cron.

- ✅ Satisfies every requirement including FR-6/FR-7/FR-8.
- ✅ Clean secret boundary: the request-serving unit never holds service-role.
- ❌ Two units to operate; the worker image is the heavy one.

### Option D — Move embeddings out of the request path

Replace in-process MiniLM with a hosted embedding API, a tiny dedicated
embedding service, or precomputed vectors (which would also fix FR-3's faculty
re-embedding).

- ✅ Shrinks U2 to a light I/O-bound service; unlocks Option B.
- ❌ Adds per-query cost or another unit, and **any model change must preserve
  vector-space compatibility with the 1,269 stored chunks** — otherwise the
  whole corpus must be re-embedded.
- Worth doing only if free-tier serverless becomes a hard requirement. Storing
  faculty-interest vectors is worth doing **regardless**.

### Recommendation

**Option A now, Option C when CR uploads begin.** One warm ~2 GB container in
Mumbai beside Supabase, with the frontend on the same registrable domain,
satisfies everything that is built today at near-zero cost. Add the worker
container (plus Storage bucket and cron) as the first step of FR-7 — that is an
additional unit, not a rewrite. Treat Option D as an optimization to revisit if
hosting cost or cold starts ever actually bite; do the cheap half of it (store
faculty embeddings) either way.

---

## 6. What would change the answer

| If this happens | Then |
|---|---|
| FR-7 (CR upload/OCR) starts | worker container + Storage bucket + queue become mandatory → Option C |
| Streaming answers are added | needs a platform comfortable with long-lived streaming responses |
| Embedding model changes | re-embed all 1,269 chunks; revisit the 0.19 similarity threshold |
| Free-tier serverless becomes a hard constraint | Option D first, then Option B — not before |
| Real student load (hundreds) | still one box; Supabase connection pooling is the first thing to look at |
| U1 and U2 must live on different domains | `SameSite=Lax` must become `None; Secure` — a deliberate, reviewed change |
