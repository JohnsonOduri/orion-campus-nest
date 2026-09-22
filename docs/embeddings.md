# Embeddings — Gemini (`gemini-embedding-2`, 768-dim)

Migrated 2026-09-22 from in-process MiniLM (`all-MiniLM-L6-v2`, 384-dim).
Migrations: `supabase/migrations/20260922065942_gemini_embeddings.sql`,
`20260922071151_fix_embedding_trigger_search_path.sql`.

| | |
|---|---|
| Embedding model | `gemini-embedding-2` (Gemini API, `google-genai` SDK) |
| Dimensions | 768 (`output_dimensionality=768`; the API returns unit-normalized vectors at this size) |
| Vector store | Supabase pgvector (`vector` 0.8.2) |
| Runtime (query) embeddings | Gemini API — **one call per SEMANTIC/HYBRID request, zero per STRUCTURED request** |
| Document embeddings | Gemini API, once, at ingestion / backfill time |
| Faculty research embeddings | Gemini API, once, stored in `faculty.research_embedding` |
| Local ML model | **removed from the API runtime** (no torch / sentence-transformers) |
| Single code path | `backend/query/embeddings.py` — nothing else calls the embedding API |

## Status (2026-09-22) — backfill incomplete, do not serve on Gemini yet

| | embedded | total | missing |
|---|---|---|---|
| `document_chunks.embedding_gemini` | **992** | 1,269 | 277 |
| `faculty.research_embedding` | **0** | 146 | 146 |

All 992 stored vectors are 768-dim; 0 failed rows. The run stopped cleanly on
the free tier's **daily** cap (1,000 embedded texts/day). The 277 missing
chunks are the high-value regulation/procedure documents (both UG
Regulations, Hostel Rules, Transcript + Certificate Verification, the three
anti-ragging documents) plus 3 chunks of the 2021-25 AI&DS and all of the
2021-25 Cyber Security and ECE curricula.

`match_document_chunks_gemini` only searches rows that have a Gemini vector,
so **until the backfill finishes, run the API with
`ORION_EMBEDDING_PROVIDER=minilm`** (the full pre-migration behaviour, see
Rollback) or regulation/hostel questions will find nothing. Then:

1. `.venv/bin/python scripts/reembed_gemini.py --target all` (after the daily
   quota resets; ~423 texts, ~5 min at the default pacing)
2. `.venv/bin/python scripts/eval_retrieval.py --k 3 --faculty` — compare with
   MiniLM and recalibrate `FACULTY_MIN_SIMILARITY` (currently a provisional
   0.60 from a single probe)
3. only then remove `ORION_EMBEDDING_PROVIDER=minilm`.

## Measurements (2026-09-22, dev laptop; clean venvs from old/new requirements)

| | MiniLM (before) | Gemini (after) |
|---|---|---|
| Python deps installed (`backend/requirements.txt`) | 1.1 GB | 127 MB |
| `import main` (API startup) | 0.28 s | 0.30 s |
| First semantic query in a fresh process (embedding stack load) | 10.1 s (36.5 s cold disk) | 0.15 s + one API call |
| Peak RSS after first query embedding | 497–581 MB | 86 MB |
| Query embedding latency | ~6 ms (warm, local CPU) | **620–940 ms** (network round trip, 2 samples) |
| Retrieval (RPC) latency | unchanged | not yet measured end-to-end (eval pending) |

The trade is explicit: a much lighter, cold-start-friendly API in exchange
for ~0.6–0.9 s added to each SEMANTIC/HYBRID question (STRUCTURED questions
are unaffected). No Docker image exists in the repo yet, so image size is
represented by the installed dependency size above. `/ai/ask` end-to-end
latency was not measured (needs a logged-in session and the finished
backfill).

**Free-tier quota is shared.** Query-time embeddings count against the same
100/min and 1,000/day text quota as ingestion. For a deployed prototype,
enable billing on the Gemini project or budget the daily cap; when it is
exhausted, semantic/hybrid answers degrade to "temporarily unavailable"
(structured answers are unaffected).

## How it fits together

```text
QUERY (API, caller's JWT, RLS applies)
  question -> router -> STRUCTURED -> orion_* RPCs            (no embedding)
                     -> SEMANTIC   -> embed_query (1 call)
                                      -> match_document_chunks_gemini
                     -> HYBRID     -> embed_query (1 call)
                                      -> match_faculty_research + timetable

INGESTION (scripts, service role, trusted only)
  PDF -> extract/OCR -> screen -> chunk -> metadata
      -> embed_documents (batched, paced) -> document_chunks.embedding_gemini
  faculty.research_interests -> embed_documents -> faculty.research_embedding
```

### Input formatting

`gemini-embedding-2` does not accept `task_type`; the task goes into the text
(official Gemini embeddings docs). `backend/query/embeddings.py` is the only
place these strings are built:

- document chunk: `title: <document title> / <section title> | text: <chunk>`
- faculty interests: `title: none | text: <research_interests>`
- document query: `task: question answering | query: <question>`
- faculty topic query: `task: search result | query: <topic>`

Passing a **list of strings** to `embed_content` makes this model return one
*aggregated* vector. Each text is wrapped in its own `types.Content`, and the
response count and dimension are validated before anything is stored.

## Schema (additive — nothing old was dropped)

| Object | Purpose |
|---|---|
| `document_chunks.embedding_gemini vector(768)` + HNSW cosine index `chunks_embedding_gemini_hnsw_idx` | new corpus vectors; NULL = not yet embedded |
| `match_document_chunks_gemini(vector(768), match_count, filter_cohort, filter_category, filter_document_type, as_of)` | same filters and security model as `match_document_chunks`: `security invoker`, `documents.status='active'`, `valid_from <= as_of <= valid_until`; EXECUTE granted to `authenticated` only |
| `faculty.research_embedding vector(768)` | stored research-interest vector (no index: ~150 rows, exact scan) |
| `match_faculty_research(vector(768), match_count, min_similarity)` | `security invoker`, active faculty only, `authenticated` only |
| triggers `document_chunks_reset_stale_embedding`, `faculty_reset_stale_research_embedding` | if the source text changes in an UPDATE that doesn't also supply a new vector, the vector is reset to NULL — a vector is never served for text it wasn't computed from |
| **unchanged:** `document_chunks.embedding vector(384)`, `chunks_embedding_hnsw_idx`, `match_document_chunks(vector(384), …)` | MiniLM rollback path |

RLS is unchanged on every table.

## Configuration

```env
GEMINI_API_KEY=            # server only — API + ingestion scripts; never VITE_/PUBLIC_
# optional
ORION_EMBEDDING_PROVIDER=gemini      # "minilm" = rollback only, see below
ORION_EMBED_BATCH_SIZE=16            # texts per API call in scripts
ORION_EMBED_TEXTS_PER_MINUTE=90      # pacing; free tier counts each text as a request (limit 100/min)
```

`SUPABASE_SECRET_KEY` stays confined to `scripts/*` (trusted tooling). The API
never uses it; it serves every request with the caller's JWT.

## Rate limits (measured, not assumed)

On the free tier, `gemini-embedding-2` returned
`429 RESOURCE_EXHAUSTED … embed_content_free_tier_requests, limit: 100` with
`retryDelay ≈ 56s` (per minute), and later the same metric with
`limit: 1000` (per day): **every embedded text counts as one request**.
Hence:

- scripts pace by *texts per minute* (default 90), not by API calls;
- batch calls back off exponentially **and honour the server's `retryDelay`**
  (up to 120 s); a daily-quota 429 or a longer requested wait stops the run
  cleanly — progress is kept, re-run later;
- interactive queries never wait for a quota window: one quick retry at most,
  then retrieval degrades to "semantic retrieval temporarily unavailable"
  (`has_answer: false`) instead of an error. `/ai/ask` still returns 200.

## Runbook

### Backfill / re-embed existing data (resumable)

```bash
.venv/bin/python scripts/reembed_gemini.py --dry-run            # counts only, no API calls
.venv/bin/python scripts/reembed_gemini.py --target all         # documents + faculty
.venv/bin/python scripts/reembed_gemini.py --target documents --limit 100   # partial run
```

A row is pending iff its Gemini column is NULL, and each row is written
individually (guarded by `is null`), so the run can be stopped at any moment
(Ctrl-C, crash, quota). **To resume, re-run the same command.** It prints
`already migrated / remaining`, embeds only what's left, never touches the
MiniLM column, and exits non-zero while anything remains or failed. A batch
rejected as a bad request is retried item-by-item; a rejected API key aborts
immediately.

After `scripts/rebuild_faculty.py` inserts/changes faculty rows, run
`reembed_gemini.py --target faculty` (changed rows were reset to NULL by the
trigger; new rows start NULL).

### New documents

`scripts/ingest_documents.py --import` embeds only chunks it inserts or whose
content changed (dry runs make no Gemini calls), writes `embedding_gemini`,
and clears the stale MiniLM vector of a changed chunk.

### Verify

```sql
select count(*) total,
       count(embedding_gemini) gemini,
       count(*) filter (where embedding_gemini is null) missing,
       count(*) filter (where vector_dims(embedding_gemini) <> 768) wrong_dim
from document_chunks;

select count(*) filter (where research_interests is not null and research_interests <> '') with_text,
       count(research_embedding) embedded,
       count(*) filter (where vector_dims(research_embedding) <> 768) wrong_dim
from faculty;
```

Retrieval quality, side by side with MiniLM (needs the rollback requirements
for the MiniLM half, or `--gemini-only`):

```bash
.venv/bin/python scripts/eval_retrieval.py --k 3 --faculty
```

### Deploy the API

`backend/requirements.txt` no longer contains `sentence-transformers`/`torch`.
Set `GEMINI_API_KEY` in the API's secret store (server only) and allow
outbound HTTPS to `generativelanguage.googleapis.com` (already required for
generation). No model cache, no warm-up, no large memory reservation.

### Rollback

The MiniLM column, index and RPC are untouched, so rollback is a config
switch, not a data operation:

1. `pip install -r backend/requirements-minilm-rollback.txt` (brings torch back)
2. set `ORION_EMBEDDING_PROVIDER=minilm` and restart the API

Semantic document search then uses `match_document_chunks` + in-process
MiniLM, and the faculty hybrid search uses the pre-migration in-process
re-embedding (threshold 0.19) — no Gemini call on either path. Caveat,
stated plainly: chunks inserted or changed **after** this migration have no
MiniLM vector (ingestion only writes Gemini vectors; a changed chunk's stale
MiniLM vector is cleared) — re-run the pre-migration ingestion if that
matters.

Only drop `document_chunks.embedding`, `chunks_embedding_hnsw_idx` and
`match_document_chunks` in a later migration, after Gemini retrieval has been
validated in production.
