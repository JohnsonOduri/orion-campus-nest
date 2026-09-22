# Query Router / Retrieval / Context Layer

Deterministic query routing → structured/semantic/hybrid retrieval →
grounding-ready context. No LLM call anywhere in this layer (see §5).

Implemented **twice, kept in lockstep**: `backend/query/` (Python —
`types.py`, `router.py`, `retrieval.py`, `context.py`, `service.py`,
`llm_client.py` scaffolded/unused) is the independently-tested reference
implementation; `src/lib/query/` (TypeScript — `types.ts`, `router.ts`,
`retrieval.ts`, `context.ts`, `service.ts`, `embed.ts`) is a same-behavior
port wired into the live chat UI (§8), since the frontend is a Node/Vite
app and can't call into a Python process at request time. Both were
verified to produce identical results against the same live queries
(§6, §8) — same regex rules, same RPCs, same `min_similarity` constant, and
numerically-equivalent embeddings (verified: the JS ONNX build of
`all-MiniLM-L6-v2` and the Python `sentence-transformers` build of the same
checkpoint produce vectors matching to 6+ decimal places on a real query).
Any change to routing rules or retrieval logic should be made in both
places, or the port will drift from the reference.

```
raw query
   │  router.classify()
   ▼
QueryPlan (route: structured | semantic | hybrid | small_talk | unsupported)
   │  service._dispatch_structured() / retrieval.semantic_search() /
   │  retrieval.faculty_topic_and_schedule() / (small_talk: canned reply,
   │  no retrieval call at all)
   ▼
RetrievalResult (StructuredFact[] + SemanticSnippet[], each cited)
   │  context.build_context()
   ▼
GroundedContext (has_answer: bool, facts, snippets, warnings)
```

## 1. Routing (`router.py`)

Pure, offline, regex/keyword-based — no LLM, no network, no cost. Matches
the STRUCTURED / SEMANTIC / HYBRID / SMALL_TALK / UNSUPPORTED examples in
README §8 and AGENTS.md §4-§5:

| Pattern | Route | Intent |
|---|---|---|
| "next class", "where is my next class" | STRUCTURED | `NEXT_CLASS` |
| "today" + class/timetable/schedule | STRUCTURED | `DAY_TIMETABLE` |
| "this week"/"weekly" + class/timetable/schedule | STRUCTURED | `WEEK_TIMETABLE` |
| a named weekday, "yesterday", or "tomorrow" + class/timetable/schedule | STRUCTURED | `DAY_OF_WEEK_TIMETABLE` |
| a specific clock time ("10:30", "3pm") + class/timetable/schedule | STRUCTURED | `CLASS_AT_TIME` |
| "who teaches `<course code>`" | STRUCTURED | `FACULTY_FOR_COURSE` |
| "`<course code>` about/credits/syllabus/prerequisites", or "what is/tell me about `<course code>`" | STRUCTURED | `COURSE_INFO` |
| "tell me about `<Title> <Name>`", "who is `<Title> <Name>`", "`<Name>`'s email/office/office hours" | STRUCTURED | `FACULTY_LOOKUP` |
| mess/canteen/food/menu/breakfast/lunch/dinner/snacks | STRUCTURED | `MESS_TODAY` (`MESS_WEEK` with "this week"/"weekly", `MESS_ON_DAY` with a named weekday/"yesterday"/"tomorrow") |
| "faculty" + work/research/interest, or "recommend a faculty" | HYBRID | — |
| attendance/regulation/policy/cgpa/credit/hostel/procedure/curriculum/… | SEMANTIC | — |
| the *entire* message is a greeting/thanks/farewell/"what can you do"/"how are you" | SMALL_TALK | — |
| anything else | UNSUPPORTED | — |

**SMALL_TALK is answered without any retrieval call or LLM call.** The
router itself picks the canned reply text (into `QueryPlan.topic_text`);
`service.answer_query` wraps it directly into a `StructuredFact` without
touching Supabase, and `backend/app/api/ai.py` uses that fact's claim as
the response `answer` verbatim, skipping `llm_client.generate()` entirely —
so small talk never costs a Gemini call regardless of whether
`GEMINI_API_KEY` is configured. The match is anchored to the whole message
(`^...$`), so "hi what is my next class" still routes to `NEXT_CLASS`, not
small talk — only a message that *is* just small talk short-circuits.
Five categories: greeting (time-of-day-aware reply — "Good morning/
afternoon/evening"), thanks, farewell, capabilities ("what can you do",
"help", "who are you"), and "how are you". Thanks/farewell/"how are you"
each pick randomly from 2–3 pre-written variants (`router.py`'s
`_THANKS_REPLIES`/`_BYE_REPLIES`/`_HOW_ARE_YOU_REPLIES`) so repeated small
talk doesn't read as one hardcoded string — the *routing decision* stays
fully deterministic (same input always → same `RouteType`), only the reply
text varies.

`FACULTY_LOOKUP`'s "tell me about `<name>`" pattern **requires** a title
(Dr./Prof./Mr./Ms./Mrs.) — without one, "tell me about the campus
regulations" would otherwise be swallowed as if "the campus regulations"
were a faculty name. The possessive form ("`<Name>`'s email") doesn't
require a title, relying instead on capitalized-word structure as a
proper-noun heuristic (case-sensitive on purpose).

`DAY_OF_WEEK_TIMETABLE`'s date resolution (`retrieval._resolve_day_reference`)
is shared with mess's `MESS_ON_DAY` (`retrieval.mess_on_day`) — one
implementation of "yesterday"/"tomorrow"/a named weekday → an actual date,
not two near-identical ones. Mess menu retrieval (`retrieval.mess_today`/
`mess_week`/`mess_on_day`) also reuses the same row-fetching/weekly-
rotation-fallback helpers as the REST `GET /mess/today`/`GET /mess/week`
endpoints (`backend/app/api/mess.py`) — one implementation
(`retrieval.py`'s `mess_all_active_rows`/`mess_menu_for_day`/
`split_mess_items`), not two kept in lockstep by hand. A specific meal
word (breakfast/lunch/dinner/snacks) narrows every mess intent to just
that meal — found live: leaving all 4 meals in the fact list for one day
was ambiguous enough that generation sometimes hedged with "I don't have
that information" even though the exact fact was present.

`QueryPlan` never carries anything that looks like a retrieved fact —
`reasoning` is an audit/debug string, not an answer (enforced by
`test_plan_never_carries_fabricated_answer_data`).

An LLM-backed classifier could later replace or augment this for genuinely
ambiguous queries without changing the `QueryPlan` contract — nothing
downstream needs to know how the plan was produced.

## 2. Retrieval (`retrieval.py`)

**Every function takes a request-scoped Supabase client** — anon key +
`client.postgrest.auth(<caller's JWT>)`, exactly `src/lib/supabase-server.ts`'s
pattern. Never service-role. RLS policies already enforce `status='active'`
and validity windows on every table touched here (`timetable_entries`,
`documents`, `document_chunks`, `faculty`, `courses`) — this layer relies on
that, it doesn't duplicate it.

### Structured

Wraps the existing `orion_*` RPCs unchanged (docs/timetable.md §9-§11):
`orion_next_class`, `orion_day_timetable`, `orion_week_timetable`.
`DAY_OF_WEEK_TIMETABLE` ("classes on Monday") also calls `orion_day_timetable`,
with the date computed from the nearest upcoming occurrence of the named
weekday (today counts if today already is that weekday) — no new RPC, no
day-of-week hard-coded on the SQL side. Always
called with `p_user_id=None` — identity is resolved server-side from the
caller's JWT via `orion_resolve_user`, never trusted from client input
(CLAUDE.md §14, §27). `faculty_for_course` is a direct RLS-scoped table
query (courses → timetable_entries → faculty), no new RPC needed.

### Semantic

Wraps the existing `document_chunks` pgvector corpus
(`scripts/ingest_documents.py`) through a new RPC,
`match_document_chunks(query_embedding, match_count, filter_cohort,
filter_category, filter_document_type, as_of)` — `security invoker` (RLS
still applies), added in migration `20260911020000_add_match_document_chunks_rpc.sql`.
It wraps the corpus; it does not re-embed or re-ingest anything.

> **Updated 2026-09-22:** the API now calls `match_document_chunks_gemini`
> (same signature and filters, 768-dim) and embeds the query with Gemini
> `gemini-embedding-2` through `backend/query/embeddings.py` — the same module
> used at ingestion time, so query and corpus vectors share one space. The
> MiniLM RPC above is kept only as a rollback path. See `docs/embeddings.md`. Validity filtering (`valid_from`/`valid_until`) is
applied inside the RPC in addition to the `documents` RLS policy, so an
expired document never surfaces regardless of caller role.

`cohort`/`category`/`document_type` filters are optional parameters, not
auto-derived from query text — CLAUDE.md §20/AGENTS.md §17: cohort must come
from the authenticated user's own academic context, never guessed from
free-text. The router intentionally leaves `semantic_filters` empty for a
plain SEMANTIC query; a future caller (the real per-student API) should
pass the student's cohort in explicitly. Without a cohort filter, a query
like "attendance requirements" correctly returns matches from *both*
regulation cohorts (verified in `scripts/verify_query_router.py`) — this is
correct behavior for an unfiltered call, not a defect.

### Hybrid

`faculty_topic_and_schedule`: embeds the topic locally, ranks all faculty
with non-null `research_interests` by in-memory cosine similarity (≈60
rows — no vector index needed), then fetches each match's live teaching
schedule (`timetable_entry_faculty` → `timetable_entries` → `courses`).

**No document corpus is touched for this intent** — matches the README §8
hybrid example exactly (faculty research + schedule, not documents).

Availability is never overstated: `faculty.office_hours` is `NULL` for
every row currently (`tasks-done.md` §1.7), so every hybrid result carries
an explicit warning — *"no office_hours on file — reporting teaching
schedule only, not confirmed availability"* — per AGENTS.md §18's required
safe fallback. The teaching schedule is reported as exactly that, a
schedule, never rephrased as "available then."

`min_similarity=0.19` is a corpus-tuned constant, not a theoretically clean
cutoff — see the docstring in `retrieval.py` for the measurement that
produced it (a small local model scores a bare acronym like "NLP" lower
against a full research-interest phrase than a spelled-out query would;
0.19 sits below the verified 0.20-0.30 band for two real NLP researchers on
this corpus, above the ~0.14-0.18 band for tangential matches).

## 3. Context (`context.py`)

Pure function: `RetrievalResult → GroundedContext`. The only real decision
is `has_answer = bool(facts) or bool(snippets)` — and if that's `False`,
a warning explaining why is guaranteed to exist (never a silent empty
result that could be mistaken for "checked, nothing there").

## 4. LLM (`llm_client.py`) — scaffolded, not wired in

Per the task that created this layer: **no LLM call is made anywhere in
`router.py` / `retrieval.py` / `context.py` / `service.py`.**
`llm_client.py` exists only so `GEMINI_API_KEY` (present in `.env`) has a
ready integration point for the next slice:

- defaults to `gemini-2.0-flash-lite` (cheapest tier with a free quota, not
  a Pro model);
- `max_output_tokens` defaults to 256 — a grounded answer should be short;
- `generate(context, ...)` **refuses to call the API at all** when
  `context.has_answer` is `False` — a safe "I don't know" costs zero
  tokens;
- no retry loop, no streaming — a caller that wants those opts in
  explicitly rather than burning quota on silent retries;
- plain REST call (`urllib`), no SDK dependency.

Not imported by any other module in `backend/query/`.

## 5. Security model (unchanged, verified)

Identical to the timetable API (CLAUDE.md §13-§15, docs/timetable.md §11):

- request-scoped client (anon key + caller's JWT), never service-role, for
  every retrieval call in this layer;
- `orion_resolve_user` resolves identity server-side; `p_user_id` is always
  passed as `None` from this layer — a client-supplied user id is never
  trusted;
- every RPC/table this layer touches is `security invoker` and RLS-scoped;
- verified live against a real authenticated session (see §6) — not just
  asserted;
- the router never parses identity/context claims out of the message text —
  a user typing "I am from batch 3 2024 BCS 66" into the chat has zero
  effect on routing or retrieval (`test_client_supplied_batch_is_never_parsed_into_the_plan`);
  personalization comes only from the authenticated user's own profile via
  `orion_resolve_user`, exactly AGENTS.md §17's rule.

## 6. Testing

**Offline (`pytest tests/`, part of the standard test suite — 124 passed/
15 skipped as of this writing, no network/credentials needed):**

- `tests/test_query_router.py` — pure `classify()` behavior including the
  three required cases, mess-menu classification, small-talk classification
  (including that a greeting embedded in a real question is not swallowed),
  and the UNSUPPORTED fallback.
- `tests/test_query_context.py` — `build_context`'s has-answer/warning
  invariant.
- `tests/test_query_service.py` — confirms the SMALL_TALK path never
  touches the Supabase client (`answer_query(None, "hi")` must not raise).

**Live end-to-end (`scripts/verify_query_router.py`, not part of `pytest`
— needs network + Supabase credentials, matching how
`scripts/verify_import.py` is kept separate from the offline suite):**

Authenticates as the existing test student
(`orion-test-student-a@iiitkottayam.ac.in`, provisioned by
`scripts/create_test_students.py`) via a real password sign-in, builds a
request-scoped client from that JWT exactly as `supabase-server.ts` would,
and runs the three required cases against the live hosted database:

```bash
.venv/bin/python scripts/verify_query_router.py
```

Verified output (2026-09-11):

1. **"What is my next class?"** → STRUCTURED/`NEXT_CLASS` → `orion_next_class`
   RPC → `ICS 211 DESIGN AND ANALYSIS OF ALGORITHMS`, day 1, 09:00-09:55 (the
   authenticated student's actual Semester 3 timetable).
2. **"What are the attendance requirements?"** → SEMANTIC → top hit
   `R.6.0 Attendance, Condonation and Course Feedback` (UG Regulations,
   2026 admission onwards) at 0.583 cosine similarity, plus the 21-25
   cohort's equivalent section (both cohorts, since no cohort filter was
   supplied).
3. **"Which faculty work in NLP and when can I meet them?"** → HYBRID →
   Dr. Manu Madhavan (0.295) and Dr. Sara Renjit (0.196), both with
   "Natural Language Processing" as their first listed research interest,
   each with their live teaching schedule and an explicit
   no-office-hours-on-file warning.

All three produced `has_answer=True` with real, cited, RLS-respecting data.
No data was invented for any case.

## 7. Frontend wiring (`src/lib/query/`, `src/lib/chat-api.ts`)

The AI chat panel (`src/components/ai/ai-chat.tsx`, previously a canned
1.1s-delay response) now calls a real TanStack Start server function,
`askOrion` (`src/lib/chat-api.ts`), which runs the TypeScript port of this
layer and returns a formatted, cited response — **still no LLM call**; the
chat renders the `GroundedContext` directly (facts as bullet points,
snippets with `[Document — Section]` citations, warnings prefixed `⚠️`).

Each AI message in the transcript carries a small badge showing which
route answered it (`STRUCTURED · LIVE DB` / `SEMANTIC · DOCUMENTS` /
`HYBRID · FACULTY + SCHEDULE`) — deliberately visible so routing behavior
is easy to see while testing, not just correct.

**Embeddings in Node**: `src/lib/query/embed.ts` uses
`@huggingface/transformers` (the maintained successor to `@xenova/
transformers`) running `Xenova/all-MiniLM-L6-v2` — the ONNX build of the
exact model used at ingestion time. Verified numerically equivalent to the
Python `sentence-transformers` output (see the note at the top of this
document); no re-embedding or
re-ingestion of the corpus was needed. Runs server-side only (the
~1MB/236KB-gzip dependency is in the server bundle, confirmed absent from
the client bundle by `npm run build`'s output).

**Auth: temporary test-student scaffolding.** There is no login flow
anywhere in the app yet (`tasks-done.md` §1.1: "Authentication — Not
started"; README: *"Auth is simulated; no credentials are verified"*), so
a browser request never carries a real bearer token and
`getSupabaseForRequest` always returns `null` for the chat panel today.
Without something else, the chat could only ever exercise demo mode.
`src/lib/chat-api.ts`'s `getTestStudentClient()` signs in as the
already-provisioned test student (`scripts/create_test_students.py`) with
a real password grant so the router can be exercised against live data.
This is **not** a client-identity shortcut — the browser never supplies or
influences who this resolves to, and every downstream call still goes
through the same RLS / `orion_resolve_user` path a real logged-in user
would use — but it is a stand-in that must be replaced once real
authentication exists. Every response is flagged (`usedTestStudent: true`)
and the chat UI renders an explicit "test student session" badge so this
is never mistaken for a real user's personalized answer, matching the
existing demo-mode transparency rule (CLAUDE.md/README: demo data must be
clearly distinguishable from real data).

**Verified live in a real browser** (Playwright, headless Chromium,
`npm run dev`, all three required queries sent through the actual UI):
all three cases rendered the correct route badge, the "test student
session" badge, the correct facts/snippets/citations, and the honest
office-hours warnings — matching the backend verification in §6 exactly.
Zero browser console errors, zero failed network requests (`>=400`)
observed across all three exchanges.

**Not done in this pass:** wiring a real per-student cohort into
`semanticSearch`'s filters (same gap as the Python layer, §8);
rendering the route badge conditionally hidden once real generation exists
(it's a debug/testing aid, not intended as permanent UI); no loading
skeleton beyond the existing typing-indicator dots.

## 8. Known limitations (not fixed in this slice — documented, not hidden)

- **Cohort filtering isn't auto-applied.** `semantic_search` accepts a
  cohort filter but nothing calls it yet — a real per-student endpoint must
  pass the student's own cohort explicitly before this is safe to expose
  as "the" answer to a cohort-sensitive question (CLAUDE.md §20).
- **Embedding model.** Gemini `gemini-embedding-2` (768-dim) since
  2026-09-22; the faculty `min_similarity` constant (`FACULTY_MIN_SIMILARITY`
  in `retrieval.py`) was recalibrated for it — Gemini cosine scores for
  unrelated text sit far higher than MiniLM's. Revisit if the model changes.
- **No reranking.** Retrieval is single-pass cosine similarity; README §9's
  "reranking if required" step doesn't exist yet.
- **No LLM/generation.** This entire layer stops at `GroundedContext` —
  turning that into a natural-language answer (with citation rendering,
  grounding validation, and an actual Gemini call) is the next slice.
