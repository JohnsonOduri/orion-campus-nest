import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api-client";

// Types + query hooks for the read-only campus endpoints
// (backend/app/api/campus.py). The same data the assistant answers from.

export type CalendarEvent = {
  id: number;
  event_name: string;
  event_date: string;
  event_type: string;
  source_id: string | null;
};

export type ExamRow = {
  id: number;
  exam_type: string;
  exam_date: string;
  start_time: string | null;
  end_time: string | null;
  courses: { course_code: string; course_name: string } | null;
  rooms: { room_no: string } | null;
};

export type Course = {
  id: number;
  course_code: string;
  course_name: string;
  credits: number | null;
  programme: string | null;
  specialisation: string | null;
  semester: number | null;
  prerequisites: string | null;
  syllabus_summary: string | null;
};

export type MyCourse = {
  course_code: string;
  course_name: string;
  faculty: string[];
  types: string[];
  sessions: number;
  curriculum: {
    lecture: number;
    tutorial: number;
    practical: number;
    credits: number;
    document_title: string;
    page: number | null;
  } | null;
};

export type DocumentMeta = {
  id: number;
  title: string;
  document_type: string | null;
  category: string | null;
  programme: string | null;
  cohort: string | null;
  valid_from: string | null;
  valid_until: string | null;
  published_at: string | null;
};

export type MyAcademic = {
  cohort_family: string | null;
  regulations: string | null;
  classroom: { room_no: string; room_type: string | null } | null;
};

const TEN_MIN = 10 * 60_000;

export const useCalendar = () =>
  useQuery({
    queryKey: ["calendar"],
    queryFn: () => apiGet<CalendarEvent[]>("/calendar"),
    staleTime: TEN_MIN,
  });

export const useExams = () =>
  useQuery({
    queryKey: ["exams"],
    queryFn: () => apiGet<{ exams: ExamRow[]; calendar: CalendarEvent[] }>("/exams"),
    staleTime: TEN_MIN,
  });

export const useCourseCatalog = () =>
  useQuery({
    queryKey: ["courses"],
    queryFn: () => apiGet<Course[]>("/courses"),
    staleTime: TEN_MIN,
  });

export const useMyCourses = () =>
  useQuery({
    queryKey: ["courses", "mine"],
    queryFn: () => apiGet<MyCourse[]>("/courses/mine"),
    staleTime: TEN_MIN,
  });

export const useDocuments = () =>
  useQuery({
    queryKey: ["documents"],
    queryFn: () => apiGet<DocumentMeta[]>("/documents"),
    staleTime: TEN_MIN,
  });

export const useMyAcademic = () =>
  useQuery({
    queryKey: ["me", "academic"],
    queryFn: () => apiGet<MyAcademic>("/me/academic"),
    staleTime: TEN_MIN,
  });

export function titleCase(text: string | null | undefined): string {
  if (!text) return "";
  if (text !== text.toUpperCase()) return text;
  const small = new Set(["and", "of", "the", "in", "for", "to", "with", "on", "a", "an", "or"]);
  const keep = new Set([
    "IT",
    "AI",
    "ML",
    "II",
    "III",
    "IV",
    "VLSI",
    "IOT",
    "NLP",
    "DBMS",
    "OS",
    "CSE",
    "ECE",
  ]);
  return text
    .split(/\s+/)
    .map((w, i) => {
      if (keep.has(w)) return w;
      const lower = w.toLowerCase();
      if (i > 0 && small.has(lower)) return lower;
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}
