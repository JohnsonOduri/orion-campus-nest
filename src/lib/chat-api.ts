import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseForRequest } from "@/lib/supabase-server";
import { answerQuery } from "@/lib/query/service";
import type { GroundedContext } from "@/lib/query/types";

function supabaseUrl(): string | null {
  const env = process.env;
  return env["SUPABASE_URL"] ?? env["VITE_SUPABASE_URL"] ?? env["PUBLIC_SUPABASE_URL"] ?? null;
}
function anonKey(): string | null {
  const env = process.env;
  return (
    env["SUPABASE_ANON_KEY"] ??
    env["SUPABASE_PUBLIC_ANON_KEY"] ??
    env["VITE_SUPABASE_ANON_KEY"] ??
    env["PUBLIC_SUPABASE_ANON_KEY"] ??
    null
  );
}

const TEST_STUDENT_EMAIL = "orion-test-student-a@iiitkottayam.ac.in";
const TEST_STUDENT_PASSWORD = "OrionTest#2026a";

let testStudentTokenCache: { token: string; expiresAt: number } | null = null;

/**
 * TEMPORARY scaffolding until Phase 1.1 (real authentication) exists —
 * tasks-done.md §1.1: "Authentication — Not started"; README: "Auth is
 * simulated; no credentials are verified." There is no login flow anywhere
 * in the app yet, so a browser request never carries a real bearer token,
 * and `getSupabaseForRequest` below always returns null for the chat panel
 * today. Without this, the query router could only ever be exercised in
 * demo mode from the UI.
 *
 * This signs in as the already-provisioned test student
 * (scripts/create_test_students.py) with a real password grant so the chat
 * panel demonstrates the router against REAL data. It is not a client-
 * identity shortcut: the browser never supplies or influences who this
 * resolves to, and every downstream call still goes through the exact same
 * RLS / orion_resolve_user path a real logged-in user would use. The
 * response is always flagged `usedTestStudent: true` so the UI can make
 * this visible (matches the existing timetable "demo mode" transparency
 * rule) — replace with a real session lookup once login exists.
 */
async function getTestStudentClient(): Promise<SupabaseClient | null> {
  const url = supabaseUrl();
  const anon = anonKey();
  if (!url || !anon) return null;

  const now = Date.now();
  if (!testStudentTokenCache || testStudentTokenCache.expiresAt < now) {
    const res = await fetch(`${url.replace(/\/$/, "")}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: { apikey: anon, "Content-Type": "application/json" },
      body: JSON.stringify({ email: TEST_STUDENT_EMAIL, password: TEST_STUDENT_PASSWORD }),
    });
    if (!res.ok) return null;
    const payload = (await res.json()) as { access_token: string; expires_in: number };
    testStudentTokenCache = {
      token: payload.access_token,
      expiresAt: now + (payload.expires_in - 60) * 1000,
    };
  }

  return createClient(url, anon, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: `Bearer ${testStudentTokenCache.token}` } },
  });
}

export type ChatResponse = {
  route: GroundedContext["route"];
  hasAnswer: boolean;
  text: string;
  usedTestStudent: boolean;
  demo: boolean;
};

const NO_ANSWER_HINT =
  "I can help with things like your next class, timetable for a specific day, attendance/academic regulations, or which faculty work on a topic — try one of those.";

function formatContext(ctx: GroundedContext): string {
  if (!ctx.hasAnswer) {
    if (ctx.route === "unsupported") {
      return `I'm not sure how to help with that yet. ${NO_ANSWER_HINT}`;
    }
    const reason = ctx.warnings[0];
    return reason
      ? `I don't have grounded information for that. (${reason})`
      : "I don't have grounded information for that.";
  }
  const lines: string[] = [];
  for (const f of ctx.facts) {
    lines.push(`• ${f.claim}`);
  }
  for (const s of ctx.snippets) {
    const cite = s.sectionTitle ? `${s.documentTitle} — ${s.sectionTitle}` : s.documentTitle;
    const excerpt = s.content.length > 280 ? `${s.content.slice(0, 280).trim()}…` : s.content.trim();
    lines.push(`• [${cite}] ${excerpt}`);
  }
  if (ctx.warnings.length) {
    lines.push("", ...ctx.warnings.map((w) => `⚠️ ${w}`));
  }
  return lines.join("\n");
}

/**
 * Routes a raw chat message through the query router / retrieval / context
 * layer (src/lib/query/) and returns a formatted, cited response. No LLM
 * call — this renders the GroundedContext directly (docs/query-router.md
 * §4: generation is a deliberately separate, not-yet-built next step).
 */
export const askOrion = createServerFn({ method: "POST" })
  .validator((input: unknown) => {
    const v = (input ?? {}) as { query?: string };
    return { query: (v.query ?? "").toString() };
  })
  .handler(async ({ data }): Promise<ChatResponse> => {
    const request = getRequest();
    let client = getSupabaseForRequest(request);
    let usedTestStudent = false;
    if (!client) {
      client = await getTestStudentClient();
      usedTestStudent = client !== null;
    }
    if (!client) {
      return {
        route: "unsupported",
        hasAnswer: false,
        text: "ORION's backend isn't configured in this environment (no Supabase connection) — this is demo mode.",
        usedTestStudent: false,
        demo: true,
      };
    }

    const ctx = await answerQuery(client, data.query);
    return {
      route: ctx.route,
      hasAnswer: ctx.hasAnswer,
      text: formatContext(ctx),
      usedTestStudent,
      demo: false,
    };
  });
