import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/shared/primitives";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { courses } from "@/lib/mock-data";

export const Route = createFileRoute("/courses")({
  head: () => ({
    meta: [
      { title: "Courses — ORION Campus Companion" },
      { name: "description", content: "Enrolled courses with credits, faculty, attendance, assignments and resources." },
      { property: "og:title", content: "Courses — ORION" },
      { property: "og:description", content: "Credits, faculty, attendance and assignments per course." },
    ],
  }),
  component: CoursesPage,
});

function CoursesPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="18 credits" title="Courses" subtitle="Semester 6 · Computer Science & Engineering" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {courses.map((c) => (
            <article key={c.code} className="surface-card hover-lift pixel-corners flex flex-col p-4">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold text-primary">{c.code}</span>
                <PixelBadge tone="muted">{c.credits} cr</PixelBadge>
              </div>
              <h2 className="mt-2 text-sm font-semibold">{c.title}</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{c.faculty}</p>
              <div className="mt-3 space-y-2">
                <div>
                  <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
                    <span>Attendance</span>
                    <span>{c.attendance}%</span>
                  </div>
                  <Progress value={c.attendance} className="mt-1 h-1.5" />
                </div>
                <div>
                  <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
                    <span>Syllabus</span>
                    <span>{c.progress}%</span>
                  </div>
                  <Progress value={c.progress} className="mt-1 h-1.5" />
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <PixelBadge tone={c.assignments ? "warning" : "success"}>
                  {c.assignments} open tasks
                </PixelBadge>
                <Button variant="ghost" size="sm">
                  Resources
                </Button>
              </div>
            </article>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
