import { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CalendarClock, Sparkles } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, QueryState, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCalendar, type CalendarEvent } from "@/lib/campus";
import { daysFromToday, formatDate, parseDate, relativeDays } from "@/lib/dates";

export const Route = createFileRoute("/calendar")({
  head: () => ({
    meta: [
      { title: "Academic Calendar — ORION Campus" },
      {
        name: "description",
        content: "Exams, deadlines and key dates from IIIT Kottayam's academic calendar.",
      },
      { property: "og:title", content: "Academic Calendar — ORION" },
      { property: "og:description", content: "Exams, deadlines and key dates for the semester." },
    ],
  }),
  component: CalendarPage,
});

const FILTERS = [
  { key: "all", label: "All" },
  { key: "exam", label: "Exams" },
  { key: "deadline", label: "Deadlines" },
  { key: "term", label: "Term dates" },
  { key: "other", label: "Events & meetings" },
] as const;
type FilterKey = (typeof FILTERS)[number]["key"];

function group(e: CalendarEvent): Exclude<FilterKey, "all"> {
  if (e.event_type === "exam" || e.event_type === "result") return "exam";
  if (e.event_type === "deadline" || e.event_type === "registration") return "deadline";
  if (e.event_type === "term_milestone") return "term";
  return "other";
}

const TONE: Record<Exclude<FilterKey, "all">, "danger" | "warning" | "primary" | "muted"> = {
  exam: "danger",
  deadline: "warning",
  term: "primary",
  other: "muted",
};

const KEY_DATES: { label: string; match: RegExp }[] = [
  { label: "Classes began", match: /class begins|1st instructional day/i },
  { label: "Mid-semester exams", match: /mid semester examination starts/i },
  { label: "Last instructional day", match: /^class ends$/i },
  { label: "End-semester exams", match: /end semester examination starts/i },
  { label: "Semester ends", match: /semester ends/i },
  { label: "Results", match: /^result publication$/i },
  { label: "Even semester begins", match: /even semester .*classes begin/i },
];

function CalendarPage() {
  const query = useCalendar();
  const [filter, setFilter] = useState<FilterKey>("all");

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Odd semester 2026–27"
          title="Academic Calendar"
          subtitle="Official dates from the Academic Section."
          actions={
            <Button asChild size="sm" variant="outline">
              <Link to="/ai" search={{ q: "What's coming up on the academic calendar?" }}>
                <Sparkles className="size-4" /> Ask ORION
              </Link>
            </Button>
          }
        />
        <QueryState
          query={query}
          isEmpty={(d) => d.length === 0}
          emptyTitle="No calendar yet"
          emptyMessage="The academic calendar for this semester hasn't been published in ORION."
          skeletonRows={8}
        >
          {(events) => <CalendarBody events={events} filter={filter} setFilter={setFilter} />}
        </QueryState>
      </div>
    </AppShell>
  );
}

function CalendarBody({
  events,
  filter,
  setFilter,
}: {
  events: CalendarEvent[];
  filter: FilterKey;
  setFilter: (f: FilterKey) => void;
}) {
  const next = events.find((e) => daysFromToday(e.event_date) >= 0);
  const visible = filter === "all" ? events : events.filter((e) => group(e) === filter);
  const byMonth = useMemo(() => {
    const m = new Map<string, CalendarEvent[]>();
    for (const e of visible) {
      const key = parseDate(e.event_date).toLocaleDateString("en-IN", {
        month: "long",
        year: "numeric",
      });
      m.set(key, [...(m.get(key) ?? []), e]);
    }
    return [...m.entries()];
  }, [visible]);

  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        {next ? (
          <div className="surface-card flex items-center gap-4 p-5">
            <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
              <CalendarClock className="size-6" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Next up
              </p>
              <p className="truncate text-base font-semibold">{next.event_name}</p>
              <p className="text-sm text-muted-foreground">
                {formatDate(next.event_date, { weekday: true })} · {relativeDays(next.event_date)}
              </p>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter events">
          {FILTERS.map((f) => (
            <Button
              key={f.key}
              size="sm"
              variant={filter === f.key ? "default" : "outline"}
              className="h-9 rounded-full"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
            </Button>
          ))}
        </div>

        <SectionCard title="Semester timeline">
          {byMonth.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events of this type.</p>
          ) : (
            <div className="space-y-6">
              {byMonth.map(([month, items]) => (
                <section key={month}>
                  <h3 className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    {month}
                  </h3>
                  <ol className="relative space-y-4 border-l border-border pl-5">
                    {items.map((e) => {
                      const past = daysFromToday(e.event_date) < 0;
                      const isNext = next?.id === e.id;
                      return (
                        <li key={e.id} className={cn("relative", past && "opacity-55")}>
                          <span
                            className={cn(
                              "absolute top-1.5 -left-[25px] size-2.5 rounded-full",
                              isNext
                                ? "bg-primary ring-4 ring-primary/20"
                                : past
                                  ? "bg-muted-foreground/40"
                                  : "bg-primary",
                            )}
                          />
                          <div className="flex flex-wrap items-baseline gap-x-2">
                            <p className="font-mono text-xs text-muted-foreground">
                              {formatDate(e.event_date, { weekday: true })}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              · {past ? "done" : relativeDays(e.event_date)}
                            </p>
                          </div>
                          <p className="mt-0.5 text-sm font-medium">{e.event_name}</p>
                          <PixelBadge tone={TONE[group(e)]} className="mt-1.5">
                            {e.event_type.replace("_", " ")}
                          </PixelBadge>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Key dates">
        <dl className="space-y-3 text-sm">
          {KEY_DATES.map(({ label, match }) => {
            const e = events.find((x) => match.test(x.event_name));
            if (!e) return null;
            return (
              <div key={label} className="flex items-center justify-between gap-3">
                <dt className="text-muted-foreground">{label}</dt>
                <dd
                  className={cn(
                    "text-right font-mono text-xs font-medium",
                    daysFromToday(e.event_date) < 0 && "text-muted-foreground",
                  )}
                >
                  {formatDate(e.event_date)}
                </dd>
              </div>
            );
          })}
        </dl>
        <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
          Source: {events[0]?.source_id ?? "academic calendar"}. The calendar in ORION lists no
          holidays for this semester.
        </p>
        <Button asChild variant="link" size="sm" className="mt-1 h-auto px-0">
          <Link to="/ai" search={{ q: "What are the upcoming deadlines?" }}>
            Ask ORION about upcoming deadlines →
          </Link>
        </Button>
      </SectionCard>
    </div>
  );
}
