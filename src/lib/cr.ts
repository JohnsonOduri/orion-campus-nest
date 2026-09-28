// Types and helpers for the CR upload workflow (src/routes/cr.tsx, the
// admin review queue). Shapes mirror backend/cr_ingest/ and
// backend/app/api/{cr,admin}.py.

export const WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

export const ENTRY_TYPES = [
  "class",
  "lab",
  "tutorial",
  "seminar",
  "project",
  "club_activity",
  "sports",
  "other",
] as const;
export type EntryType = (typeof ENTRY_TYPES)[number];

export type DraftEntry = {
  day_of_week: number | null; // 1 = Monday … 7 = Sunday
  start_time: string | null; // "HH:MM"
  end_time: string | null;
  course_code: string | null;
  course_name?: string | null; // resolved by the server, read-only
  faculty_initials: string[];
  faculty_names?: string[]; // resolved by the server, read-only
  entry_type: EntryType | string;
  lab_batch: number | null;
  source_text?: string | null;
};

export type DraftIssue = { index: number; field: string; message: string; severity: "error" | "warning" };

export type ClassKey = {
  semester: number;
  programme: string;
  department: string;
  batch: string | null;
  section: string | null;
};

export type TimetableDiff = {
  added: DraftEntry[];
  removed: DraftEntry[];
  changed: { before: DraftEntry; after: DraftEntry }[];
  unchanged: number;
};

export type TimetablePayload = {
  class: ClassKey;
  class_label: string;
  entries: DraftEntry[];
  issues: DraftIssue[];
  can_submit: boolean;
  diff: TimetableDiff;
  current_count: number;
  notes: string[];
};

export const ACADEMIC_CATEGORIES = ["QUIZ", "EXAM", "ASSIGNMENT", "CLASS_UPDATE", "DEADLINE", "ACADEMIC"] as const;
export const OTHER_CATEGORIES = ["EVENT", "CLUB", "OFFICIAL", "GENERAL", "ADVERTISEMENT"] as const;
export const CATEGORY_LABELS: Record<string, string> = {
  QUIZ: "Quiz",
  EXAM: "Exam",
  ASSIGNMENT: "Assignment",
  CLASS_UPDATE: "Class update (cancel / reschedule / extra)",
  DEADLINE: "Deadline",
  ACADEMIC: "Other academic",
  EVENT: "Event",
  CLUB: "Club",
  OFFICIAL: "Official",
  GENERAL: "General",
  ADVERTISEMENT: "Advertisement",
};

export function isAcademic(category: string | null | undefined): boolean {
  return (ACADEMIC_CATEGORIES as readonly string[]).includes((category ?? "").toUpperCase());
}

export type AnnouncementDraft = {
  title: string;
  content: string;
  category: string;
  event_date: string | null;
  event_time: string | null;
  valid_until: string | null;
  sensitive: string[];
  auto_publish: boolean;
  decision?: { publish_now: boolean; reason: string };
};

export type ExamEntry = {
  exam_date: string | null;
  start_time: string | null;
  end_time: string | null;
  course_code: string | null;
  course_name: string | null;
  department: string | null;
  alt_group: string | null;
  notes?: string | null;
  in_catalogue?: boolean;
};

export type ExamDiff = {
  added: ExamEntry[];
  removed: ExamEntry[];
  changed: { before: ExamEntry; after: ExamEntry }[];
  unchanged: number;
};

export type ExamPayload = {
  scope: { semester: number; department: string | null; programme?: string | null };
  scope_label: string;
  exam_type: string;
  exam_type_label: string;
  entries: ExamEntry[];
  issues: DraftIssue[];
  can_submit: boolean;
  diff: ExamDiff;
  current_count: number;
  departments: string[];
  notes: string[];
};

export const EXAM_TYPES: { value: string; label: string }[] = [
  { value: "end_sem", label: "End semester" },
  { value: "mid_sem", label: "Mid semester" },
  { value: "repeat", label: "Repeat / supplementary" },
  { value: "quiz", label: "Quiz / class test" },
  { value: "other", label: "Other" },
];

export type ClassChange = {
  change_type: "cancel" | "reschedule" | "extra" | string;
  change_date: string | null;
  course_code: string | null;
  course_name?: string | null;
  original_start?: string | null;
  original_end?: string | null;
  new_date?: string | null;
  new_start?: string | null;
  new_end?: string | null;
  note?: string | null;
};

export type ClassChangePreview = {
  permanent: boolean;
  changes: ClassChange[];
  notes: string[];
  issues: DraftIssue[];
  can_post: boolean;
  courses: { course_code: string; course_name: string | null }[];
  class_label: string;
};

export type ClassOption = { programme: string; semester: number; department: string; section: string };

export type TargetClass = { semester: number; department?: string | null; section?: string | null; programme?: string };

export function targetQuery(t: TargetClass | null | undefined): string {
  if (!t) return "";
  const q = new URLSearchParams({ semester: String(t.semester) });
  if (t.department) q.set("department", t.department);
  if (t.section) q.set("section", t.section);
  return `?${q.toString()}`;
}

export type UploadResult = {
  kind: "timetable" | "exam_timetable" | "announcement" | "other";
  method: "layout" | "text" | "vision" | "manual";
  confidence: number;
  text: string;
  announcement: AnnouncementDraft | null;
  timetable: TimetablePayload | null;
  exams: ExamPayload | null;
  warnings: string[];
  upload_path: string | null;
};

export const METHOD_LABELS: Record<string, string> = {
  layout: "Read from the PDF's layout (exact)",
  text: "Read from the PDF's text",
  vision: "Read with OCR — check every value",
  manual: "Entered by hand",
};

export function dayName(d: number | null | undefined): string {
  return (d && d >= 1 && d <= 7 ? WEEK_DAYS[d - 1] : undefined) ?? "—";
}

export function toMinutes(t: string | null | undefined): number | null {
  if (!t || !/^\d{1,2}:\d{2}/.test(t)) return null;
  const [h, m] = t.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export function fromMinutes(m: number): string {
  const h = Math.floor(m / 60) % 24;
  return `${String(h).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function entryTitle(e: DraftEntry): string {
  if (e.course_code) return e.course_code;
  if (e.source_text) return e.source_text.replace(/\s+/g, " ").slice(0, 28);
  return String(e.entry_type).replace("_", " ");
}

export function blankEntry(day: number, start: string, end: string): DraftEntry {
  return {
    day_of_week: day,
    start_time: start,
    end_time: end,
    course_code: null,
    faculty_initials: [],
    entry_type: "class",
    lab_batch: null,
    source_text: null,
  };
}

// The server stores only these fields; resolved names are re-derived.
export function stripResolved(entries: DraftEntry[]): DraftEntry[] {
  return entries.map(({ course_name: _n, faculty_names: _f, ...rest }) => rest);
}

export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

// Phone photos are often 3–8 MB; the /be proxy caps bodies at ~4.5 MB.
// Re-encode large images as JPEG, longest side ≤ 2200 px — still plenty for
// OCR of a timetable grid. PDFs are sent as-is.
export async function prepareUpload(file: File): Promise<Blob> {
  if (!file.type.startsWith("image/") || (file.size <= 1.5 * 1024 * 1024 && file.type !== "image/heic")) {
    return file;
  }
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 2200 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  return blob ?? file;
}
