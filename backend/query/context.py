"""Context builder: RetrievalResult -> GroundedContext.

Pure function, no I/O. This is the last stop before an eventual LLM call
(not added yet — see llm_client.py). Its only job is to decide whether
there's enough grounded evidence to answer at all, and to never let
anything through that isn't traceable to a `StructuredFact` or
`SemanticSnippet` with a real source (AGENTS.md §6: "if reliable
information cannot be retrieved, the assistant should say so").
"""

from __future__ import annotations

from .types import GroundedContext, RetrievalResult


def build_context(result: RetrievalResult) -> GroundedContext:
    has_answer = bool(result.facts) or bool(result.snippets)
    warnings = list(result.warnings)
    if not has_answer and not warnings:
        warnings.append("no grounded facts or document snippets retrieved")
    return GroundedContext(
        query=result.plan.raw_query,
        route=result.plan.route,
        facts=result.facts,
        snippets=result.snippets,
        warnings=warnings,
        has_answer=has_answer,
    )
