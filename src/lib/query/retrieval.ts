/**
 * Retrieval layer — TypeScript port of backend/query/retrieval.py.
 *
 * Every function takes a request-scoped Supabase client (anon key + the
 * caller's JWT via `Authorization: Bearer`) — the same client
 * src/lib/supabase-server.ts's `getSupabaseForRequest` builds for the
 * timetable API. Never service-role. RLS already enforces `status='active'`
 * and validity windows on every table touched here; this module relies on
 * that instead of duplicating it, exactly like backend/query/retrieval.py.
 *
 * Structured retrieval wraps the existing orion_* RPCs (docs/timetable.md)
 * unchanged. Semantic retrieval wraps the existing pgvector document_chunks
 * corpus via match_document_chunks (added in
 * supabase/migrations/20260911020000_add_match_document_chunks_rpc.sql,
 * security invoker — RLS still applies).
 */

import type { SupabaseClient } from "@supabase/supabase-js";

import { embedQuery } from "./embed";
import type { QueryPlan, RetrievalResult, SemanticSnippet, StructuredFact } from "./types";

type Row = Record<string, unknown>;

function str(row: Row, key: string): string {
  const v = row[key];
  return v === null || v === undefined ? "" : String(v);
}
function strOrNull(row: Row, key: string): string | null {
  const v = row[key];
  return v === null || v === undefined ? null : String(v);
}

// ------------------------------------------------------------ structured

export async function nextClass(client: SupabaseClient, plan: QueryPlan): Promise<RetrievalResult> {
  const { data, error } = await client.rpc("orion_next_class", {
    p_user_id: null,
    p_at: new Date().toISOString(),
    p_include_activities: false,
  });
  const row = data as Row | null;
  if (error || !row) {
    return {
      plan,
      facts: [],
      snippets: [],
      warnings: [
        error
          ? `orion_next_class failed: ${error.message}`
          : "no upcoming class found in the resolved student's active, valid timetable",
      ],
    };
  }
  const claim =
    `Next class: ${str(row, "course_code")} ${str(row, "course_name")} on day ${str(row, "day_of_week")} ` +
    `${str(row, "start_time").slice(0, 5)}-${str(row, "end_time").slice(0, 5)}`.trim();
  const fact: StructuredFact = {
    claim,
    data: row,
    source: "orion_next_class RPC (live timetable)",
    sourceId: strOrNull(row, "source_id"),
  };
  return { plan, facts: [fact], snippets: [], warnings: [] };
}

function timetableFacts(rows: Row[], source: string, withDay: boolean): StructuredFact[] {
  return rows.map((e) => {
    const label = str(e, "course_code") || str(e, "entry_type");
    const day = withDay ? `day ${str(e, "day_of_week")} ` : "";
    return {
      claim: `${label} ${day}${str(e, "start_time").slice(0, 5)}-${str(e, "end_time").slice(0, 5)}`,
      data: e,
      source,
      sourceId: strOrNull(e, "source_id"),
    };
  });
}

export async function dayTimetable(client: SupabaseClient, plan: QueryPlan): Promise<RetrievalResult> {
  const { data, error } = await client.rpc("orion_day_timetable", {
    p_user_id: null,
    p_on_date: new Date().toISOString().slice(0, 10),
  });
  const entries = (data as Row[] | null) ?? [];
  const facts = timetableFacts(entries, "orion_day_timetable RPC (live timetable)", false);
  const warnings = error
    ? [`orion_day_timetable failed: ${error.message}`]
    : entries.length
      ? []
      : ["no active, valid entries for this day"];
  return { plan, facts, snippets: [], warnings };
}

export async function weekTimetable(client: SupabaseClient, plan: QueryPlan): Promise<RetrievalResult> {
  const { data, error } = await client.rpc("orion_week_timetable", {
    p_user_id: null,
    p_on_date: new Date().toISOString().slice(0, 10),
  });
  const entries = (data as Row[] | null) ?? [];
  const facts = timetableFacts(entries, "orion_week_timetable RPC (live timetable)", true);
  const warnings = error
    ? [`orion_week_timetable failed: ${error.message}`]
    : entries.length
      ? []
      : ["no active, valid entries for this week"];
  return { plan, facts, snippets: [], warnings };
}

const WEEKDAY_TO_NUM: Record<string, number> = {
  Monday: 1, Tuesday: 2, Wednesday: 3, Thursday: 4, Friday: 5, Saturday: 6, Sunday: 7,
};

/**
 * "What classes do I have on Monday?" — resolves to the nearest upcoming
 * occurrence of that weekday (today counts if today already is that
 * weekday), then calls orion_day_timetable for that specific date — same
 * RPC and validity/status filtering as every other timetable query, just
 * with the date computed from a weekday name instead of "today".
 */
export async function dayOfWeekTimetable(client: SupabaseClient, plan: QueryPlan, weekdayName: string): Promise<RetrievalResult> {
  const targetNum = WEEKDAY_TO_NUM[weekdayName];
  if (!targetNum) {
    return { plan, facts: [], snippets: [], warnings: [`unrecognized weekday name: ${weekdayName}`] };
  }
  const today = new Date();
  const todayIso = ((today.getUTCDay() + 6) % 7) + 1; // JS 0=Sun..6=Sat -> ISO 1=Mon..7=Sun
  const offset = (targetNum - todayIso + 7) % 7;
  const target = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + offset));
  const targetDate = target.toISOString().slice(0, 10);

  const { data, error } = await client.rpc("orion_day_timetable", { p_user_id: null, p_on_date: targetDate });
  const entries = (data as Row[] | null) ?? [];
  const facts = entries.map((e) => ({
    claim: `${str(e, "course_code") || str(e, "entry_type")} ${str(e, "start_time").slice(0, 5)}-${str(e, "end_time").slice(0, 5)} (${weekdayName} ${targetDate})`,
    data: e,
    source: "orion_day_timetable RPC (live timetable)",
    sourceId: strOrNull(e, "source_id"),
  }));
  const warnings = error
    ? [`orion_day_timetable failed: ${error.message}`]
    : entries.length
      ? []
      : [`no active, valid entries for ${weekdayName} (${targetDate})`];
  return { plan, facts, snippets: [], warnings };
}

export async function facultyForCourse(
  client: SupabaseClient,
  plan: QueryPlan,
  courseCode: string,
): Promise<RetrievalResult> {
  const { data: courses } = await client
    .from("courses")
    .select("id,course_code,course_name")
    .ilike("course_code", courseCode.replace(" ", "%"))
    .limit(1);
  const course = courses?.[0] as Row | undefined;
  if (!course) {
    return {
      plan,
      facts: [],
      snippets: [],
      warnings: [`course code ${courseCode} not found in the active course catalog`],
    };
  }
  const { data: entries } = await client
    .from("timetable_entries")
    .select("id,faculty_id")
    .eq("course_id", course["id"] as number);
  const facultyIds = [...new Set(((entries ?? []) as Row[]).map((e) => e["faculty_id"]).filter(Boolean))] as number[];
  let facts: StructuredFact[] = [];
  if (facultyIds.length) {
    const { data: facRows } = await client
      .from("faculty")
      .select("id,full_name,initials,email")
      .in("id", facultyIds);
    facts = ((facRows ?? []) as Row[]).map((f) => ({
      claim: `${str(f, "full_name")} (${str(f, "initials")}) teaches ${str(course, "course_code")}`,
      data: { ...f, course },
      source: "timetable_entries + faculty (live timetable)",
    }));
  }
  const warnings = facts.length ? [] : [`no active faculty link found for ${str(course, "course_code")}`];
  return { plan, facts, snippets: [], warnings };
}

// --------------------------------------------------------------- semantic

export async function semanticSearch(
  client: SupabaseClient,
  queryText: string,
  opts: { topK?: number; cohort?: string | null; category?: string | null; documentType?: string | null } = {},
): Promise<RetrievalResult> {
  const plan: QueryPlan = {
    rawQuery: queryText,
    route: "semantic",
    structuredIntent: "none",
    topicText: queryText,
    courseCode: null,
    reasoning: "",
  };
  const embedding = await embedQuery(queryText);
  const { data, error } = await client.rpc("match_document_chunks", {
    query_embedding: embedding,
    match_count: opts.topK ?? 5,
    filter_cohort: opts.cohort ?? null,
    filter_category: opts.category ?? null,
    filter_document_type: opts.documentType ?? null,
  });
  if (error) {
    return { plan, facts: [], snippets: [], warnings: [`match_document_chunks failed: ${error.message}`] };
  }
  const rows = (data as Row[] | null) ?? [];
  const snippets: SemanticSnippet[] = rows.map((r) => ({
    content: str(r, "content"),
    documentTitle: str(r, "title"),
    sectionTitle: strOrNull(r, "section_title"),
    pageStart: (r["page_start"] as number | null) ?? null,
    pageEnd: (r["page_end"] as number | null) ?? null,
    similarity: (r["similarity"] as number) ?? 0,
    cohort: strOrNull(r, "cohort"),
    category: strOrNull(r, "category"),
    documentType: strOrNull(r, "document_type"),
    validFrom: strOrNull(r, "valid_from"),
    validUntil: strOrNull(r, "valid_until"),
  }));
  const warnings = snippets.length ? [] : ["no document chunks matched — say so, never invent an answer"];
  return { plan, facts: [], snippets, warnings };
}

// ----------------------------------------------------------------- hybrid

function dot(a: number[], b: number[]): number {
  let s = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) {
    s += (a[i] ?? 0) * (b[i] ?? 0);
  }
  return s;
}

/**
 * min_similarity=0.19 — see backend/query/retrieval.py's docstring for the
 * measurement this was tuned from (a small local model scores a bare
 * acronym like "NLP" lower against a full research-interest phrase than a
 * spelled-out query would). Kept identical here so both implementations
 * agree on the same real queries.
 */
const HYBRID_MIN_SIMILARITY = 0.19;
const HYBRID_TOP_K = 5;

type TimetableEntryJoin = {
  day_of_week: number;
  start_time: string;
  end_time: string;
  courses: { course_code: string } | null;
};

export async function facultyTopicAndSchedule(client: SupabaseClient, topic: string): Promise<RetrievalResult> {
  const plan: QueryPlan = {
    rawQuery: topic,
    route: "hybrid",
    structuredIntent: "none",
    topicText: topic,
    courseCode: null,
    reasoning: "",
  };

  const { data: facData } = await client
    .from("faculty")
    .select("id,full_name,initials,email,office_location,office_hours,research_interests")
    .not("research_interests", "is", null);
  const facRows = (facData ?? []) as Row[];
  if (!facRows.length) {
    return { plan, facts: [], snippets: [], warnings: ["no faculty rows have research_interests on file"] };
  }

  const queryVec = await embedQuery(topic);
  const corpusVecs = await Promise.all(facRows.map((f) => embedQuery(str(f, "research_interests"))));
  const ranked = facRows
    .map((f, i) => ({ f, sim: dot(queryVec, corpusVecs[i] ?? []) }))
    .sort((a, b) => b.sim - a.sim)
    .slice(0, HYBRID_TOP_K);

  const facts: StructuredFact[] = [];
  const warnings: string[] = [];
  for (const { f, sim } of ranked) {
    if (sim < HYBRID_MIN_SIMILARITY) continue;
    const { data: scheduleData } = await client
      .from("timetable_entry_faculty")
      .select("entry_id, timetable_entries(day_of_week,start_time,end_time,courses(course_code))")
      .eq("faculty_id", f["id"] as number);
    const schedule = (scheduleData ?? []) as unknown as { timetable_entries: TimetableEntryJoin | null }[];
    const seen = new Set<string>();
    const slots: { day_of_week: number; start_time: string; end_time: string; course_code: string | null }[] = [];
    for (const row of schedule) {
      const te = row.timetable_entries;
      if (!te) continue;
      const courseCode = te.courses?.course_code ?? null;
      const key = `${te.day_of_week}|${te.start_time}|${te.end_time}|${courseCode ?? ""}`;
      if (seen.has(key)) continue;
      seen.add(key);
      slots.push({ day_of_week: te.day_of_week, start_time: te.start_time, end_time: te.end_time, course_code: courseCode });
    }
    slots.sort((a, b) => a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time));

    const hasOfficeHours = Boolean(f["office_hours"]);
    const fullName = str(f, "full_name");
    facts.push({
      claim: `${fullName} (${str(f, "initials")}) — research match for '${topic}' (similarity ${sim.toFixed(2)})`,
      data: {
        faculty: {
          full_name: fullName,
          initials: f["initials"],
          email: f["email"],
          office_location: f["office_location"],
          office_hours: f["office_hours"],
        },
        similarity: sim,
        teaching_slots: slots,
        availability_basis: hasOfficeHours ? "office_hours" : "teaching_schedule_only",
      },
      source: "faculty.research_interests (local embedding match) + timetable_entries (live schedule)",
    });
    if (!hasOfficeHours) {
      warnings.push(
        `${fullName}: no office_hours on file — reporting teaching schedule only, not confirmed availability (AGENTS.md §18)`,
      );
    }
  }
  if (!facts.length) {
    warnings.push(`no faculty research_interests matched '${topic}' above the similarity threshold`);
  }
  return { plan, facts, snippets: [], warnings };
}
