/**
 * Context builder — TypeScript port of backend/query/context.py.
 * Pure function: RetrievalResult -> GroundedContext. hasAnswer is False
 * whenever there are no facts and no snippets, and a warning explaining why
 * is guaranteed (AGENTS.md §6 — never fail silently).
 */

import type { GroundedContext, RetrievalResult } from "./types";

export function buildContext(result: RetrievalResult): GroundedContext {
  const hasAnswer = result.facts.length > 0 || result.snippets.length > 0;
  const warnings = [...result.warnings];
  if (!hasAnswer && warnings.length === 0) {
    warnings.push("no grounded facts or document snippets retrieved");
  }
  return {
    query: result.plan.rawQuery,
    route: result.plan.route,
    facts: result.facts,
    snippets: result.snippets,
    warnings,
    hasAnswer,
  };
}
