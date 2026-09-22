import { createFileRoute, Link } from "@tanstack/react-router";
import { CalendarClock, Info, Sparkles } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, QueryState, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { titleCase, useExams, type CalendarEvent, type ExamRow } from "@/lib/campus";
import { daysFromToday, formatDate, formatTime, relativeDays } from "@/lib/dates";

export const Route = createFileRoute("/exams")({
  head: () => ({
    meta: [
      { title: "Exams — ORION Campus" },
      {
        name: "description",
        content: "Exam windows and published exam schedules for IIIT Kottayam.",
      },
      { property: "og:title", content: "Exams — ORION" },
      { property: "og:description", content: "Exam windows and schedules." },
    ],
  }),
  component: ExamsPage,
});

type Window = { name: string; start: CalendarEvent; end?: CalendarEvent };

// Pairs "X Starts" with the matching "X Ends" event from the calendar.
function windows(events: CalendarEvent[]): Window[] {
  const base = (n: string) =>
    n
      .toLowerCase()
      .replace(/\s*&\s*semester\s+ends?$/, "")
      .replace(/\s+(starts?|begins?|ends?)$/, "")
      .replace(/\bexam\b/, "examination");
  const used = new Set<number>();
  const out: Window[] = [];
  for (const e of events) {
    if (used.has(e.id)) continue;
    used.add(e.id);
    const partner = events.find(
      (x) => !used.has(x.id) && base(x.event_name) === base(e.event_name),
    );
    if (partner) used.add(partner.id);
    out.push({
      name: e.event_name.replace(/\s+(starts?|begins?)$/i, ""),
      start: e,
      ...(partner ? { end: partner } : {}),
    });
  }
  return out;
}

function status(w: Window): { label: string; tone: "danger" | "warning" | "muted" | "primary" } {
  const s = daysFromToday(w.start.event_date);
  const e = w.end ? daysFromToday(w.end.event_date) : s;
  if (e < 0) return { label: "Done", tone: "muted" };
  if (s <= 0) return { label: "Ongoing", tone: "danger" };
  if (s <= 14) return { label: relativeDays(w.start.event_date), tone: "warning" };
  return { label: relativeDays(w.start.event_date), tone: "primary" };
}

function ExamsPage() {
  const query = useExams();
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Odd semester 2026–27"
          title="Exams"
          subtitle="Exam windows from the academic calendar."
          actions={
            <Button asChild size="sm" variant="outline">
              <Link to="/ai" search={{ q: "When do the end semester exams start?" }}>
                <Sparkles className="size-4" /> Ask ORION
              </Link>
            </Button>
          }
        />
        <QueryState
          query={query}
          isEmpty={(d) => d.exams.length === 0 && d.calendar.length === 0}
          emptyTitle="No exam dates yet"
          emptyMessage="Exam dates haven't been published in ORION for this semester."
          skeletonRows={5}
        >
          {(data) => <ExamsBody exams={data.exams} calendar={data.calendar} />}
        </QueryState>
      </div>
    </AppShell>
  );
}

function ExamsBody({ exams, calendar }: { exams: ExamRow[]; calendar: CalendarEvent[] }) {
  const ws = windows(calendar);
  const next = ws.find((w) => daysFromToday((w.end ?? w.start).event_date) >= 0);

  return (
    <div className="space-y-5">
      {next ? (
        <div className="surface-card flex flex-wrap items-center gap-4 p-5">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-destructive/10 text-destructive">
            <CalendarClock className="size-6" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Next exam window
            </p>
            <p className="text-base font-semibold">{next.name}</p>
            <p className="text-sm text-muted-foreground">
              {formatDate(next.start.event_date, { weekday: true })}
              {next.end ? ` – ${formatDate(next.end.event_date, { weekday: true })}` : ""}
            </p>
          </div>
          <PixelBadge tone={status(next).tone}>{status(next).label}</PixelBadge>
        </div>
      ) : null}

      {exams.length === 0 ? (
        <div className="flex gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="text-muted-foreground">
            The exam timetable for individual courses hasn't been published in ORION yet. The
            windows below come from the official academic calendar; your course exams will fall
            inside them.
          </p>
        </div>
      ) : (
        <SectionCard title="Your exam schedule" contentClassName="p-0">
          <ul className="divide-y divide-border">
            {exams.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-3 p-4">
                <span className="font-mono text-xs font-bold text-primary">
                  {e.courses?.course_code}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {titleCase(e.courses?.course_name)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {e.exam_type} · {formatDate(e.exam_date, { weekday: true })}
                    {e.start_time ? ` · ${formatTime(e.start_time)}` : ""}
                    {e.rooms?.room_no ? ` · ${e.rooms.room_no}` : ""}
                  </p>
                </div>
                <PixelBadge tone={daysFromToday(e.exam_date) < 0 ? "muted" : "warning"}>
                  {relativeDays(e.exam_date)}
                </PixelBadge>
              </li>
            ))}
          </ul>
        </SectionCard>
      )}

      <SectionCard title="Exam windows this semester" contentClassName="p-0">
        <ul className="divide-y divide-border">
          {ws.map((w) => {
            const st = status(w);
            return (
              <li
                key={w.start.id}
                className={cn(
                  "flex flex-wrap items-center gap-3 p-4",
                  st.label === "Done" && "opacity-60",
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{w.name}</p>
                  <p className="font-mono text-xs text-muted-foreground">
                    {formatDate(w.start.event_date, { weekday: true })}
                    {w.end ? ` – ${formatDate(w.end.event_date, { weekday: true })}` : ""}
                  </p>
                </div>
                <PixelBadge tone={st.tone}>{st.label}</PixelBadge>
              </li>
            );
          })}
        </ul>
      </SectionCard>
    </div>
  );
}
