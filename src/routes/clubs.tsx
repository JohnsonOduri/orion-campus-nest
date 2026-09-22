import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Info, Sparkles, Users } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { CardSkeleton, PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Button } from "@/components/ui/button";
import { apiGet } from "@/lib/api-client";
import { useCalendar } from "@/lib/campus";
import { daysFromToday, formatDate, formatTime, relativeDays } from "@/lib/dates";
import type { StudentContext, TimetableEntry } from "@/lib/timetable";

export const Route = createFileRoute("/clubs")({
  head: () => ({
    meta: [
      { title: "Clubs & Events — ORION Campus" },
      {
        name: "description",
        content:
          "Club activity slots in your timetable and campus events from the academic calendar.",
      },
      { property: "og:title", content: "Clubs & Events — ORION" },
      { property: "og:description", content: "Club slots and campus events." },
    ],
  }),
  component: ClubsPage,
});

// The timetable stores day_of_week as ISO (1 = Monday … 7 = Sunday).
const ISO_DAY = ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type Entry = TimetableEntry & { source_text?: string | null };

function ClubsPage() {
  const week = useQuery({
    queryKey: ["timetable", "week"],
    queryFn: () => apiGet<{ student: StudentContext | null; entries: Entry[] }>("/timetable/week"),
  });
  const calendar = useCalendar();

  const clubSlots = (week.data?.entries ?? []).filter(
    (e) => e.entry_type === "club_activity" || e.entry_type === "sports",
  );
  const byName = new Map<string, Entry[]>();
  for (const e of clubSlots) {
    const name =
      e.source_text || e.course_name || (e.entry_type === "sports" ? "Sports" : "Club activity");
    byName.set(name, [...(byName.get(name) ?? []), e]);
  }
  const events = (calendar.data ?? []).filter(
    (e) => ["event", "sports"].includes(e.event_type) && daysFromToday(e.event_date) >= -7,
  );

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Campus life"
          title="Clubs & Events"
          subtitle="Club time in your week and campus events."
        />

        <div className="flex gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="text-muted-foreground">
            Club memberships and club event sign-ups aren't in ORION yet. Below are the club slots
            your timetable reserves and the events on the academic calendar.
          </p>
        </div>

        <SectionCard title="Club slots in your week">
          {week.isLoading ? (
            <CardSkeleton rows={3} />
          ) : week.isError ? (
            <p className="text-sm text-muted-foreground">
              Couldn't load your timetable. Try again in a moment.
            </p>
          ) : byName.size === 0 ? (
            <p className="text-sm text-muted-foreground">
              Your timetable doesn't reserve any club time this week.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {[...byName.entries()].map(([name, slots]) => (
                <article key={name} className="rounded-2xl border border-border p-4">
                  <div className="flex items-center gap-2">
                    <Users className="size-4 text-primary" />
                    <h3 className="text-sm font-semibold">{name}</h3>
                  </div>
                  <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                    {slots
                      .sort(
                        (a, b) =>
                          a.day_of_week - b.day_of_week ||
                          (a.start_time ?? "").localeCompare(b.start_time ?? ""),
                      )
                      .map((s) => (
                        <li key={s.id}>
                          {ISO_DAY[s.day_of_week] ?? ""} · {formatTime(s.start_time)} –{" "}
                          {formatTime(s.end_time)}
                        </li>
                      ))}
                  </ul>
                </article>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Campus events" contentClassName="p-0">
          {calendar.isLoading ? (
            <div className="p-4">
              <CardSkeleton rows={2} />
            </div>
          ) : events.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              No campus events on the calendar right now.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {events.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center gap-3 p-4">
                  <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-secondary/60">
                    <CalendarDays className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{e.event_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDate(e.event_date, { weekday: true })}
                    </p>
                  </div>
                  <PixelBadge tone={daysFromToday(e.event_date) < 0 ? "muted" : "primary"}>
                    {relativeDays(e.event_date)}
                  </PixelBadge>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <Button asChild variant="outline" size="sm">
          <Link to="/ai" search={{ q: "When is the sports meet?" }}>
            <Sparkles className="size-4" /> Ask ORION about events
          </Link>
        </Button>
      </div>
    </AppShell>
  );
}
