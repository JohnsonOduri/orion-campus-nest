/**
 * Deterministic query classification — TypeScript port of
 * backend/query/router.py, kept rule-for-rule identical (see
 * tests/test_query_router.py for the behavior this must match).
 *
 * No LLM call here by design (README §8, AGENTS.md §4): the router must not
 * blindly send every question to vector search, and a regex classifier
 * costs nothing per call, unlike an LLM-backed one.
 */

import type { QueryPlan, RouteType, StructuredIntent } from "./types";

const NEXT_CLASS_RE =
  /\b(next class|where.*(is|s)\s+my\s+next\s+class|what.*(class|lecture).*(now|currently|right now))\b/i;
const WEEK_WORD_RE = /\b(this week|weekly|week.s)\b/i;
const TIMETABLE_WORD_RE = /\b(class|classes|timetable|schedule)\b/i;
const TODAY_TIMETABLE_RE =
  /\btoday\b.*\b(class|classes|timetable|schedule)\b|\b(class|classes|timetable|schedule)\b.*\btoday\b/i;
const WEEKDAY_RE = /\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i;
const WHO_TEACHES_RE = /\bwho\s+teaches\b|\bfaculty\s+(for|teaching)\b|\binstructor\s+for\b/i;
const COURSE_CODE_RE = /\b([IUE][A-Z]{2}\s?\d{3}|[A-Z]{2,4}\s?\d{3})\b/;

const SEMANTIC_TOPIC_RE =
  /\b(attendance|regulation|rule|policy|policies|cgpa|sgpa|grading|grade|credit|prerequisite|curriculum|syllabus|hostel|ragging|transcript|verification|procedure|condonation|registration requirement|degree requirement|summer term|continuation requirement)\b/i;

const FACULTY_MENTION_RE =
  /\b(faculty|professor|instructor)\b.*\b(work|works|working|research|specializ|interest)\w*\b|\bwho\s+(works|is\s+working)\s+(on|in)\b|\brecommend\s+a\s+faculty\b/i;
const MEET_AVAILABILITY_RE = /\b(meet|available|availability|office hours|when can i|when.s a good time)\b/i;

const STOPWORDS = new Set([
  "which", "who", "what", "faculty", "professor", "instructor", "work", "works",
  "working", "on", "in", "and", "when", "can", "i", "meet", "them", "is", "the",
  "a", "an", "recommend", "for", "of", "to", "with", "research", "interests",
]);

function extractTopic(query: string): string {
  const words = query.match(/[A-Za-z][A-Za-z.+-]*/g) ?? [];
  const kept = words.filter((w) => !STOPWORDS.has(w.toLowerCase()));
  return kept.length ? kept.join(" ") : query;
}

function plan(
  rawQuery: string,
  route: RouteType,
  reasoning: string,
  extra: Partial<Pick<QueryPlan, "structuredIntent" | "topicText" | "courseCode">> = {},
): QueryPlan {
  return {
    rawQuery,
    route,
    structuredIntent: extra.structuredIntent ?? "none",
    topicText: extra.topicText ?? null,
    courseCode: extra.courseCode ?? null,
    reasoning,
  };
}

export function classify(query: string): QueryPlan {
  const q = (query ?? "").trim();
  if (!q) {
    return plan(query, "unsupported", "empty query");
  }

  if (NEXT_CLASS_RE.test(q)) {
    return plan(query, "structured", "matched next-class pattern -> orion_next_class (live timetable)", {
      structuredIntent: "next_class",
    });
  }
  if (WEEK_WORD_RE.test(q) && TIMETABLE_WORD_RE.test(q)) {
    return plan(query, "structured", "matched week-timetable pattern -> orion_week_timetable", {
      structuredIntent: "week_timetable",
    });
  }
  if (TODAY_TIMETABLE_RE.test(q)) {
    return plan(query, "structured", "matched today-timetable pattern -> orion_day_timetable", {
      structuredIntent: "day_timetable",
    });
  }
  const weekdayMatch = q.match(WEEKDAY_RE);
  if (weekdayMatch && TIMETABLE_WORD_RE.test(q)) {
    const raw = weekdayMatch[1] ?? "";
    const weekdayName = raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
    return plan(
      query,
      "structured",
      `matched a named weekday (${weekdayName}) + class/timetable word -> orion_day_timetable for the nearest upcoming occurrence of that weekday`,
      { structuredIntent: "day_of_week_timetable", topicText: weekdayName },
    );
  }

  const courseMatch = q.match(COURSE_CODE_RE);
  if (WHO_TEACHES_RE.test(q) && courseMatch) {
    return plan(query, "structured", "matched 'who teaches <course code>' -> timetable/course join", {
      structuredIntent: "faculty_for_course",
      courseCode: (courseMatch[1] ?? "").toUpperCase(),
    });
  }

  if (FACULTY_MENTION_RE.test(q) || (/faculty/i.test(q) && MEET_AVAILABILITY_RE.test(q))) {
    return plan(
      query,
      "hybrid",
      "faculty + topic/meet pattern -> faculty.research_interests match (structured) + timetable schedule (structured); no document corpus involved",
      { topicText: extractTopic(q) },
    );
  }

  if (SEMANTIC_TOPIC_RE.test(q)) {
    return plan(query, "semantic", "matched a regulations/policy/procedure topic -> document_chunks", {
      topicText: q,
    });
  }

  return plan(query, "unsupported", "no structured/semantic/hybrid pattern matched — ambiguous or out of scope");
}
