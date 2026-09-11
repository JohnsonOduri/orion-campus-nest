import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import type { SupabaseClient } from "@supabase/supabase-js";

import { getSupabaseForRequest } from "@/lib/supabase-server";
import { DEMO_STUDENT } from "@/lib/timetable-demo";

export type TimetableEntryDto = {
  course_code: string | null;
  course_name: string | null;
  faculty: string[];
  room: string | null;
  day: string;
  day_of_week: number;
  slot_index: number;
  start_time: string | null;
  end_time: string | null;
  entry_type: string;
};

export type TimetableResponse = {
  student: {
    name: string;
    semester: number;
    programme: string;
    branch: string;
    batch: string;
    section: string;
    demo: boolean;
  } | null;
  entries: TimetableEntryDto[];
};

export type NextClassResponse = {
  student: TimetableResponse["student"];
  next_class: TimetableEntryDto | null;
  as_of: string;
  include_activities: boolean;
};

const DAY_NAMES = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
] as const;

type RawEntry = {
  course_code: string | null;
  course_name: string | null;
  readonly faculty_names?: readonly string[] | null;
  room: string | null;
  day_of_week: number;
  slot_index: number;
  start_time: string | null;
  end_time: string | null;
  entry_type: string;
};

function toDto(e: RawEntry): TimetableEntryDto {
  return {
    course_code: e.course_code ?? null,
    course_name: e.course_name ?? null,
    faculty: e.faculty_names ? [...e.faculty_names] : [],
    room: e.room ?? null,
    day: DAY_NAMES[e.day_of_week % 7] ?? "",
    day_of_week: e.day_of_week,
    slot_index: e.slot_index,
    start_time: e.start_time ? e.start_time.slice(0, 5) : null,
    end_time: e.end_time ? e.end_time.slice(0, 5) : null,
    entry_type: e.entry_type,
  };
}

type StudentCtx = {
  display_name: string | null;
  semester: number;
  programme: string;
  branch: string;
  batch: string;
  section: string;
};

function demoStudent() {
  return {
    name: DEMO_STUDENT.display_name,
    semester: DEMO_STUDENT.semester,
    programme: DEMO_STUDENT.programme,
    branch: DEMO_STUDENT.branch,
    batch: DEMO_STUDENT.batch,
    section: DEMO_STUDENT.section,
    demo: true,
  };
}

function studentFromCtx(ctx: StudentCtx | null) {
  if (!ctx) return null;
  return {
    name: ctx.display_name ?? "Student",
    semester: ctx.semester,
    programme: ctx.programme,
    branch: ctx.branch,
    batch: ctx.batch,
    section: ctx.section,
    demo: false,
  };
}

type Scoped = { client: SupabaseClient; demo: boolean };

/**
 * Resolve the Supabase client for a user request.
 *
 * Preferred: a request-scoped client carrying the caller's verified JWT so
 * orion_* functions resolve auth.uid() and RLS applies (never a client-supplied
 * user id). Fallback (no Supabase configured): demo mode, clearly flagged.
 * The service-role admin client is NOT used to serve user requests — it would
 * bypass RLS and orion_resolve_user's identity rule.
 */
async function scopedClient(request: Request): Promise<Scoped> {
  const userClient = getSupabaseForRequest(request);
  if (userClient) {
    return { client: userClient, demo: false };
  }
  return { client: null as unknown as SupabaseClient, demo: true };
}

async function getStudentContext(
  request: Request,
): Promise<{ ctx: StudentCtx | null; demo: boolean }> {
  const { client, demo } = await scopedClient(request);
  if (client) {
    const { data, error } = await client.rpc("orion_student_context");
    if (!error && data) {
      return { ctx: data as StudentCtx, demo: false };
    }
  }
  // No bearer token / no Supabase configured (or no profile yet): demo mode.
  return { ctx: null, demo: true };
}

// ---------------------------------------------------------------- functions

export const getTimetable = createServerFn({ method: "GET" }).handler(
  async (): Promise<TimetableResponse> => {
    const request = getRequest();
    const { ctx, demo } = await getStudentContext(request);
    if (demo) {
      return {
        student: demoStudent(),
        entries: DEMO_STUDENT.entries.map(toDto),
      };
    }
    const { client } = await scopedClient(request);
    const { data, error } = await client.rpc("orion_day_timetable", {
      p_on_date: new Date().toISOString().slice(0, 10),
    });
    if (error) throw new Error(`timetable query failed: ${error.message}`);
    return {
      student: studentFromCtx(ctx),
      entries: ((data as RawEntry[]) ?? []).map(toDto),
    };
  },
);

export const getTodayTimetable = createServerFn({ method: "GET" }).handler(
  async (): Promise<TimetableResponse> => {
    const request = getRequest();
    const { ctx, demo } = await getStudentContext(request);
    if (demo) {
      const today = new Date().getDay();
      return {
        student: demoStudent(),
        entries: DEMO_STUDENT.entries.filter((e) => e.day_of_week === today).map(toDto),
      };
    }
    const { client } = await scopedClient(request);
    const { data, error } = await client.rpc("orion_day_timetable", {
      p_on_date: new Date().toISOString().slice(0, 10),
    });
    if (error) throw new Error(`timetable query failed: ${error.message}`);
    return {
      student: studentFromCtx(ctx),
      entries: ((data as RawEntry[]) ?? []).map(toDto),
    };
  },
);

export const getWeekTimetable = createServerFn({ method: "GET" }).handler(
  async (): Promise<TimetableResponse> => {
    const request = getRequest();
    const { ctx, demo } = await getStudentContext(request);
    if (demo) {
      return {
        student: demoStudent(),
        entries: DEMO_STUDENT.entries.map(toDto),
      };
    }
    const { client } = await scopedClient(request);
    const { data, error } = await client.rpc("orion_week_timetable", {
      p_on_date: new Date().toISOString().slice(0, 10),
    });
    if (error) throw new Error(`timetable query failed: ${error.message}`);
    return {
      student: studentFromCtx(ctx),
      entries: ((data as RawEntry[]) ?? []).map(toDto),
    };
  },
);

export const getNextClass = createServerFn({ method: "GET" })
  .validator((input: unknown) => {
    const v = (input ?? {}) as { include_activities?: boolean };
    return { include_activities: v.include_activities === true };
  })
  .handler(async ({ data }): Promise<NextClassResponse> => {
    const request = getRequest();
    const { ctx, demo } = await getStudentContext(request);
    const asOf = new Date().toISOString();
    if (demo) {
      return {
        student: demoStudent(),
        next_class: demoNextClass(data.include_activities),
        as_of: asOf,
        include_activities: data.include_activities,
      };
    }
    const { client } = await scopedClient(request);
    const { data: row, error } = await client.rpc("orion_next_class", {
      p_include_activities: data.include_activities,
    });
    if (error) throw new Error(`next-class query failed: ${error.message}`);
    return {
      student: studentFromCtx(ctx),
      next_class: row ? toDto(row as RawEntry) : null,
      as_of: asOf,
      include_activities: data.include_activities,
    };
  });

// ------------------------------------------------------------- demo helper

function demoNextClass(includeActivities: boolean): TimetableEntryDto | null {
  const now = new Date();
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const candidates = DEMO_STUDENT.entries
    .filter((e): e is (typeof DEMO_STUDENT.entries)[number] => {
      if (e.day_of_week !== now.getDay()) return false;
      if (!includeActivities && e.entry_type === "club_activity") return false;
      const [eh] = e.end_time.split(":").map(Number) as [number, number];
      // ongoing classes count as next
      return minutesNow < eh * 60;
    })
    .map((e) => ({ ...e, faculty_names: [...e.faculty_names] }))
    .sort((a, b) => Number(a.start_time.replace(":", "")) - Number(b.start_time.replace(":", "")));
  const next = candidates[0];
  return next ? toDto(next) : null;
}
