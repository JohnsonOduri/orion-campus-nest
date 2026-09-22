"""Backfill Gemini (gemini-embedding-2, 768-dim) vectors — resumable.

Targets:
  documents  document_chunks.embedding_gemini   (from content, titled by
             "<document title> / <section title>")
  faculty    faculty.research_embedding         (from research_interests)

Resumability is the column itself: a row is pending iff its Gemini vector
is NULL. A run only ever writes that one column, one row at a time, so
stopping it (Ctrl-C, crash, quota exhaustion) at any point leaves every
already-written row valid; re-running picks up exactly the rows still NULL.
The original MiniLM `document_chunks.embedding` column is never read or
written here. The DB triggers from migration 20260922000001 reset a
vector to NULL whenever its source text changes, so "NULL" also covers
"stale".

Rate limiting: the free tier counts every embedded text as one request
(100/min for gemini-embedding-2), so batches (default 16 texts per call)
are paced to --per-minute texts/minute (default 90). 429/5xx/timeouts back
off inside backend/query/embeddings.py, honouring the server's retryDelay. If a batch still fails transiently the
run stops cleanly (exit 1) — just re-run later. A batch rejected as a bad
request (4xx) is retried item-by-item so one bad row cannot block the rest;
rows that still fail are reported and left NULL. Auth/config errors
(missing/invalid key) abort immediately.

Usage:
  .venv/bin/python scripts/reembed_gemini.py --dry-run
  .venv/bin/python scripts/reembed_gemini.py --target documents
  .venv/bin/python scripts/reembed_gemini.py --target faculty
  .venv/bin/python scripts/reembed_gemini.py --target all --batch-size 8 --per-minute 60

Needs SUPABASE_URL + SUPABASE_SECRET_KEY (service role — trusted tooling
only, never the API) and GEMINI_API_KEY in the repo-root .env.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import embeddings  # noqa: E402

PAGE_SIZE = 200


@dataclass
class Target:
    name: str
    table: str
    vector_column: str
    select: str
    text_of: Callable[[dict], Optional[str]]
    title_of: Callable[[dict], Optional[str]]
    source_filter: Callable[[Any], Any] = lambda q: q


def _chunk_title(row: dict) -> Optional[str]:
    doc = row.get("documents") or {}
    return embeddings.chunk_title(doc.get("title"), row.get("section_title"))


TARGETS = {
    "documents": Target(
        name="documents",
        table="document_chunks",
        vector_column="embedding_gemini",
        select="id,content,section_title,documents(title)",
        text_of=lambda r: r.get("content"),
        title_of=_chunk_title,
    ),
    "faculty": Target(
        name="faculty",
        table="faculty",
        vector_column="research_embedding",
        select="id,research_interests",
        text_of=lambda r: r.get("research_interests"),
        title_of=lambda r: None,
        source_filter=lambda q: q.not_.is_("research_interests", "null").neq("research_interests", ""),
    ),
}


@dataclass
class Stats:
    total: int = 0
    already_done: int = 0
    embedded: int = 0
    skipped_empty: int = 0
    failed_ids: list = field(default_factory=list)


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except ImportError:  # pragma: no cover
        pass


def get_client() -> Any:
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("error: SUPABASE_URL and SUPABASE_SECRET_KEY must be set (service role, trusted tooling only)")
    return create_client(url, key)


def count(client: Any, t: Target, *, pending_only: bool) -> int:
    q = t.source_filter(client.table(t.table).select("id", count="exact").limit(1))
    if pending_only:
        q = q.is_(t.vector_column, "null")
    return q.execute().count or 0


def iter_pending(client: Any, t: Target) -> Iterator[list[dict]]:
    """Keyset pagination over pending rows — never loads the corpus at once,
    and a row that fails (left NULL) cannot make the loop revisit it."""
    last_id = 0
    while True:
        q = (
            t.source_filter(client.table(t.table).select(t.select))
            .is_(t.vector_column, "null")
            .gt("id", last_id)
            .order("id")
            .limit(PAGE_SIZE)
        )
        rows = q.execute().data or []
        if not rows:
            return
        yield rows
        last_id = rows[-1]["id"]


def write_vectors(client: Any, t: Target, rows: list[dict], vectors: list[list[float]]) -> None:
    for row, vec in zip(rows, vectors):
        # Guarded by `is null`: never overwrite a vector another run (or a
        # fresh ingestion) wrote in the meantime.
        client.table(t.table).update({t.vector_column: vec}).eq("id", row["id"]).is_(t.vector_column, "null").execute()


def embed_rows(t: Target, rows: list[dict]) -> list[list[float]]:
    return embeddings.embed_documents([t.text_of(r) for r in rows], [t.title_of(r) for r in rows])


def process(client: Any, t: Target, *, batch_size: int, min_interval: float, limit: Optional[int]) -> Stats:
    st = Stats(total=count(client, t, pending_only=False))
    pending = count(client, t, pending_only=True)
    st.already_done = st.total - pending
    print(f"[{t.name}] {st.total} rows with source text · already migrated {st.already_done} · remaining {pending}")
    if pending == 0:
        return st

    last_call = 0.0
    batch_no = 0
    started = time.perf_counter()
    for page in iter_pending(client, t):
        for i in range(0, len(page), batch_size):
            if limit is not None and st.embedded + len(st.failed_ids) >= limit:
                print(f"[{t.name}] --limit {limit} reached; stopping (re-run to continue)")
                return st
            batch = []
            for r in page[i : i + batch_size]:
                if (t.text_of(r) or "").strip():
                    batch.append(r)
                else:
                    st.skipped_empty += 1
            if not batch:
                continue
            wait = min_interval - (time.perf_counter() - last_call)
            if wait > 0:
                time.sleep(wait)
            batch_no += 1
            last_call = time.perf_counter()
            try:
                vectors = embed_rows(t, batch)
                write_vectors(client, t, batch, vectors)
                st.embedded += len(batch)
            except embeddings.EmbeddingAuthError as exc:
                raise SystemExit(f"error: Gemini rejected the API key/permissions — aborting ({exc})")
            except embeddings.EmbeddingRequestError as exc:
                print(f"[{t.name}] batch {batch_no} rejected ({exc}); isolating item-by-item")
                for r in batch:
                    time.sleep(min_interval / len(batch))
                    try:
                        write_vectors(client, t, [r], embed_rows(t, [r]))
                        st.embedded += 1
                    except embeddings.EmbeddingAuthError as auth_exc:
                        raise SystemExit(f"error: Gemini rejected the API key/permissions — aborting ({auth_exc})")
                    except (embeddings.EmbeddingRequestError, embeddings.EmbeddingResponseError) as item_exc:
                        st.failed_ids.append(r["id"])
                        print(f"[{t.name}]   id={r['id']} failed: {item_exc}")
            except embeddings.EmbeddingResponseError as exc:
                st.failed_ids.extend(r["id"] for r in batch)
                print(f"[{t.name}] batch {batch_no} malformed response ({exc}); rows left NULL")
            done = st.already_done + st.embedded
            rate = st.embedded / max(1e-9, time.perf_counter() - started)
            print(f"[{t.name}] batch {batch_no}: +{len(batch)} → {done}/{st.total} ({rate:.1f} rows/s)")
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill gemini-embedding-2 (768-dim) vectors, resumably.")
    ap.add_argument("--target", choices=["documents", "faculty", "all"], default="all")
    ap.add_argument("--batch-size", type=int, default=int(os.environ.get("ORION_EMBED_BATCH_SIZE", 16)))
    ap.add_argument("--per-minute", type=float, default=None,
                    help="max texts embedded per minute (default ORION_EMBED_TEXTS_PER_MINUTE or 90; "
                         "the free tier allows 100)")
    ap.add_argument("--limit", type=int, default=None, help="embed at most N rows per target this run")
    ap.add_argument("--dry-run", action="store_true", help="report counts only; no Gemini calls, no writes")
    args = ap.parse_args()
    if args.batch_size < 1 or args.batch_size > 100:
        ap.error("--batch-size must be between 1 and 100")
    min_interval = embeddings.batch_interval_s(args.batch_size, args.per_minute)
    sys.stdout.reconfigure(line_buffering=True)

    load_env()
    client = get_client()
    names = ["documents", "faculty"] if args.target == "all" else [args.target]

    if args.dry_run:
        for n in names:
            t = TARGETS[n]
            total = count(client, t, pending_only=False)
            pending = count(client, t, pending_only=True)
            print(f"[{n}] {total} rows · already migrated {total - pending} · remaining {pending} "
                  f"(~{-(-pending // args.batch_size)} API calls at batch size {args.batch_size})")
        print("dry run: no Gemini calls made, nothing written")
        return 0

    if not embeddings.is_configured():
        print("error: GEMINI_API_KEY is not set", file=sys.stderr)
        return 2

    exit_code = 0
    for n in names:
        try:
            st = process(client, TARGETS[n], batch_size=args.batch_size, min_interval=min_interval, limit=args.limit)
        except embeddings.EmbeddingUnavailable as exc:
            print(f"[{n}] stopping: {exc}\n[{n}] progress is saved — re-run the same command to resume.", file=sys.stderr)
            return 1
        remaining = count(client, TARGETS[n], pending_only=True)
        print(f"[{n}] done this run: embedded {st.embedded}, skipped empty {st.skipped_empty}, "
              f"failed {len(st.failed_ids)}{' ' + str(st.failed_ids[:20]) if st.failed_ids else ''}; remaining {remaining}")
        if st.failed_ids or remaining:
            exit_code = 1
    if exit_code == 0:
        print("Migration complete.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
