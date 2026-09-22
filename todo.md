# Gemini embeddings — TODO

Status as of 2026-09-22. Full runbook: docs/embeddings.md.

- Code, schema, tests: done.
- Backfill: **992 / 1,269 chunks** and **0 / 146 faculty** rows embedded. It stopped on the free-tier daily cap (1,000 texts/day).
- Still missing: both UG Regulations, Hostel Rules, Transcript and Certificate Verification, the three anti-ragging documents, and the 2021-25 Cyber Security and ECE curricula (plus 3 chunks of the 2021-25 AI&DS curriculum).

---

## A. Test now by deploying on Render

`render.yaml` at the repo root now defines this service as code (added
2026-09-22, see `docs/backend-requirements.md` §7 for the full writeup and
what was verified locally). It has **not** been created on Render yet — no
API access was available in that session. Steps below are what's left.

### Render setup

- [ ] Render dashboard → New → Blueprint → connect this repo. It reads
  `render.yaml` and proposes the `orion-api` web service automatically —
  build/start commands, health check path and `PYTHON_VERSION` are already
  set there, nothing to type by hand.

- [ ] Fill in the secret env vars `render.yaml` leaves blank (Render will
  prompt for these on first deploy):

  - `GEMINI_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
  - `FRONTEND_ORIGIN`
  - `API_BASE_URL` — leave a placeholder for the first deploy, then set it
    to the real assigned `https://orion-api.onrender.com` URL and redeploy.

- [ ] Do **not** set `SUPABASE_SECRET_KEY` on the API service — it's not in
  `render.yaml` on purpose. The API never needs it.

- [ ] Do **not** set `ORION_EMBEDDING_PROVIDER=minilm` on Render.
  `render.yaml` already fixes it to `gemini`. The Render build has no
  torch/sentence-transformers installed, so the MiniLM path cannot run
  there. Render runs on Gemini, with the partial data described above.

- [ ] Before testing login: add the frontend's real callback URL to
  Supabase Dashboard → Authentication → URL Configuration → Redirect URLs
  (currently only the localhost one is allowed).

- [ ] **Cookie domain blocker (confirmed against the live Public Suffix
  List):** `onrender.com` is a registered public suffix, so a frontend on
  one bare `*.onrender.com` service and this API on another are different
  "sites" — `SameSite=Lax` cookies will NOT be sent on the frontend's
  cross-site `fetch` calls, and login will silently fail past the initial
  `set-session` call. Put the frontend and API on one custom registrable
  domain (e.g. `app.<domain>` + `api.<domain>`) before relying on login.

### Things to check

> Already verified locally against a clean venv built from
> `backend/requirements.txt` alone (docs/backend-requirements.md §7): 128 MB
> installed, no torch/sentence-transformers, `GET /health` → 200, 75 MB RSS
> at idle, every protected route → 401 without a cookie. The items below are
> the same checks against the *real* Render deployment, not a repeat of that
> local verification.

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