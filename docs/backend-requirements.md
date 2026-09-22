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

- **Google is the only sign-in method** (`GET /auth/me`, `POST /auth/logout`
  against Supabase GoTrue; no password signup/login — removed 2026-09-22):
  the browser drives the OAuth/PKCE handshake itself via supabase-js, then
  POSTs the resulting tokens once to `POST /auth/oauth/google/set-session`,
  which sets the session cookies (see `docs/auth.md`, CLAUDE.md §13's
  "Google sign-in token handling").
- Signup is restricted to `@iiitkottayam.ac.in` **in the database** by a
  Before-User-Created auth hook; role assignment, role-escalation blocking and
  CR approval are database functions, not application code
  (`20260913000001_capture_live_auth_drift.sql`, `docs/auth.md`).
- **Sessions are httpOnly cookies set by U2** (`orion_access_token`,
  `orion_refresh_token`), `SameSite=Lax`, `Secure` controlled by
  `COOKIE_SECURE`. The Google sign-in tokens do pass through frontend JS/
  `sessionStorage` briefly during the handshake before that handoff — see
  CLAUDE.md §13 for why and how that window is minimized.

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
4. The Google redirect URL is now the **frontend's own origin**
   (`FRONTEND_ORIGIN/auth/callback`, e.g. `http://localhost:8080/auth/callback`
   in dev) — not U2's — and must be added to the Supabase Auth allowlist per
   environment. Only `localhost` is allowlisted today.
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

### FR-3 — Semantic retrieval with hosted embeddings *(built; no longer a deployment constraint)*

> **Changed 2026-09-22** (docs/embeddings.md). Previously the API loaded
> `sentence-transformers/all-MiniLM-L6-v2` in-process, which made U2 a
> ~1.1 GB, ≥2 GB-RAM, must-stay-warm service. That is gone.

- Corpus: **17 documents / 17 versions / 1,269 chunks**, 768-dim Gemini
  vectors (`document_chunks.embedding_gemini`), searched through the
  `match_document_chunks_gemini` RPC with cohort / category / document-type /
  validity filters. Faculty research vectors are stored
  (`faculty.research_embedding`) and searched via `match_faculty_research`.
- **Query embeddings come from the Gemini API** (`gemini-embedding-2`) —
  exactly one call per SEMANTIC/HYBRID request, none for STRUCTURED ones.

Measured 2026-09-22 on the dev laptop (clean venvs built from the old and new
`backend/requirements.txt`):

| Item | MiniLM (before) | Gemini (after) |
|---|---|---|
| `requirements.txt` closure installed | **1.1 GB** (torch dominates) | **127 MB** |
| API startup (`import main`) | 0.28 s warm-disk | 0.30 s warm-disk |
| First semantic query in a fresh process | **10.1 s** warm-disk / 36.5 s cold-disk (torch import + model load) | +0.15 s (`google-genai` import + client) plus one API call |
| Peak RSS after first query embedding | **497–581 MB** | **86 MB** |
| Query embedding latency | ~6 ms warm (local CPU) | network round trip — see docs/embeddings.md §Measurements |
| Model weights / cache dir | ~90 MB, must persist | none |

**Deployment consequences:**

1. U2 is now a light, I/O-bound service: no model memory, no warm-up, small
   image. Scale-to-zero platforms are no longer ruled out by FR-3 (FR-1's
   cookie/domain rule still applies).
2. Outbound HTTPS to `generativelanguage.googleapis.com` is required for
   semantic/hybrid answers (it already was for generation), and
   `GEMINI_API_KEY` is a server-only secret.
3. Free-tier embedding quota is **100 texts/minute** (measured). Interactive
   queries don't wait out a quota window — they degrade to a
   "temporarily unavailable" warning; batch jobs pace themselves.

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
runs each one in a threadpool. Since 2026-09-22 there is no CPU-bound
embedding step (FR-3), so throughput is bounded by I/O waiting on Supabase and
Gemini, which the threadpool handles well.

**Deployment consequence:** 1–2 small uvicorn workers (~256–512 MB) are
enough for real load (a few dozen students).

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
| `google-genai` | corpus embeddings (Gemini API, since 2026-09-22) | small |
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
| U2 memory | ~256–512 MB (was ≥2 GB before the 2026-09-22 embedding migration) | FR-3 |
| U2 image size | small (~130 MB of Python deps) | FR-3 |
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

1. ~~Long-lived container, ≥2 GB RAM, no forced scale-to-zero~~ — lifted by the 2026-09-22 Gemini embedding migration — **FR-3**.
2. ~~1–2 GB image with a model cache~~ — no longer needed — **FR-3**.
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
- ✅ ~~FR-3 disqualifying (torch + model in a function)~~ — resolved by Option D (2026-09-22).
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

### Option D — Move embeddings out of the request path *(done 2026-09-22 — Gemini API, stored faculty vectors)*

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

**Option A now, Option C when CR uploads begin.** One small container
(~512 MB is ample since Option D landed on 2026-09-22) in Mumbai beside
Supabase, with the frontend on the same registrable domain, satisfies
everything that is built today at near-zero cost. Add the worker container
(plus Storage bucket and cron) as the first step of FR-7 — that is an
additional unit, not a rewrite.

---

## 6. What would change the answer

| If this happens | Then |
|---|---|
| FR-7 (CR upload/OCR) starts | worker container + Storage bucket + queue become mandatory → Option C |
| Streaming answers are added | needs a platform comfortable with long-lived streaming responses |
| Embedding model changes | re-embed with `scripts/reembed_gemini.py` into a new parallel column; revisit `FACULTY_MIN_SIMILARITY` |
| Free-tier serverless becomes a hard constraint | Option D first, then Option B — not before |
| Real student load (hundreds) | still one box; Supabase connection pooling is the first thing to look at |
| U1 and U2 must live on different domains | `SameSite=Lax` must become `None; Secure` — a deliberate, reviewed change |

---

## 7. Render deployment (2026-09-22) — configured, not yet applied

`render.yaml` at the repo root implements Option A: one Python web service
for `backend/`, no MiniLM/torch, no worker, no cron. It was written and
verified locally (see below) but **not created on Render in this session** —
no `RENDER_API_KEY` or dashboard access was available. Everything here is
ready for a human to apply.

### Service definition (from `render.yaml`)

| | |
|---|---|
| Type | Python web service (`runtime: python`) |
| Build | `pip install -r backend/requirements.txt` |
| Start | `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check | `GET /health` (already existed — `{"status": "ok"}`, no DB/Gemini call) |
| Region | `singapore` (closest Render region to Supabase `ap-south-1`) |
| Plan | `free` — change in the dashboard if the free tier's cold-start/sleep behavior is unacceptable |

### Verified locally before writing this section

- Built a clean venv from `backend/requirements.txt` alone: **128 MB**
  installed, **no torch, no sentence-transformers**.
- Ran the exact start command (`uvicorn main:app --host 0.0.0.0 --port
  $PORT`) against that clean venv: started in <1s, **75 MB RSS** at idle.
- `GET /health` → 200. Every protected route (`/timetable/day`, `/faculty`,
  `/mess/today`, `/announcements`, `/ai/ask`, `/auth/me`) → 401 without a
  session cookie, confirming auth gating runs before any Supabase/Gemini call.
- `embeddings.embed_query(...)` succeeded live against the real Gemini API
  (quota was available at test time — it is a **shared, resettable daily
  quota**, not a permanent block; see docs/embeddings.md §Status).
- `.venv/bin/python -m pytest tests -q` → 175 passed. `python -m compileall
  backend` → clean. `npx tsc --noEmit` → clean. `npm run build` → passes.

### Required Render dashboard environment variables

Set as **secrets** (no value lives in `render.yaml`):

| Variable | Source |
|---|---|
| `SUPABASE_URL` | Supabase project settings |
| `SUPABASE_ANON_KEY` | Supabase project settings — anon/publishable key, **not** service-role |
| `GEMINI_API_KEY` | Google AI Studio |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | already configured on the Supabase Auth provider; kept here only because `config.py` reads them |
| `API_BASE_URL` | this service's own Render URL, once assigned (e.g. `https://orion-api.onrender.com`, or the custom domain once set) |
| `FRONTEND_ORIGIN` | the frontend's exact origin, no trailing slash |

Set as **fixed values** (already in `render.yaml`):

| Variable | Value | Why |
|---|---|---|
| `PYTHON_VERSION` | `3.13.7` | matches the version this was developed/tested against |
| `ORION_EMBEDDING_PROVIDER` | `gemini` | keeps this service MiniLM/torch-free, per the deployment goal — see the caveat below |
| `COOKIE_SECURE` | `true` | Render terminates TLS in front of the app; cookies must still say `Secure` |

**`SUPABASE_SECRET_KEY` is deliberately absent.** No router uses it; adding
it to Render would be a real privilege-escalation risk for no benefit
(CLAUDE.md §13). It stays confined to `scripts/*` run locally/in a trusted
environment, never in this service.

### Known blocker: cookies won't work across two `onrender.com` subdomains

Verified against the live Public Suffix List
(`publicsuffix.org`/`publicsuffix/list` on GitHub): **`onrender.com` is a
listed public suffix.** That means `orion-api.onrender.com` and
`orion-frontend.onrender.com` are different "sites" under the same-site
cookie algorithm, not different origins on one site. `SameSite=Lax` cookies
(`backend/app/core/cookies.py`) are sent on top-level GET navigation across
sites, but **not** on cross-site `fetch`/XHR — which is exactly how
`src/lib/api-client.ts` calls this API (`credentials: "include"`). Deployed
as two bare `onrender.com` services, login will appear to succeed
(`set-session` returns 200) but every subsequent API call will arrive with
no cookie and 401.

**Fix:** put the frontend and this API on the same registrable custom
domain before relying on login in production — e.g. `app.example.edu` and
`api.example.edu` (same `example.edu` site; Lax cookies flow across
subdomains of one site). This needs a real domain, which is outside what
this session can provision. Do **not** work around it by switching to
`SameSite=None` — that reopens the CSRF surface `SameSite=Lax` exists to
close, and the task that requested this deployment was explicit not to
make that change casually.

### Known blocker: the Gemini embedding backfill is incomplete

Live-checked against Supabase at deployment-configuration time:
**992 / 1,269 `document_chunks` and 0 / 146 `faculty` rows have a Gemini
vector** (docs/embeddings.md §Status — unchanged since the migration
session). `ORION_EMBEDDING_PROVIDER=gemini` is still the right choice for
Render (keeps the service light, matches the deployment goal), but it means
regulation, hostel-rules, procedure and faculty-research questions will
return "temporarily unavailable" / no match until
`scripts/reembed_gemini.py --target all` is run to completion against a
reset quota. Structured queries (timetable/mess/announcements/faculty
directory) are unaffected. The alternative — `ORION_EMBEDDING_PROVIDER=minilm`
— would restore full semantic coverage immediately but requires installing
`backend/requirements-minilm-rollback.txt` (~1.1 GB, brings torch back),
which defeats the point of this deployment; it is documented as a rollback
path, not recommended here.

### Manual steps (cannot be done from this session)

1. Render dashboard → New → Blueprint → connect this GitHub repo → it will
   read `render.yaml` and propose the `orion-api` service.
2. Fill in the secret env vars listed above (`SUPABASE_URL`,
   `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `API_BASE_URL`, `FRONTEND_ORIGIN`).
3. Deploy, then copy the assigned `https://<name>.onrender.com` URL back
   into `API_BASE_URL` if it wasn't known yet, and redeploy.
4. In Supabase Dashboard → Authentication → URL Configuration, add the
   frontend's real callback URL (`https://<frontend-origin>/auth/callback`)
   to the redirect allowlist — it is currently only
   `http://localhost:8080/auth/callback`.
5. Decide the frontend's hosting so it shares a registrable domain with
   `orion-api` (see the cookie blocker above) before testing login.
6. Once the Gemini daily quota resets, run
   `.venv/bin/python scripts/reembed_gemini.py --target all` from a trusted
   local/CI environment (needs `SUPABASE_SECRET_KEY`, never Render) to
   finish the backfill.
