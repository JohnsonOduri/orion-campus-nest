# Gemini embeddings — TODO

Status as of 2026-09-22. Full runbook: docs/embeddings.md.

- Code, schema, tests: done.
- Backfill: **992 / 1,269 chunks** and **0 / 146 faculty** rows embedded. It stopped on the free-tier daily cap (1,000 texts/day).
- Still missing: both UG Regulations, Hostel Rules, Transcript and Certificate Verification, the three anti-ragging documents, and the 2021-25 Cyber Security and ECE curricula (plus 3 chunks of the 2021-25 AI&DS curriculum).

---

## A. Test now by deploying on Render (already done, needs verifying)

### Render setup

- [ ] Create a Web Service from this repo:

  - Build command: `pip install -r backend/requirements.txt`
  - Start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`

- [ ] Set env var `PYTHON_VERSION=3.13` (the version tested locally).

- [ ] Add env vars (secret values set in Render only, never committed):

  - `GEMINI_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `FRONTEND_ORIGIN`
  - `API_BASE_URL`
  - `COOKIE_SECURE=true`

- [ ] Do **not** set `SUPABASE_SECRET_KEY` on the API service. The API never needs it.

- [ ] Do **not** set `ORION_EMBEDDING_PROVIDER=minilm` on Render. The Render build has no torch/sentence-transformers installed, so the MiniLM path cannot run there. Render runs on Gemini, with the partial data described above.

### Things to check

- [ ] The build log has no `torch` / `sentence-transformers` and the build is fast. Locally the dependencies take 127 MB (they were 1.1 GB before).

- [ ] `GET /health` returns 200.

- [ ] Memory in the Render dashboard stays well under 512 MB (about 86 MB locally).

- [ ] Cold start: after the free instance spins down, the first request should not take 10+ s for the embedding model. The old version loaded torch on first use.

- [ ] **Structured** question works and makes no Gemini call: "What classes do I have today?"

- [ ] **Semantic** question on an already-embedded document returns snippets: "Which course covers reinforcement learning?" (ADM 2026 curricula are embedded).

- [ ] **Expected gaps until part B is done** (not bugs):

  - "What is the attendance requirement?" or "What are the hostel curfew rules?" find nothing.
  - "Which faculty work on NLP?" returns no faculty match.

- [ ] Note the `/ai/ask` latency for a semantic question. Expect about +0.6–0.9 s for the embedding call. Structured questions should be unaffected.

- [ ] Optional degrade test:

  1. Temporarily blank `GEMINI_API_KEY` in Render.
  2. Ask a semantic question and check for a 200 response with a "temporarily unavailable" warning, not a 500.
  3. Structured questions should still answer.
  4. Restore the key.

- [ ] Cookie check before testing login: `SameSite=Lax` needs the frontend and API on the same site. Two different `*.onrender.com` subdomains are likely treated as different sites, so use a custom domain or serve both from one origin (see `docs/backend-requirements.md`).

> Every test question uses the same Gemini quota (100/min, 1,000/day) as the backfill. Keep deployment testing light on the day you run part B.

---

## B. When the Gemini quota resets (not done yet)

About 423 texts plus about 20 for the evaluation, which fits in one day's quota.

- [ ] `.venv/bin/python scripts/reembed_gemini.py --dry-run`

  - Expect about 277 chunks and 146 faculty rows remaining.

- [ ] `.venv/bin/python scripts/reembed_gemini.py --target all`

  - Takes about 5 min.
  - If it stops on a 429, just re-run the same command. It resumes where it stopped.
  - It should end with `Migration complete.`

- [ ] Verify in SQL. Expect `missing = 0` and `wrong_dim = 0` for both queries:

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

- [ ] Run the retrieval evaluation: `.venv/bin/python scripts/eval_retrieval.py --k 3 --faculty`

  - Gemini should match or beat MiniLM on keyword hit@3. Read the top hits yourself too; don't trust the score alone.
  - Record the result in the Status section of `docs/embeddings.md`.

- [ ] Recalibrate `FACULTY_MIN_SIMILARITY` in `backend/query/retrieval.py`.

  - It is currently a provisional 0.60, taken from one probe.
  - Pick a value between real matches (NLP, computer vision) and the junk topic ("cooking recipes") in the `--faculty` output.

- [ ] Re-test on Render:

  - "attendance requirement", "hostel curfew", "transcript verification fee" now return snippets.
  - "Which faculty work on NLP and when can I meet them?" returns faculty and their schedule.

- [ ] Locally, remove `ORION_EMBEDDING_PROVIDER=minilm` from `.env` (if you set it).

- [ ] Update the Status section of `docs/embeddings.md` and the backfill note in `CLAUDE.md` §17 to say "complete".

- [ ] Commit the migration work (nothing is committed yet).

## C. Later (only after Gemini has been validated in production)

- [ ] Decide on Gemini billing. The free tier's 1,000 embeddings/day is shared with user questions.

- [ ] Write a new migration that drops the MiniLM rollback path:

  - `document_chunks.embedding`
  - `chunks_embedding_hnsw_idx`
  - `match_document_chunks`

- [ ] Delete `backend/requirements-minilm-rollback.txt` and the `minilm` branches in `retrieval.py`.

- [ ] Optional: remove the unused `@huggingface/transformers` dependency from `package.json`.