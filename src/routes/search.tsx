import { useMemo } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, CalendarDays, FileText, Megaphone, Search, Sparkles, Users } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { apiGet } from "@/lib/api-client";
import { titleCase, useCalendar, useCourseCatalog, useDocuments } from "@/lib/campus";
import { formatDate } from "@/lib/dates";

type FacultyMember = {
  id: number;
  full_name: string;
  designation: string | null;
  research_interests: string | null;
};
type Announcement = { id: number; title: string; content: string };

export const Route = createFileRoute("/search")({
  head: () => ({
    meta: [
      { title: "Search — ORION Campus Companion" },
      {
        name: "description",
        content: "Search faculty, courses, dates, notices and documents across IIIT Kottayam.",
      },
      { property: "og:title", content: "Search — ORION" },
      { property: "og:description", content: "One search box for the whole campus." },
    ],
  }),
  validateSearch: (search: Record<string, unknown>): { q?: string } => {
    const q = search["q"];
    return typeof q === "string" ? { q: q.slice(0, 200) } : {};
  },
  component: SearchPage,
});

type Hit = { key: string; title: string; detail?: string; to: string; search?: { q?: string } };

function matches(text: string | null | undefined, terms: string[]): boolean {
  const t = (text ?? "").toLowerCase();
  return terms.every((term) => t.includes(term));
}

function SearchPage() {
  const { q = "" } = Route.useSearch();
  const navigate = useNavigate();
  const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);

  const faculty = useQuery({
    queryKey: ["faculty"],
    queryFn: () => apiGet<FacultyMember[]>("/faculty"),
  });
  const announcements = useQuery({
    queryKey: ["announcements"],
    queryFn: () => apiGet<Announcement[]>("/announcements"),
  });
  const courses = useCourseCatalog();
  const calendar = useCalendar();
  const documents = useDocuments();
  const loading = [faculty, announcements, courses, calendar, documents].some((x) => x.isLoading);

  const groups = useMemo(() => {
    if (!terms.length) return [];
    const g: { label: string; icon: typeof Users; hits: Hit[] }[] = [
      {
        label: "Faculty",
        icon: Users,
        hits: (faculty.data ?? [])
          .filter((f) =>
            matches(`${f.full_name} ${f.designation ?? ""} ${f.research_interests ?? ""}`, terms),
          )
          .slice(0, 6)
          .map((f) => ({
            key: `f${f.id}`,
            title: f.full_name,
            detail: f.designation ?? undefined,
            to: "/ai",
            search: { q: `Tell me about ${f.full_name}` },
          })),
      },
      {
        label: "Courses",
        icon: BookOpen,
        hits: (courses.data ?? [])
          .filter((c) => matches(`${c.course_code} ${c.course_name}`, terms))
          .slice(0, 6)
          .map((c) => ({
            key: `c${c.id}`,
            title: `${c.course_code} · ${titleCase(c.course_name)}`,
            detail: c.semester ? `Semester ${c.semester}` : undefined,
            to: "/ai",
            search: { q: `Tell me about ${c.course_code}` },
          })),
      },
      {
        label: "Dates",
        icon: CalendarDays,
        hits: (calendar.data ?? [])
          .filter((e) => matches(e.event_name, terms))
          .slice(0, 6)
          .map((e) => ({
            key: `e${e.id}`,
            title: e.event_name,
            detail: formatDate(e.event_date, { weekday: true }),
            to: "/calendar",
          })),
      },
      {
        label: "Announcements",
        icon: Megaphone,
        hits: (announcements.data ?? [])
          .filter((a) => matches(`${a.title} ${a.content}`, terms))
          .slice(0, 6)
          .map((a) => ({ key: `a${a.id}`, title: a.title, to: "/announcements" })),
      },
      {
        label: "Documents",
        icon: FileText,
        hits: (documents.data ?? [])
          .filter((d) => matches(d.title, terms))
          .slice(0, 6)
          .map((d) => ({ key: `d${d.id}`, title: d.title, to: "/documents" })),
      },
    ];
    return g.filter((x) => x.hits.length);
  }, [terms, faculty.data, courses.data, calendar.data, announcements.data, documents.data]);

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Campus"
          title="Search"
          subtitle="Faculty, courses, dates, notices and documents."
        />
        <div className="relative">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            autoFocus
            value={q}
            onChange={(e) =>
              void navigate({ to: "/search", search: { q: e.target.value }, replace: true })
            }
            placeholder="Try “machine learning”, “end semester” or “ICS 213”"
            aria-label="Search campus"
            className="h-11 pl-9 text-base md:text-sm"
          />
        </div>

        {terms.length ? (
          <Link
            to="/ai"
            search={{ q }}
            className="flex items-center gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-4 text-sm transition-colors hover:bg-primary/10"
          >
            <Sparkles className="size-4 shrink-0 text-primary" />
            <span>
              Ask ORION: <span className="font-medium">“{q}”</span>
            </span>
          </Link>
        ) : (
          <p className="text-sm text-muted-foreground">
            Start typing to search across campus data.
          </p>
        )}

        {terms.length && !loading && groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing matches “{q}”. Try fewer words, or ask ORION above.
          </p>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <SectionCard key={g.label} title={g.label} contentClassName="p-0">
              <ul className="divide-y divide-border">
                {g.hits.map((h) => (
                  <li key={h.key}>
                    <Link
                      to={h.to}
                      {...(h.search ? { search: h.search } : {})}
                      className="flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-muted/50"
                    >
                      <g.icon className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">{h.title}</span>
                      {h.detail ? (
                        <span className="shrink-0 text-xs text-muted-foreground">{h.detail}</span>
                      ) : null}
                    </Link>
                  </li>
                ))}
              </ul>
            </SectionCard>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
