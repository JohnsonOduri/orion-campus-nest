/**
 * Top-level orchestration — TypeScript port of backend/query/service.py.
 * raw query -> QueryPlan -> RetrievalResult -> GroundedContext. No LLM call
 * here (see backend/query/llm_client.py's rationale — unchanged for this
 * port: the chat panel renders the GroundedContext directly).
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import { buildContext } from "./context";
import * as retrieval from "./retrieval";
import { classify } from "./router";
import type { GroundedContext, RetrievalResult } from "./types";

export async function answerQuery(client: SupabaseClient, query: string): Promise<GroundedContext> {
  const plan = classify(query);

  let result: RetrievalResult;
  if (plan.route === "unsupported") {
    result = { plan, facts: [], snippets: [], warnings: ["unsupported or ambiguous query"] };
  } else if (plan.route === "structured") {
    switch (plan.structuredIntent) {
      case "next_class":
        result = await retrieval.nextClass(client, plan);
        break;
      case "day_timetable":
        result = await retrieval.dayTimetable(client, plan);
        break;
      case "week_timetable":
        result = await retrieval.weekTimetable(client, plan);
        break;
      case "day_of_week_timetable":
        result = await retrieval.dayOfWeekTimetable(client, plan, plan.topicText ?? "");
        break;
      case "faculty_for_course":
        result = await retrieval.facultyForCourse(client, plan, plan.courseCode ?? "");
        break;
      default:
        result = { plan, facts: [], snippets: [], warnings: ["structured route with no recognized intent"] };
    }
  } else if (plan.route === "semantic") {
    result = await retrieval.semanticSearch(client, plan.topicText ?? plan.rawQuery);
  } else {
    result = await retrieval.facultyTopicAndSchedule(client, plan.topicText ?? plan.rawQuery);
  }

  result.plan = plan;
  return buildContext(result);
}
