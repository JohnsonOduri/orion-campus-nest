"""Side-by-side retrieval evaluation: MiniLM (legacy) vs Gemini.

Runs a fixed set of real ORION questions through both
`match_document_chunks` (384-dim MiniLM column) and
`match_document_chunks_gemini` (768-dim Gemini column) against the live
database and scores each with a deliberately simple, inspectable proxy: does
any of the top-k chunks contain an expected keyword (case-insensitive
regex)? Prints the top hits so a human can check the proxy too.

This is a before/after sanity check for the embedding migration, not a
benchmark — keep the question set small and the expectations honest.

Needs: SUPABASE_URL + SUPABASE_SECRET_KEY (read-only use of RPCs),
GEMINI_API_KEY, and — for the MiniLM side only —
backend/requirements-minilm-rollback.txt (skipped with --gemini-only).

Usage:
  .venv/bin/python scripts/eval_retrieval.py [--k 3] [--gemini-only] [--faculty]
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.query import embeddings  # noqa: E402
from reembed_gemini import get_client, load_env  # noqa: E402

# (group, question, expected-keyword regex over the retrieved chunk text)
QUESTIONS = [
    ("regulations", "What is the attendance requirement?", r"attendance"),
    ("regulations", "What are the rules for course withdrawal?", r"withdraw"),
    ("regulations", "Can I take a summer term?", r"summer"),
    ("regulations", "How is CGPA calculated?", r"cgpa|grade point average"),
    ("curriculum", "What are the prerequisites for Machine Learning?", r"pre-?requisite"),
    ("curriculum", "Which course covers reinforcement learning?", r"reinforcement"),
    ("curriculum", "How many credits are required to graduate?", r"credits?"),
    ("hostel", "What are the hostel curfew rules?", r"curfew|in-?time|\b(9|10|11)[:.]?\d{0,2}\s*(pm|p\.m)"),
    ("hostel", "What is the campus movement timing?", r"timing|movement|\bpm\b|p\.m"),
    ("hostel", "How does the outpass process work?", r"out-?\s?pass|outing|leave"),
    ("procedures", "How do I request transcript verification?", r"transcript|verification"),
    ("procedures", "What is the verification fee?", r"fee|rs\.?|₹|inr"),
]

FACULTY_TOPICS = ["NLP", "computer vision", "VLSI design", "cryptography", "wireless communication", "cooking recipes"]


def run_rpc(client, rpc: str, vec: list[float], k: int) -> list[dict]:
    return client.rpc(rpc, {"query_embedding": vec, "match_count": k}).execute().data or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--gemini-only", action="store_true")
    ap.add_argument("--faculty", action="store_true", help="also print faculty research-match similarities")
    args = ap.parse_args()
    load_env()
    client = get_client()

    minilm = None
    if not args.gemini_only:
        from sentence_transformers import SentenceTransformer

        minilm = SentenceTransformer("all-MiniLM-L6-v2")

    score = {"gemini": 0, "minilm": 0}
    lat = {"gemini_embed": [], "gemini_rpc": []}
    for group, q, expect in QUESTIONS:
        pat = re.compile(expect, re.I)
        print(f"\n[{group}] {q}")
        systems = [("gemini", None)] + ([("minilm", None)] if minilm else [])
        for name, _ in systems:
            if name == "gemini":
                t = time.perf_counter()
                vec = embeddings.embed_query(q)
                lat["gemini_embed"].append(time.perf_counter() - t)
                t = time.perf_counter()
                rows = run_rpc(client, "match_document_chunks_gemini", vec, args.k)
                lat["gemini_rpc"].append(time.perf_counter() - t)
            else:
                vec = minilm.encode([q], normalize_embeddings=True)[0].tolist()
                rows = run_rpc(client, "match_document_chunks", vec, args.k)
            hit = any(pat.search(r["content"] or "") for r in rows)
            score[name] += hit
            print(f"  {name:6s} {'HIT ' if hit else 'miss'}")
            for r in rows:
                snippet = " ".join((r["content"] or "").split())[:90]
                print(f"      {r['similarity']:.3f}  {r['title'][:38]:38s} p{r.get('page_start')}  {snippet}")
            if name == "gemini":
                time.sleep(0.7)  # stay well under the per-minute quota

    n = len(QUESTIONS)
    print(f"\nkeyword hit@{args.k}: gemini {score['gemini']}/{n}" + (f" · minilm {score['minilm']}/{n}" if minilm else ""))
    for key, vals in lat.items():
        vals.sort()
        print(f"latency {key}: median {vals[len(vals)//2]*1000:.0f} ms, max {vals[-1]*1000:.0f} ms")

    if args.faculty:
        print("\nfaculty research match (top 3, no threshold):")
        for topic in FACULTY_TOPICS:
            vec = embeddings.embed_query(topic, task=embeddings.QUERY_TASK_SEARCH)
            rows = client.rpc("match_faculty_research", {"query_embedding": vec, "match_count": 3, "min_similarity": 0}).execute().data or []
            print(f"  {topic!r}")
            for r in rows:
                print(f"      {r['similarity']:.3f}  {r['full_name'][:30]:30s} {(r['research_interests'] or '')[:70]}")
            time.sleep(0.7)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
