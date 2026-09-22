import { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, QueryState, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/hooks/use-profile";
import {
  titleCase,
  useCourseCatalog,
  useMyCourses,
  type Course,
  type MyCourse,
} from "@/lib/campus";

export const Route = createFileRoute("/courses")({
  head: () => ({
    meta: [
      { title: "Courses — ORION Campus" },
      {
        name: "description",
        content:
          "Your courses this semester, their teachers and credits, and the full course catalog.",
      },
      { property: "og:title", content: "Courses — ORION" },
      { property: "og:description", content: "Your courses, teachers and credits." },
    ],
  }),
  component: CoursesPage,
});

function CoursesPage() {
  const { data: profile } = useProfile();
  const mine = useMyCourses();
  const catalog = useCourseCatalog();
  const totalCredits = (mine.data ?? []).reduce((sum, c) => sum + (c.curriculum?.credits ?? 0), 0);

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge={totalCredits ? `${totalCredits} credits` : "This semester"}
          title="Courses"
          subtitle={
            profile?.semester
              ? `Semester ${profile.semester} · ${titleCase(profile.department)} · section ${profile.section}`
              : "Your courses this semester"
          }
        />

        <SectionCard
          title="My courses"
          description="From your live timetable. Credits from your programme's curriculum."
        >
          <QueryState
            query={mine}
            isEmpty={(d) => d.length === 0}
            emptyTitle="No courses found"
            emptyMessage="Your timetable doesn't list any courses yet. Check that your registration details are right."
          >
            {(courses) => (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {courses.map((c) => (
                  <MyCourseCard key={c.course_code} course={c} />
                ))}
              </div>
            )}
          </QueryState>
        </SectionCard>

        <SectionCard title="Course catalog" description="Every active course in ORION.">
          <QueryState
            query={catalog}
            isEmpty={(d) => d.length === 0}
            emptyTitle="Catalog is empty"
            emptyMessage="No courses have been published yet."
          >
            {(courses) => <Catalog courses={courses} />}
          </QueryState>
        </SectionCard>
      </div>
    </AppShell>
  );
}

function MyCourseCard({ course: c }: { course: MyCourse }) {
  const kinds = c.types.filter((t) => t !== "class");
  return (
    <article className="flex flex-col rounded-2xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-bold text-primary">{c.course_code}</span>
        {c.curriculum ? (
          <PixelBadge tone="muted">
            {c.curriculum.credits} cr · {c.curriculum.lecture}-{c.curriculum.tutorial}-
            {c.curriculum.practical}
          </PixelBadge>
        ) : null}
      </div>
      <h3 className="mt-2 text-sm font-semibold">{titleCase(c.course_name)}</h3>
      {c.faculty.length ? (
        <p className="mt-1 text-xs text-muted-foreground">{c.faculty.join(", ")}</p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <PixelBadge tone="primary">{c.sessions} sessions/week</PixelBadge>
        {kinds.map((k) => (
          <PixelBadge key={k} tone="muted">
            {k}
          </PixelBadge>
        ))}
      </div>
      <Button asChild variant="ghost" size="sm" className="mt-3 -ml-2 w-fit">
        <Link to="/ai" search={{ q: `Tell me about ${c.course_code}` }}>
          <Sparkles className="size-3.5" /> Ask ORION
        </Link>
      </Button>
    </article>
  );
}

function Catalog({ courses }: { courses: Course[] }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return courses;
    return courses.filter((c) => `${c.course_code} ${c.course_name}`.toLowerCase().includes(q));
  }, [courses, query]);
  const bySemester = useMemo(() => {
    const m = new Map<number, Course[]>();
    for (const c of filtered) m.set(c.semester ?? 0, [...(m.get(c.semester ?? 0) ?? []), c]);
    return [...m.entries()].sort(([a], [b]) => a - b);
  }, [filtered]);

  return (
    <div className="space-y-4">
      <div className="relative max-w-md">
        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by code or name"
          aria-label="Search the course catalog"
          className="h-10 pl-9"
        />
      </div>
      {bySemester.length === 0 ? (
        <p className="text-sm text-muted-foreground">No course matches “{query}”.</p>
      ) : (
        bySemester.map(([sem, list]) => (
          <section key={sem}>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              {sem ? `Semester ${sem}` : "Other"}
            </h3>
            <ul className="divide-y divide-border rounded-2xl border border-border">
              {list.map((c) => (
                <li key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                  <span className="w-20 shrink-0 font-mono text-xs font-semibold text-primary">
                    {c.course_code}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{titleCase(c.course_name)}</span>
                  {c.credits != null ? (
                    <span className="text-xs text-muted-foreground">{c.credits} cr</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
