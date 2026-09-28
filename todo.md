# Gemini embeddings — TODO

Status as of 2026-09-23 (backfill finished this session). Full runbook: docs/embeddings.md.

- Code, schema, tests: done.
- **Backfill: complete.** 1,269 / 1,269 chunks and 146 / 146 faculty rows embedded (`embedding_gemini`, `faculty.research_embedding`), verified by direct SQL (`missing = 0`, `wrong_dim = 0` on both tables).
- `scripts/eval_retrieval.py --k 3 --faculty`: keyword hit@3 gemini 12/12 · minilm 11/12. `FACULTY_MIN_SIMILARITY` recalibrated 0.60 → **0.65**(`backend/query/retrieval.py`) from real scores on the full corpus.
- Answer quality was never blocked on this — since 2026-09-22/23 ORION answers regulation/hostel/faculty-research questions from Postgres full-text search (`search_document_chunks`, `backend/query/documents.py`, `backend/query/campus.py`), not from these embeddings. The vector path is now a second, ranked signal alongside it — see `production-tasks.md` and `docs/query-router.md` for the current architecture.

---

## A. Deploy on Render — done, verified live 2026-09-23

Completed and verified in the 2026-09-22/23 sessions (`production-tasks.md` §5, `AI-task-results.md`, `scripts/smoke_live.py`). Checklist below kept for the record.

- [x] Render service created from `render.yaml` (`srv-dap4h48ae00c73921ee0`, live at `https://orion-campus-nest.onrender.com`).

- [x] Secret env vars set (`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GOOGLE_CLIENT_ID`/`SECRET`, `FRONTEND_ORIGIN`, `API_BASE_URL`) — confirmed working via live login-independent checks (see below); `SUPABASE_SECRET_KEY` intentionally not set.

- [x] `ORION_EMBEDDING_PROVIDER=gemini` (not `minilm`) — confirmed live: the deployed `requirements.txt` has no `torch`/`sentence-transformers`.

- [x] `GET /health` → `200 {"status":"ok","commit":"12d66a8"}` — matches `main` HEAD, confirmed 2026-09-23. `/health` now reports the deployed commit (`RENDER_GIT_COMMIT`), so this check no longer requires guessing.

- [x] Protected route without a cookie → `401` (checked `/calendar` live).

- [x] Structured question needs no Gemini call: confirmed via the full `AI-task.md` run and the live smoke test (`next_class`, `mess_today`, etc. all answer with `answer_source: composer`, no LLM call).

- [x] Semantic question on an embedded document returns snippets: live- checked 2026-09-23, "Which course covers reinforcement learning?" → quotes *B.Tech CSE Curriculum (2021-25 batch)* correctly (full-text search, not embeddings — see the status note above).

- [x] Cold start measured: \~40s on the free plan (`production-tasks.md` §6). Needs a person to decide on an always-on plan or an uptime ping if this matters for real students — not something to silently upgrade to a paid plan.

- [x] Gemini-failure degrade behavior: covered by `tests/test_ai_router.py`'s parametrized failure tests (7 exception types → 200 with a fallback, never a 500) instead of toggling the production key by hand.

- [ ] **Still open, needs a person — do not silently change:** cross-domain cookies. Frontend (`*.vercel.app`) and API (`*.onrender.com`) are different sites; `SameSite=Lax` (the current default) will not send the session cookie on the frontend's cross-site calls, so real browser login will not work as deployed even though every API check above passes with a manually-set cookie. `render.yaml`'s own comment and `docs/backend-requirements.md` §7 lay out the two fixes (`COOKIE_SAMESITE=none` + `Secure`, or one shared custom domain) — this is a security-relevant choice left for you to make explicitly.

Live latency: `/ai/ask` median **2.45s** as of the round-trip-reduction fix (2026-09-23) — up from \~175ms locally because the API (Oregon) and Supabase (ap-south-1) are in different regions. See `production-tasks.md` §6.

---

## B. Gemini embedding backfill — done 2026-09-23

```
$ .venv/bin/python scripts/reembed_gemini.py --target all
[documents] done this run: embedded 277, skipped empty 0, failed 0; remaining 0
[faculty] done this run: embedded 146, skipped empty 0, failed 0; remaining 0
Migration complete.
```

A few 429s hit mid-run (the daily embedding quota was still recovering) but the script's backoff/retry absorbed all of them — 0 failed rows.

- [x] `.venv/bin/python scripts/reembed_gemini.py --target all` — complete.

- [x] Verified in SQL — `missing = 0` and `wrong_dim = 0` on both `document_chunks.embedding_gemini` and `faculty.research_embedding`.

- [x] `.venv/bin/python scripts/eval_retrieval.py --k 3 --faculty` — Gemini 12/12 hit@3 vs. MiniLM 11/12. Recorded in `docs/embeddings.md`.

- [x] Recalibrated `FACULTY_MIN_SIMILARITY` in `backend/query/retrieval.py`: 0.60 → 0.65 (junk-topic ceiling 0.630, real matches 0.677–0.836).

- [x] Locally, `ORION_EMBEDDING_PROVIDER=minilm` was not set in `.env` — nothing to remove.

- [x] `docs/embeddings.md` Status section updated to "complete".

- [x] **Decided 2026-09-28: hybrid** — `documents.search()` fuses full-text with vector search (`search_document_chunks_semantic`) and uses vector similarity as a relevance check before quoting. See `docs/embeddings.md` and `docs/query-router.md`.

- [ ] Run backend tests + typecheck/build and commit the `FACULTY_MIN_SIMILARITY` change and doc updates (not yet committed as of this writing).

## C. Later (only after B's routing decision above is made)

- [ ] Decide on Gemini billing — **now relevant**: every document question not already in the in-process cache costs one embedding call, and the free tier allows ~1000/day. Past the quota, vector search pauses itself and answers fall back to full-text only (still correct, less good at word-only false matches).

- [ ] Write a migration dropping the MiniLM rollback path: `document_chunks.embedding`, `chunks_embedding_hnsw_idx`, `match_document_chunks`.

- [ ] Delete `backend/requirements-minilm-rollback.txt` and the `minilm`branches in `retrieval.py`.

- [ ] Optional: remove the unused `@huggingface/transformers` dependency from `package.json`.