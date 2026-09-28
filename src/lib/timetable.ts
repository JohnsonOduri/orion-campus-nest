// Shared between src/routes/timetable.tsx and the dashboard's "today's
// classes" widget. The backend RPC (orion_day_timetable/orion_week_timetable,
// see backend/app/api/timetable.py) has no "live/upcoming/done" concept —
// that was always a mock-only field — so it's derived here, once, from
// start_time/end_time/day_of_week vs the current time.

export type TimetableEntry = {
  id: number;
  course_code: string | null;
  course_name: string | null;
  faculty_names: string[] | null;
  room: string | null;
  day_of_week: number; // 0=Sunday .. 6=Saturday
  slot_index: number;
  start_time: string | null; // "HH:MM:SS"
  end_time: string | null;
  entry_type: "class" | "lab" | "tutorial" | "seminar" | "project" | "club_activity" | "sports" | "break" | "other";
  // One-off changes your CR announced for this date (backend/query/schedule.py)
  _cancelled?: boolean;
  _extra?: boolean;
  _moved_from?: string | null;
  _change_note?: string | null;
};

export type StudentContext = {
  display_name: string | null;
  semester: number;
  programme: string;
  department: string;
  batch: string;
  section: string;
};

export const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"] as const;

export function formatTime(t: string | null): string {
  return t ? t.slice(0, 5) : "—";
}

export type LiveStatus = "live" | "upcoming" | "done" | null;

// null means "not applicable today" (different day, or no start/end time —
// e.g. some club_activity/sports rows carry no fixed time).
export function deriveStatus(entry: TimetableEntry, now: Date): LiveStatus {
  if (entry.day_of_week !== now.getDay()) return null;
  if (!entry.start_time || !entry.end_time) return null;
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const [sh, sm] = entry.start_time.split(":").map(Number);
  const [eh, em] = entry.end_time.split(":").map(Number);
  const start = (sh ?? 0) * 60 + (sm ?? 0);
  const end = (eh ?? 0) * 60 + (em ?? 0);
  if (minutesNow < start) return "upcoming";
  if (minutesNow >= end) return "done";
  return "live";
}

export function todaysEntries(entries: TimetableEntry[], now: Date): TimetableEntry[] {
  return entries
    .filter((e) => e.day_of_week === now.getDay())
    .sort((a, b) => (a.start_time ?? "").localeCompare(b.start_time ?? ""));
}

export function entryLabel(e: TimetableEntry): string {
  if (e.course_code) return e.course_code;
  return e.entry_type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
