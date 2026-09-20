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


def build_prompt(context: GroundedContext) -> str:
    """Render a GroundedContext into a prompt that only asks the model to
    phrase what's already retrieved — never to introduce new facts."""
    lines = [
        "Answer the user's question using ONLY the facts and excerpts below. "
        "If they don't answer the question, say you don't have that information. "
        "Cite sources by name when you state a fact. "
        "A fact may include parenthetical context (e.g. explaining why an "
        "answer skips ahead to a later day) — preserve that context in your "
        "answer instead of dropping it, since it's exactly what stops a "
        "correct-but-surprising answer from reading as wrong. "
        "If the question uses a relative day word (yesterday, today, "
        "tomorrow, a weekday name), the facts have ALREADY been resolved to "
        "that exact calendar date by the retrieval system — a fact stating "
        "a specific date (e.g. 2026-09-19) IS the answer to a question "
        "about \"yesterday\", do not refuse just because the fact uses the "
        "date instead of repeating the relative word.",
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
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 256,
    temperature: float = 0.1,
) -> Optional[str]:
    """Generate a grounded answer, or None if there's nothing to ground on
    (no API call made in that case — see module docstring)."""
    if not context.has_answer:
        return None

    prompt = build_prompt(context)
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
