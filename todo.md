# Gemini embeddings — TODO

Status as of 2026-09-23. Full runbook: docs/embeddings.md.

- Code, schema, tests: done.
- Backfill: **992 / 1,269 chunks** and **0 / 146 faculty** rows embedded.
  Unchanged since 2026-09-22 — see the quota check below.
- **This no longer blocks answer quality.** As of 2026-09-22/23, ORION
  answers regulation/hostel/faculty-research questions from Postgres
  full-text search (`search_document_chunks`, `backend/query/documents.py`,
  `backend/query/campus.py`), not from these embeddings. The backfill below
  is now a **quality improvement for semantic ranking**, not a blocker —
  see `production-tasks.md` and `docs/query-router.md` for the current
  architecture.

---

## A. Deploy on Render — done, verified live 2026-09-23

Completed and verified in the 2026-09-22/23 sessions
(`production-tasks.md` §5, `AI-task-results.md`, `scripts/smoke_live.py`).
Checklist below kept for the record.

- [x] Render service created from `render.yaml` (`srv-dap4h48ae00c73921ee0`,
  live at `https://orion-campus-nest.onrender.com`).
- [x] Secret env vars set (`GEMINI_API_KEY`, `SUPABASE_URL`,
  `SUPABASE_ANON_KEY`, `GOOGLE_CLIENT_ID`/`SECRET`, `FRONTEND_ORIGIN`,
  `API_BASE_URL`) — confirmed working via live login-independent checks
  (see below); `SUPABASE_SECRET_KEY` intentionally not set.
- [x] `ORION_EMBEDDING_PROVIDER=gemini` (not `minilm`) — confirmed live: the
  deployed `requirements.txt` has no `torch`/`sentence-transformers`.
- [x] `GET /health` → `200 {"status":"ok","commit":"12d66a8"}` — matches
  `main` HEAD, confirmed 2026-09-23. `/health` now reports the deployed
  commit (`RENDER_GIT_COMMIT`), so this check no longer requires guessing.
- [x] Protected route without a cookie → `401` (checked `/calendar` live).
- [x] Structured question needs no Gemini call: confirmed via the full
  `AI-task.md` run and the live smoke test (`next_class`, `mess_today`,
  etc. all answer with `answer_source: composer`, no LLM call).
- [x] Semantic question on an embedded document returns snippets: live-
  checked 2026-09-23, "Which course covers reinforcement learning?" →
  quotes *B.Tech CSE Curriculum (2021-25 batch)* correctly (full-text
  search, not embeddings — see the status note above).
- [x] Cold start measured: ~40s on the free plan (`production-tasks.md` §6).
  Needs a person to decide on an always-on plan or an uptime ping if this
  matters for real students — not something to silently upgrade to a paid
  plan.
- [x] Gemini-failure degrade behavior: covered by
  `tests/test_ai_router.py`'s parametrized failure tests (7 exception types
  → 200 with a fallback, never a 500) instead of toggling the production
  key by hand.
- [ ] **Still open, needs a person — do not silently change:** cross-domain
  cookies. Frontend (`*.vercel.app`) and API (`*.onrender.com`) are
  different sites; `SameSite=Lax` (the current default) will not send the
  session cookie on the frontend's cross-site calls, so real browser login
  will not work as deployed even though every API check above passes with
  a manually-set cookie. `render.yaml`'s own comment and
  `docs/backend-requirements.md` §7 lay out the two fixes
  (`COOKIE_SAMESITE=none` + `Secure`, or one shared custom domain) — this
  is a security-relevant choice left for you to make explicitly.

Live latency: `/ai/ask` median **2.45s** as of the round-trip-reduction fix
(2026-09-23) — up from ~175ms locally because the API (Oregon) and Supabase
(ap-south-1) are in different regions. See `production-tasks.md` §6.

---

## B. Gemini embedding backfill — still blocked on quota (checked 2026-09-23)

Verified directly against the live API today, not assumed:

```
$ .venv/bin/python scripts/reembed_gemini.py --dry-run
[documents] 1269 rows · already migrated 992 · remaining 277
[faculty] 146 rows · already migrated 0 · remaining 146
```

A direct `embed_query()` probe returned a 429 with:

```
quotaId: "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier"
quotaMetric: generativelanguage.googleapis.com/embed_content_free_tier_requests
quotaValue: "1000"
```

**This is the embedding quota specifically, and it is still exhausted right
now.** It is a separate metric from the generation quota
(`generateContent`), which *has* recovered — confirmed by a direct
`llm_client.generate()` call succeeding today. That's likely why it looked
like "the Gemini limit reset": one of the two limits genuinely did.

Free-tier daily quotas reset once every 24 hours from when they were first
exhausted, not at a fixed clock time shared across metrics — retry later
today or tomorrow and re-run the dry-run above to check.

When it's actually available, the steps are unchanged:

- [ ] `.venv/bin/python scripts/reembed_gemini.py --dry-run` — re-confirm
  before spending quota.
- [ ] `.venv/bin/python scripts/reembed_gemini.py --target all`
  - Takes about 5 min. Resumes on a 429 instead of restarting.
  - Should end with `Migration complete.`
- [ ] Verify in SQL — expect `missing = 0` and `wrong_dim = 0`:

  ```sql
  select count(*) total, count(embedding_gemini) gemini,
         count(*) filter (where embedding_gemini is null) missing,
         count(*) filter (where vector_dims(embedding_gemini) <> 768) wrong_dim
  from document_chunks;

  select count(*) filter (where research_interests is not null and research_interests <> '') with_text,
         count(research_embedding) embedded,
         count(*) filter (where vector_dims(research_embedding) <> 768) wrong_dim
  from faculty;
  ```

- [ ] `.venv/bin/python scripts/eval_retrieval.py --k 3 --faculty` — Gemini
  should match or beat MiniLM on keyword hit@3; read the top hits, don't
  trust the score alone. Record the result in `docs/embeddings.md`.
- [ ] Recalibrate `FACULTY_MIN_SIMILARITY` in `backend/query/retrieval.py`
  (currently a provisional 0.60 from one probe) using the `--faculty`
  output: a value between real matches (NLP, computer vision) and a junk
  topic ("cooking recipes").
- [ ] Once embedded, the vector path (`retrieval.semantic_search`,
  `faculty_topic_and_schedule`) becomes a second, ranked signal alongside
  the full-text search that already answers these questions — not a
  prerequisite for them to work at all any more. Compare the two before
  deciding whether/how to combine them.
- [ ] Locally, remove `ORION_EMBEDDING_PROVIDER=minilm` from `.env` if set.
- [ ] Update the Status section of `docs/embeddings.md` and this file to
  say "complete".
- [ ] Commit the migration work.

## C. Later (only after B is validated in production)

- [ ] Decide on Gemini billing — the free tier's daily quota is shared
  between the backfill and real embedding calls, once anything depends on
  them again.
- [ ] Write a migration dropping the MiniLM rollback path:
  `document_chunks.embedding`, `chunks_embedding_hnsw_idx`,
  `match_document_chunks`.
- [ ] Delete `backend/requirements-minilm-rollback.txt` and the `minilm`
  branches in `retrieval.py`.
- [ ] Optional: remove the unused `@huggingface/transformers` dependency
  from `package.json`.
