/**
 * Typed contracts for the ORION query router / retrieval / context layer.
 *
 * TypeScript port of backend/query/types.py, kept behaviorally identical so
 * the router/retrieval logic in this directory mirrors the independently
 * tested Python implementation (docs/query-router.md) rather than
 * reinventing it. No I/O in this file.
 */

export type RouteType = "structured" | "semantic" | "hybrid" | "unsupported";

export type StructuredIntent =
  | "next_class"
  | "day_timetable"
  | "week_timetable"
  | "day_of_week_timetable"
  | "faculty_for_course"
  | "none";

/** The router's output: what kind of question this is, never the answer. */
export type QueryPlan = {
  rawQuery: string;
  route: RouteType;
  structuredIntent: StructuredIntent;
  topicText: string | null;
  courseCode: string | null;
  reasoning: string;
};

export type StructuredFact = {
  claim: string;
  data: Record<string, unknown>;
  source: string;
  sourceId?: string | null;
};

export type SemanticSnippet = {
  content: string;
  documentTitle: string;
  sectionTitle: string | null;
  pageStart: number | null;
  pageEnd: number | null;
  similarity: number;
  cohort: string | null;
  category: string | null;
  documentType: string | null;
  validFrom: string | null;
  validUntil: string | null;
};

export type RetrievalResult = {
  plan: QueryPlan;
  facts: StructuredFact[];
  snippets: SemanticSnippet[];
  warnings: string[];
};

export type GroundedContext = {
  query: string;
  route: RouteType;
  facts: StructuredFact[];
  snippets: SemanticSnippet[];
  warnings: string[];
  hasAnswer: boolean;
};
