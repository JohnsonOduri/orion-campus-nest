"""Gemini client, called from backend/app/api/ai.py's POST /ai/ask.

Per the task that created this module: "do not add an LLM until the
routing/retrieval/context layer is independently tested." Kept as a
cost-conscious integration point, deliberately not imported by router.py,
retrieval.py, context.py, or service.py themselves — those stay pure
retrieval, generation is layered on top by the caller.

Cost-control choices, so a wired-in caller can't accidentally burn the free
tier:
  - defaults to `gemini-3.5-flash-lite`, the cheapest/fastest Gemini model
    with a free tier, not a Pro model;
  - `max_output_tokens` defaults small (256) — grounded answers from a
    GroundedContext should be short, not essays;
  - `generate()` takes the already-built GroundedContext and refuses to
    call the API at all when `has_answer` is False (AGENTS.md §6: a safe
    "I don't know" costs zero tokens — never spend a call manufacturing an
    apology);
  - no retry loop and no streaming here — a caller that wants those makes
    that decision explicitly, this module never retries silently and burns
    quota on transient errors.

This module is deliberately synchronous/minimal: it wraps the plain REST
API (no SDK dependency) since the only thing needed is one text-generation
call once a caller decides to use it.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from .types import GroundedContext

DEFAULT_MODEL = "gemini-3.5-flash-lite"
_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiNotConfigured(RuntimeError):
    pass


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiNotConfigured("GEMINI_API_KEY is not set")
    return key


def build_prompt(context: GroundedContext, history: Optional[list[dict[str, str]]] = None) -> str:
    """Render a GroundedContext into a prompt that only asks the model to
    phrase what's already retrieved — never to introduce new facts.

    `history` (oldest first, each `{"role": "user"|"assistant", "content": str}`)
    is the last few conversation turns, used ONLY so the model can resolve
    references like "it"/"that" back to the earlier turn and keep a
    consistent tone — it is never treated as a source of facts. The facts
    for THIS turn still come exclusively from `context`, produced by the
    router/retrieval layer from the current query alone (see
    backend/query/service.py — history is not fed into routing).
    """
    lines = []
    if history:
        lines.append(
            "Recent conversation so far (for tone/reference resolution only — "
            "the facts below, not this history, are the source of truth for "
            "this answer):"
        )
        for turn in history:
            speaker = "User" if turn["role"] == "user" else "ORION"
            lines.append(f"{speaker}: {turn['content']}")
        lines.append("")
    lines += [
        "The facts and excerpts below were already retrieved and matched to "
        "this exact question by a separate, deterministic system BEFORE you "
        "saw them — they are not a general-purpose search result you need "
        "to judge for relevance, they ARE the answer. Your only job is to "
        "phrase them clearly and cite sources by name, not to re-verify "
        "whether they're on-topic.\n"
        "A fact will often use different words or formats than the "
        "question — a specific date instead of \"yesterday\"/\"tomorrow\", a "
        "specific time range instead of the exact clock time asked about, "
        "etc. That is expected and already correct: the retrieval system "
        "resolved the relative/approximate wording in the question to the "
        "concrete fact shown. Never refuse or hedge just because a fact's "
        "wording doesn't literally repeat the question's wording — if a "
        "fact is present below, treat it as answering the question.\n"
        "A fact may include parenthetical context (e.g. explaining why an "
        "answer skips ahead to a later day) — preserve that context in your "
        "answer instead of dropping it, it's what stops a correct-but-"
        "surprising answer from reading as wrong.\n"
        "Only say you don't have that information when the list below is "
        "empty, or every fact is clearly about a different subject entirely "
        "(e.g. only mess-menu facts for a question about faculty).",
        "",
        f"Question: {context.query}",
        "",
    ]
    if context.facts:
        lines.append("Facts:")
        for f in context.facts:
            lines.append(f"- {f.claim} (source: {f.source})")
    if context.snippets:
        lines.append("Document excerpts:")
        for s in context.snippets:
            cite = f"{s.document_title}" + (f", {s.section_title}" if s.section_title else "")
            lines.append(f"- [{cite}] {s.content[:500]}")
    return "\n".join(lines)


def generate(
    context: GroundedContext,
    *,
    history: Optional[list[dict[str, str]]] = None,
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 256,
    temperature: float = 0.1,
) -> Optional[str]:
    """Generate a grounded answer, or None if there's nothing to ground on
    (no API call made in that case — see module docstring)."""
    if not context.has_answer:
        return None

    prompt = build_prompt(context, history)
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
            },
        }
    ).encode()
    req = urllib.request.Request(
        f"{_API_BASE}/{model}:generateContent?key={_api_key()}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts) or None


# --------------------------------------------------------------------------
# Optional passage rephrasing (2026-09-22).
#
# ORION answers every question without an LLM (backend/query/compose.py).
# When Gemini is available it may reword ONE retrieved document passage into
# a short plain-English answer — nothing else. Failures (quota exhausted,
# network, timeout) trip a circuit breaker so later requests skip Gemini
# entirely instead of each paying for another failed call; the composer's
# verbatim-quote answer is used meanwhile.

import os as _os
import time as _time
import urllib.error as _urlerror

_breaker_open_until = 0.0


class LLMUnavailable(RuntimeError):
    pass


def llm_mode() -> str:
    """ORION_LLM_MODE: "auto" (default — use Gemini for document answers
    when it's reachable) or "off" (never call it)."""
    return (_os.environ.get("ORION_LLM_MODE") or "auto").strip().lower()


def llm_available() -> bool:
    return llm_mode() != "off" and bool(_os.environ.get("GEMINI_API_KEY")) and _time.monotonic() >= _breaker_open_until


def _trip(seconds: float) -> None:
    global _breaker_open_until
    _breaker_open_until = _time.monotonic() + seconds


def rephrase_passage(question: str, passage: str, document_title: str, *, model: str = DEFAULT_MODEL, timeout: float = 8.0) -> str:
    """Rewrite `passage` as a direct 1-3 sentence answer to `question`.
    Raises LLMUnavailable on any failure (caller falls back to the quote)."""
    if not llm_available():
        raise LLMUnavailable("LLM disabled or circuit open")
    prompt = (
        "Answer the student's question using ONLY the rule quoted below, in 1-3 plain sentences. "
        "Keep every number, time, percentage and condition exactly as written. Do not add anything "
        "that is not in the quote. If the quote does not answer the question, reply exactly: NO_ANSWER\n\n"
        f"Question: {question}\n\nQuoted rule (from {document_title}):\n\"{passage}\""
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.0},
    }).encode()
    req = urllib.request.Request(
        f"{_API_BASE}/{model}:generateContent?key={_api_key()}",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except _urlerror.HTTPError as exc:
        # 429 = free-tier quota exhausted: don't try again for a while.
        _trip(1800 if exc.code == 429 else 300)
        raise LLMUnavailable(f"HTTP {exc.code}") from exc
    except Exception as exc:  # noqa: BLE001 - timeouts, DNS, TLS: all degrade
        _trip(120)
        raise LLMUnavailable(exc.__class__.__name__) from exc
    parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text or "NO_ANSWER" in text:
        raise LLMUnavailable("model found no answer in the passage")
    return text
