# ORION — final production checklist

Status 2026-09-23. ✅ done · ⏳ in progress · ⬜ needs a person (credentials,
money or a decision). Tasks in `todo.md` (Gemini re-embedding backfill,
Render dashboard setup) are deliberately not repeated here.

## 1. AI answers (primary goal)

- ✅ Answers work with **no Gemini at all**: every reply is written from
  Supabase rows or quoted from an approved document (`backend/query/compose.py`).
  Gemini, when reachable, only rewords a quoted rule; a circuit breaker skips
  it for 30 min after a quota error (`llm_client.rephrase_passage`).
- ✅ Document questions use Postgres full-text search (no model, no quota) with
  cohort isolation in SQL and coordination ranking
  (migrations `20260922100000`, `20260922110000`).
- ✅ Router covers calendar/exams, announcements, wardens, HOD/dean/registrar/
  medical/counsellor, research topics, my courses, my profile, classroom, free
  time, out-of-scope records; question-shaped leftovers go to document search.
- ✅ Follow-ups ("Who teaches it?", "And dinner?", "What does he research?").
- ✅ `AI-task.md`: 134-question bank; `scripts/run_ai_task.py` runs it through
  the real pipeline as a signed-in student. Last run: **0 errors, 3 intentional
  flags, median ~175 ms** (`AI-task-results.md`).

## 2. Portal pages — no mock data left

- ✅ `/calendar`, `/exams`, `/courses`, `/documents`, `/profile`, `/clubs`,
  `/search`, dashboard sections — all live (`backend/app/api/campus.py`).
  `src/lib/mock-data.ts` deleted.
- ✅ Removed misleading UI: fake grades, hall tickets, seat numbers,
  attendance %, a fake "campus QR ID", fake download buttons, a hard-coded
  name/clock/weather, and settings toggles (incl. "Two-factor auth") that did
  nothing.
- ✅ Loading → error-with-retry → empty states on every new page (`QueryState`).
- ✅ Mobile: AI in the bottom nav, safe-area insets on header/nav, chat fills
  the screen; `/ai?q=` deep links from other pages.

## 3. Correctness / hardening

- ✅ Timetable & mess APIs used the server's UTC date → fixed to IST
  (wrong day between 00:00 and 05:30 IST on Render).
- ✅ Per-user rate limits: `/ai/ask` 20/min, `/tts/speech` 90/min; question
  length capped at 1,000 characters.
- ✅ Revoked anonymous EXECUTE on admin review RPCs and document search
  (migration `20260922120000`); Supabase advisor shows nothing new from this work.
- ✅ Chat conversations persisted under RLS (`ai_conversations` / `ai_messages`).

## 4. Verification

- ✅ `pytest` 264 passed · `npm test` (Vitest) 23 passed · `tsc` clean ·
  ESLint clean on changed files · `npm run build` passes · every page
  server-renders with 200.

## 5. Deploy

- ✅ Pushed to `main`; Render rebuilt the API (~100 s) and Vercel the frontend.
- ✅ Live smoke test (`scripts/smoke_live.py`): 19/19 checks pass against
  `https://orion-campus-nest.onrender.com` as the test student — every
  endpoint, one question per answer category, and a 401 for anonymous calls.
  It caught one real regression (attendance quoting R.5.2 instead of R.5.1),
  now fixed and re-deployed.
- ✅ `/health` reports the deployed commit (`RENDER_GIT_COMMIT`), so a deploy
  is verified by hash instead of guessed from behaviour. Live = `12d66a8`.
- ✅ Live `/ai/ask` median **2.45 s** (was ~3.9 s before the round-trip fix);
  ~0.5 s of that is this machine's round trip to Oregon. Locally: ~175 ms.

## 6. Needs a person

- ⬜ **Region mismatch is the main latency cost.** `render.yaml` pins the API
  to **Oregon**; Supabase is in **ap-south-1 (Mumbai)**, so every database
  round trip costs ~250 ms. Measured today: the same question takes ~175 ms
  locally and ~3 s live. Round trips per question were cut from 8-10 to 5-7
  (one insert for both chat turns, cached profile), but the fix is an API in
  Singapore/Mumbai. Render cannot change a service's region after creation —
  it needs a new service (the blueprint is ready) and `API_BASE_URL` updated.
- ⬜ **Render cold starts** (~40 s on the free plan, measured today). Upgrade to
  an always-on instance, or add an external uptime ping, if first-request
  latency matters for real students.
- ⬜ **Login across domains**: frontend on `*.vercel.app` and API on
  `*.onrender.com` are different sites; cookies need `COOKIE_SAMESITE=none` +
  `COOKIE_SECURE=true` on Render, or one custom domain for both
  (`docs/backend-requirements.md` §7). Decide and set in the Render dashboard.
- ⬜ **Vercel connector access**: the Vercel integration here returns 403 for
  the `johnson-oduris-projects` scope; re-authorise it to let deployments be
  checked from this tool.
- ⬜ **Data gaps** ORION says out loud rather than hides: no per-course exam
  timetable, no holidays on the calendar, mess menu is last published in
  August, no announcements approved, `office_hours` empty for all faculty,
  no room per timetable slot.
- ⬜ **Kokoro voice** in production needs a ≥ 2 GB always-on instance (paid) —
  see `docs/tts.md` §4. Browser voice is the current provider.
- ⬜ Supabase Auth: enable leaked-password protection (advisor warning; only
  matters if password sign-in is ever re-enabled — Google is the only method).
