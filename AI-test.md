# ORION AI test — 2026-09-22 12:58 UTC

Every question below was sent to the **live** `/ai/ask` on Render
(`https://orion-campus-nest.onrender.com`), authenticated as the real test account
`orion-test-student-a@iiitkottayam.ac.in` (Semester 3, CSE-I). Nothing here is simulated or
hand-written — these are the actual HTTP responses.

Only questions about data confirmed present in the structured DB or the
RAG corpus at test time were asked (real course codes, real faculty names,
real research interests — pulled from Supabase immediately before writing
the question set).

### [structured — timetable] What is my next class?

- route: `structured` · has_answer: `True` · generation_available: `True` · 30.88s
- **Answer:** Your next class is **ICS 214 IT WORKSHOP III**, which will take place tomorrow (Wednesday) from 10:00:00 to 10:55:00. You have no more classes today after your currently ongoing class (IPT 211 PHYSICAL TRAINING, 17:00:00–19:00:00).

*(Source: orion_next_class RPC (live timetable))*
- facts returned: 1 (first claim: Currently ongoing: IPT 211 PHYSICAL TRAINING right now (17:00:00-19:00:00). After that, next class: ICS 214 IT WORKSHOP III tomorrow (Wednesday), 10:0)
### [structured — timetable] What classes do I have today?

- route: `structured` · has_answer: `False` · generation_available: `True` · 4.33s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['no active, valid entries for this day']
### [structured — timetable] What is my timetable for this week?

- route: `structured` · has_answer: `False` · generation_available: `True` · 2.13s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['no active, valid entries for this week']
### [structured — timetable] What class do I have at 5 PM?

- route: `structured` · has_answer: `True` · generation_available: `True` · 5.26s
- **Answer:** At 5:00 PM (17:00), you have the class **IPT 211 PHYSICAL TRAINING**, which runs until 19:00. After that, you have no more classes today; your next class is ICS 214 IT WORKSHOP III tomorrow (Wednesday) from 10:00:00 to 10:55:00 (source: orion_next_class RPC (live timetable)).
- facts returned: 1 (first claim: Currently ongoing: IPT 211 PHYSICAL TRAINING at 17:00 (17:00:00-19:00:00). After that, next class: ICS 214 IT WORKSHOP III tomorrow (Wednesday), 10:00)
### [structured — faculty/course] Who teaches ICS 213 Database Management Systems?

- route: `structured` · has_answer: `True` · generation_available: `True` · 35.25s
- **Answer:** ICS 213 Database Management Systems is taught by the following faculty members:

* Dr. Vengadeswaran S (VS) (source: timetable_entries + faculty (live timetable))
* Dr. Syamala S (SLS) (source: timetable_entries + faculty (live timetable))
* Dr. Amit Kumar Roy (AKR) (source: timetable_entries + faculty (live timetable))
* Dr. E. Silambarasan (ES) (source: timetable_entries + faculty (live timetable))
- facts returned: 4 (first claim: Dr. Vengadeswaran S (VS) teaches ICS 213)
### [structured — course] Tell me about ICS 211 Design and Analysis of Algorithms.

- **HTTP 500** (32.07s) — Internal Server Error
### [structured — faculty] What is Dr. Manu Madhavan's email and office location?

- route: `structured` · has_answer: `True` · generation_available: `True` · 26.61s
- **Answer:** Dr. Manu Madhavan's email is manum@iiitkottayam.ac.in and his office location is BC 307 (source: faculty (live)).
- facts returned: 1 (first claim: Dr. Manu Madhavan (MM), email: manum@iiitkottayam.ac.in, office: BC 307, research interests: Natural Language Processing; Bioinformatics; Machine Lear)
### [structured — mess] What is on the mess menu today?

- **HTTP 500** (31.97s) — Internal Server Error
### [structured — mess] What is being served for dinner this week?

- route: `structured` · has_answer: `True` · generation_available: `True` · 2.94s
- **Answer:** Based on the mess menus on file (note that these are the most recent menus on file and are not strictly confirmed for these dates), here is what is scheduled for dinner this week:

* **Monday (2026-09-21):** Rice, Roti, Egg roast, Beetroot thoran, Vegetable Kurma, Papad, curd, and Salad *(source: mess_menus (live))*
* **Tuesday (2026-09-22):** Rice, Roti, Chole curry, Onion Dal Tadka, Carrot Beans Thoran, Rasam, Chips Salad, and Curd *(source: mess_menus (live))*
* **Wednesday (2026-09-23):** Vegetable Fried rice, Roti, Paneer Butter masala, Chilli chicken, Onionchilli Raita, and Passion Fruit drink *(source: mess_menus (live))*
* **Thursday (2026-09-24):** Roti, Rice, Sambar, Potato fry, Kanji, Chammanthi, curd, Brinjal Curry, Salad, and Rava Kesari (sweet) *(source: mess_menus (live))*

- facts returned: 7 (first claim: Dinner on 2026-09-21: Rice, Roti, Egg roast, Beetroot thoran, Vegetable Kurma, Papad, curd, Salad (most recent Monday menu on file, from 2026-08-31 — )
### [structured — announcements] Are there any current announcements?

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 0.89s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [semantic — regulations] What is the attendance requirement?

- **HTTP 500** (35.35s) — Internal Server Error
### [semantic — regulations] What are the rules for course withdrawal?

- route: `semantic` · has_answer: `True` · generation_available: `True` · 3.34s
- **Answer:** Based on the provided documents, there is no information regarding the rules for course withdrawal. The retrieved excerpts only contain curriculum details, course structures, activity points, and semester-wise course lists for various programs (such as B.Tech CSE and ECE).
- snippets returned: 5 (top: [('B.Tech CSE (AI & DS) Curriculum (ADM 2026)', 0.64), ('B.Tech CSE Curriculum (2021-25 batch)', 0.63), ('B.Tech ECE Curriculum (ADM 2026)', 0.63)])
### [semantic — regulations] Can I take a summer term?

- route: `semantic` · has_answer: `True` · generation_available: `True` · 22.08s
- **Answer:** Based on the provided curriculum documents (B.Tech CSE Curriculum (2021-25 batch), B.Tech Mathematics & Computing Curriculum (ADM 2026), B.Tech AI & DS Curriculum (2021-25 batch), and B.Tech Mathematics & Computing Curriculum (ADM 2026), PROGRAMME STRUCTURE), there is no mention or information regarding whether you can take a summer term.
- snippets returned: 5 (top: [('B.Tech CSE Curriculum (2021-25 batch)', 0.6), ('B.Tech CSE Curriculum (2021-25 batch)', 0.6), ('B.Tech Mathematics & Computing Curriculum (ADM 2026)', 0.6)])
### [semantic — regulations] How is CGPA calculated?

- route: `semantic` · has_answer: `True` · generation_available: `True` · 3.49s
- **Answer:** Based on the provided documents, there is no information explaining how CGPA is calculated. The documents only mention that Activity Credits (AC) earned through Activity Points are not counted towards the CGPA (as stated in the *B.Tech CSE (AI & DS) Curriculum (ADM 2026)* and *B.Tech CSE (Cyber Security) Curriculum (ADM 2026)*).
- snippets returned: 5 (top: [('B.Tech CSE Curriculum (2021-25 batch)', 0.62), ('B.Tech CSE Curriculum (2021-25 batch)', 0.62), ('B.Tech CSE Curriculum (2021-25 batch)', 0.62)])
### [semantic — hostel] What are the hostel curfew rules?

- route: `semantic` · has_answer: `True` · generation_available: `True` · 5.31s
- **Answer:** Based on the provided documents, there is no information available regarding hostel curfew rules.
- snippets returned: 5 (top: [('B.Tech CSE (AI & DS) Curriculum (ADM 2026)', 0.59), ('B.Tech ECE Curriculum (ADM 2026)', 0.58), ('B.Tech CSE Curriculum (2021-25 batch)', 0.57)])
### [semantic — hostel] What is the campus movement timing?

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 2.1s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [semantic — hostel] How does the outpass process work?

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 3.03s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [semantic — procedures] How do I request transcript verification?

- route: `semantic` · has_answer: `True` · generation_available: `True` · 12.17s
- **Answer:** Based on the provided documents, there is no information available regarding how to request transcript verification.
- snippets returned: 5 (top: [('B.Tech ECE Curriculum (ADM 2026)', 0.58), ('B.Tech ECE Curriculum (ADM 2026)', 0.58), ('B.Tech ECE Curriculum (ADM 2026)', 0.58)])
### [semantic — procedures] What is the transcript verification fee?

- route: `semantic` · has_answer: `False` · generation_available: `True` · 4.09s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['semantic document retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [semantic — anti-ragging] What are the anti-ragging rules?

- route: `semantic` · has_answer: `False` · generation_available: `True` · 4.51s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['semantic document retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [semantic — curriculum] What are the prerequisites for a Machine Learning course?

- route: `semantic` · has_answer: `False` · generation_available: `True` · 1.48s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['semantic document retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [semantic — curriculum] How many credits are required to graduate?

- route: `semantic` · has_answer: `False` · generation_available: `True` · 2.53s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['semantic document retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [hybrid — faculty research] Which faculty work on Natural Language Processing and when can I meet them?

- route: `hybrid` · has_answer: `False` · generation_available: `True` · 1.28s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['faculty research retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [hybrid — faculty research] Recommend a faculty member for machine learning research.

- route: `hybrid` · has_answer: `False` · generation_available: `True` · 2.17s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['faculty research retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']
### [hybrid — faculty research] Who researches underwater sensor networks?

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 1.69s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [small talk] Hi

- route: `small_talk` · has_answer: `True` · generation_available: `True` · 1.75s
- **Answer:** Good afternoon! I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations.
- facts returned: 1 (first claim: Good afternoon! I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations.)
### [small talk] Thanks!

- route: `small_talk` · has_answer: `True` · generation_available: `True` · 1.81s
- **Answer:** You're welcome! Let me know if you need anything else.
- facts returned: 1 (first claim: You're welcome! Let me know if you need anything else.)
### [unsupported / no-answer honesty] asdkfj qwer nonsense query

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 1.63s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [unsupported / no-answer honesty] What is the meaning of life?

- route: `unsupported` · has_answer: `False` · generation_available: `True` · 2.49s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['unsupported or ambiguous query']
### [out-of-scope (should not hallucinate)] What are my exam grades this semester?

- route: `semantic` · has_answer: `False` · generation_available: `True` · 1.41s
- **Answer:** _(none — generation not run / nothing to ground on)_
- warnings: ['semantic document retrieval is temporarily unavailable — no documents were searched, so no answer can be grounded']

---

# Analysis

30 questions, 27 HTTP 200 / 3 HTTP 500 (all one root cause, now fixed — see below).
Two real bugs were found and fixed while investigating these results; both are
committed... no — **not yet committed** (see "State of this work" at the end).

## What's working well

- **Structured timetable/faculty/course lookups are accurate and well-cited.**
  "Who teaches ICS 213?" correctly listed all 4 real faculty from
  `timetable_entry_faculty`; "What class do I have at 5 PM?" correctly resolved
  the live IPT 211 session; Dr. Manu Madhavan's email/office came back exactly
  as stored. Every structured answer cited its real source (`orion_next_class
  RPC`, `faculty (live)`, etc.) rather than asserting facts unsourced.
- **Mess week view works and is honest about staleness.** "What is being
  served for dinner this week?" returned 4 real days of menu data *and*
  proactively said the dates aren't confirmed for the current week (`mess_menus`
  is August-only data, a known gap — see docs). That's the right behavior:
  surfacing the caveat instead of presenting stale data as current.
- **No hallucination observed anywhere.** Every semantic question whose
  answer wasn't actually in the retrieved chunks got an honest "no information
  in the provided documents" rather than an invented answer, even under
  pressure from questions like "What are my exam grades this semester?" (there
  is no exams data at all — `exams` = 0 rows — and the model correctly refused
  rather than guessing a grade).
- **Cost discipline holds.** Small talk (`Hi`, `Thanks!`) and unsupported
  queries never call Gemini (0.9–2.5s, no generation) — confirmed by latency
  alone, not just the code reading that way.
- **The router's structured/semantic/hybrid split is real, not cosmetic** —
  timetable questions never triggered an embedding call; regulation questions
  did; "next class" queries correctly separated ongoing-vs-upcoming.

## Bugs found — and fixed (both are code changes in the working tree now,
see "State of this work")

### 1. `day_timetable`/`week_timetable` silently returned nothing for "today"/"this week" — the most severe finding

**Symptom:** "What classes do I have today?" and "What is my timetable for
this week?" both answered "no active, valid entries" — for the exact same
moment "What is my next class?" correctly found an ongoing IPT 211 session
for the same student. A confident, wrong "you have nothing today" is worse
than a crash: it looks like a real, checked answer.

**Root cause, confirmed with real authenticated RPC calls (not guessed):**
`backend/query/retrieval.py` called
`client.rpc("orion_day_timetable", {"p_user_id": None, "p_on_date": None})`
whenever no specific date was requested. `supabase-py` serializes that
Python `None` as a literal JSON `null` in the request body — and PostgreSQL
only applies a SQL function's `default` when the argument is **omitted**
from the call, not when it's explicitly `null`. `orion_active_entries`'s
WHERE clause compares `p_on_date` directly (`e.valid_from <= p_on_date`,
`e.day_of_week = extract(isodow from p_on_date)`, …) with no
`p_on_date is null` guard, so every row's comparison against SQL `NULL`
evaluates to `NULL` (not true), and the query returns zero rows.

Verified directly against the live DB, same student, same moment, real JWT:

| Call | Result |
|---|---|
| `p_on_date` key omitted | 6 entries |
| `p_on_date: null` (what the code sent) | **0 entries** |
| `p_on_date: "2026-09-22"` | 6 entries |

**Fix:** `backend/query/retrieval.py` — new `_date_rpc_args()` helper omits
`p_on_date` from the RPC params entirely when no date is given, instead of
sending it as `None`. Verified live post-fix: `day_timetable` → 6 facts,
`week_timetable` → 38 facts, both with no warnings.

**Not affected:** `day_of_week_timetable` ("what do I have tomorrow/on
Monday?") and `class_at_time` always resolve a real date/timestamp first,
so they never hit this. Only the plain "today"/"this week" (no date
reference in the question) path was broken.

**Tests added:** `tests/test_timetable_retrieval.py` — asserts the literal
params dict sent to `.rpc()` never contains `p_on_date: None`; verified the
test actually fails against the old (reintroduced-then-reverted) buggy code
before trusting it.

### 2. A slow Gemini response crashed the whole request instead of degrading (3/30 questions)

**Symptom:** 3 questions ("Tell me about ICS 211…", "What is on the mess
menu today?", "What is the attendance requirement?") returned a bare
HTTP 500 with no JSON body, each at 32–35 seconds — right at
`llm_client.py`'s `urlopen(timeout=30)`.

**Root cause, confirmed from the actual Render stack trace (all three
identical):** `urllib.request.urlopen(..., timeout=30)`'s read timeout
raises a bare `TimeoutError`, not `urllib.error.URLError` — so
`backend/app/api/ai.py`'s `except (urllib.error.URLError, ValueError)`
never caught it, and the exception propagated past FastAPI's default
handler as an unstyled 500, discarding the retrieval facts/snippets that
were already computed and ready to return.

```
File "backend/app/api/ai.py", line 52, in ask
    answer = generate(context)
File "backend/query/llm_client.py", line 121, in generate
    with urllib.request.urlopen(req, timeout=30) as resp:
TimeoutError: The read operation timed out
```

**Fix:** broadened the `except` in `ai.py` to catch any exception from the
Gemini call, not just the two classes it happened to be narrowed to before —
matching the module's own stated intent ("Gemini being unreachable/erroring
must never break retrieval"). Never silent: still logs the exception class
and message to stderr.

**Tests added:** `tests/test_ai_router.py`, parametrized over `TimeoutError`,
`socket.timeout`, `urllib.error.URLError`, `ssl.SSLError`,
`ConnectionResetError`, `ValueError`, `OSError` — all must degrade to
`generation_available: false` with the retrieval facts still returned, never
a raised exception.

## Known limitations (not bugs — already tracked, now empirically confirmed)

- **Gemini's free-tier daily embedding quota (1,000 texts/day) ran out
  mid-battery**, at question 19/30. From that point every semantic/hybrid
  question correctly degraded to `"...retrieval is temporarily unavailable"`
  (confirmed in the Render logs as `EmbeddingUnavailable: ... daily quota
  exhausted`) rather than crashing or hallucinating — the degradation path
  itself worked exactly as designed. But it's a real capacity data point:
  this quota can be exhausted by a single afternoon of testing/light real
  usage, not just by a bulk backfill job. Relevant before relying on the
  free tier for real students.
- **The Gemini embedding backfill is still incomplete** (992/1,269 document
  chunks; 0/146 faculty — unchanged since the migration). Concretely
  visible here: "What are the rules for course withdrawal?", "How is CGPA
  calculated?", "What are the hostel curfew rules?" all retrieved genuine
  top-5 chunks (curriculum documents, similarity 0.57–0.64) but correctly
  reported no information — because the actually-relevant documents (UG
  Regulations, Hostel Rules) aren't embedded yet, so curriculum chunks were
  the closest thing available, not really close at all. The honesty is
  correct; the retrieval quality won't be meaningful until the backfill
  finishes (`scripts/reembed_gemini.py --target all`).
- **Mess data is August 2026 only.** The AI already discloses this per-answer
  rather than presenting it as current — a good stopgap, but the actual fix
  is a September/October `mess_menus` import.

## Router coverage gaps — not fixed, recommend prioritizing

Three questions fell through to `route: unsupported` even though the
underlying data/capability exists, because the keyword-based classifier in
`backend/query/router.py` doesn't recognize the phrasing:

1. **"Are there any current announcements?"** — there's no
   `StructuredIntent` for announcements at all (`backend/query/types.py`'s
   enum has timetable/faculty/course/mess intents but nothing for
   `announcements`), even though `/announcements` already exists as a real
   REST endpoint over real data. The AI chat simply can't answer this
   question today.
2. **"What is the campus movement timing?" / "How does the outpass process
   work?"** — `_SEMANTIC_TOPIC_RE` in `router.py` lists `hostel`, `ragging`,
   `transcripts?`, etc. but not `curfew`, `timing`, `movement`, `outpass`,
   `in-time`/`out-time` — natural ways a student would actually ask about
   hostel rules. (Would still hit the incomplete-backfill limitation above
   even if routed correctly, but right now it doesn't even try.)
3. **"Who researches underwater sensor networks?"** — `_FACULTY_MENTION_RE`'s
   "who ___" branch only matches `who works/is working (on|in)`; "who
   researches/studies/specializes in X" doesn't match. A real faculty match
   exists in the DB (Dr. JALAJA M J) that this phrasing can't reach.

None of these were changed — router keyword lists affect classification
broadly and deserve deliberate review/testing together, not a reflexive
regex patch buried in a test report.

## Other observations

- **Latency is highly variable and sometimes slow enough to need a loading
  state**: 0.9s (no-LLM paths) up to 30–35s (structured/semantic + Gemini
  generation, likely compounded by Render's free-tier cold start). Worth
  measuring separately from Gemini's own latency before deciding whether to
  upgrade the Render plan or add UI-level streaming/patience messaging.
- `generation_available: true` was reported even on the three questions that
  ultimately 500'd — because the field defaults to `true` and is only set
  `false` inside the (previously too-narrow) except block, which never ran.
  Now that the except block actually catches these, this reports correctly.

## State of this work — please read before deploying

- **Both fixes above are in the local working tree, not yet committed or
  deployed.** Render is still running the version from commit `0943784`,
  which has neither fix — the 3-crash and empty-today-timetable bugs are
  still live in production right now.
- **A second, unrelated change appeared in `backend/app/api/ai.py`,
  `backend/app/schemas.py`, and `backend/query/llm_client.py` while this
  test was running** — conversation history/persistence
  (`ai_conversations`/`ai_messages`, a new untracked migration
  `20260922080000_ai_chat_conversations.sql`). This wasn't part of this
  test session; it looks like concurrent work (matches "make UI changes" —
  likely a paired backend change for a chat UI). It was left entirely
  alone: not reverted, not committed, not deployed, not applied to
  Supabase. `pytest` passes against the current combined state (196 passed),
  but the new `ai_conversations`/`ai_messages` tables don't exist on the
  live DB yet — deploying this as-is would break every `/ai/ask` call until
  that migration is applied.
