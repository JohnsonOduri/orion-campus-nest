import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader, SectionCard } from "@/components/shared/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { MapPin } from "lucide-react";
import { apiGet } from "@/lib/api-client";
import {
  DAY_NAMES,
  deriveStatus,
  entryLabel,
  formatTime,
  todaysEntries,
  type StudentContext,
  type TimetableEntry,
} from "@/lib/timetable";

export const Route = createFileRoute("/timetable")({
  head: () => ({
    meta: [
      { title: "Timetable — ORION Campus Companion" },
      { name: "description", content: "Weekly and daily class schedules with rooms, labs and faculty for IIIT Kottayam." },
      { property: "og:title", content: "ORION Timetable" },
      { property: "og:description", content: "Weekly and daily class schedules with rooms and faculty." },
    ],
  }),
  component: TimetablePage,
});

type TimetableResponse = { student: StudentContext | null; entries: TimetableEntry[] };

function TimetablePage() {
  const dayQuery = useQuery({
    queryKey: ["timetable", "day"],
    queryFn: () => apiGet<TimetableResponse>("/timetable/day"),
  });
  const weekQuery = useQuery({
    queryKey: ["timetable", "week"],
    queryFn: () => apiGet<TimetableResponse>("/timetable/week"),
  });

  const now = new Date();
  const dayEntries = todaysEntries(dayQuery.data?.entries ?? [], now);
  const withStatus = dayEntries.map((e) => ({ entry: e, status: e._cancelled ? null : deriveStatus(e, now) }));
  const live = withStatus.find((x) => x.status === "live")?.entry;
  const next = withStatus.find((x) => x.status === "upcoming")?.entry;

  const student = dayQuery.data?.student ?? weekQuery.data?.student ?? null;
  const subtitle = student
    ? `${student.department} · Semester ${student.semester} · Batch ${student.batch} · Section ${student.section}`
    : "";

  const weekEntries = weekQuery.data?.entries ?? [];
  const days = Array.from(new Set(weekEntries.map((e) => e.day_of_week))).sort((a, b) => a - b);
  const slots = Array.from(new Set(weekEntries.map((e) => e.slot_index))).sort((a, b) => a - b);
  const slotLabel = (slot: number) => {
    const sample = weekEntries.find((e) => e.slot_index === slot && e.start_time && e.end_time);
    return sample ? `${formatTime(sample.start_time)}–${formatTime(sample.end_time)}` : `Slot ${slot}`;
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Timetable" title="Timetable" subtitle={subtitle} />

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="surface-card p-4">
            <PixelBadge tone="success">Now</PixelBadge>
            <p className="mt-2 text-sm font-semibold">{live ? entryLabel(live) : "Free period"}</p>
            <p className="font-mono text-xs text-muted-foreground">
              {live
                ? `${formatTime(live.start_time)}–${formatTime(live.end_time)} · ${live.room ?? "—"} · ${(live.faculty_names ?? []).join(", ") || "—"}`
                : "Enjoy the break"}
            </p>
          </div>
          <div className="surface-card p-4">
            <PixelBadge>Next</PixelBadge>
            <p className="mt-2 text-sm font-semibold">{next ? entryLabel(next) : "—"}</p>
            <p className="font-mono text-xs text-muted-foreground">
              {next
                ? `${formatTime(next.start_time)}–${formatTime(next.end_time)} · ${next.room ?? "—"} · ${(next.faculty_names ?? []).join(", ") || "—"}`
                : "—"}
            </p>
          </div>
        </div>

        <Tabs defaultValue="week">
          <TabsList>
            <TabsTrigger value="day">Day</TabsTrigger>
            <TabsTrigger value="week">Week</TabsTrigger>
          </TabsList>

          <TabsContent value="day" className="pt-4">
            <SectionCard title={DAY_NAMES[now.getDay()] ?? "Today"} contentClassName="p-0">
              {dayQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : dayEntries.length === 0 ? (
                <EmptyState title="No classes today" message="Nothing scheduled for today." />
              ) : (
                <ul className="divide-y divide-border">
                  {withStatus.map(({ entry: c, status }) => (
                    <li key={c.id} className="flex items-center gap-3 p-4">
                      <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">
                        {formatTime(c.start_time)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className={`truncate text-sm font-medium ${c._cancelled ? "text-muted-foreground line-through" : ""}`}>
                          {entryLabel(c)} {c.course_name && <span className="text-xs text-muted-foreground">{c.course_name}</span>}
                        </p>
                        {c._cancelled || c._extra || c._moved_from ? (
                          <p className="text-[11px] font-medium text-warning-foreground">
                            {c._cancelled
                              ? `Cancelled${c._change_note ? ` — ${c._change_note}` : ""}`
                              : c._moved_from
                                ? `Rescheduled here from ${c._moved_from}`
                                : "Extra class"}
                          </p>
                        ) : null}
                        <p className="truncate text-xs text-muted-foreground">
                          {(c.faculty_names ?? []).join(", ") || "—"} · <MapPin className="inline size-3" /> {c.room ?? "—"}
                        </p>
                      </div>
                      {status && (
                        <PixelBadge tone={status === "live" ? "success" : status === "done" ? "muted" : "primary"}>
                          {status}
                        </PixelBadge>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </TabsContent>

          <TabsContent value="week" className="pt-4">
            <SectionCard contentClassName="p-0">
              {weekQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : days.length === 0 ? (
                <EmptyState title="No timetable found" message="Nothing scheduled for this week." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[46rem] border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/40">
                        <th className="p-3 text-left font-mono text-[11px] tracking-wider text-muted-foreground uppercase">
                          Day
                        </th>
                        {slots.map((slot) => (
                          <th key={slot} className="p-3 text-left font-mono text-[11px] text-muted-foreground">
                            {slotLabel(slot)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {days.map((day) => (
                        <tr key={day} className="border-b border-border last:border-0">
                          <td className="p-3 font-semibold">{DAY_NAMES[day]}</td>
                          {slots.map((slot) => {
                            const cellEntries = weekEntries.filter(
                              (e) => e.day_of_week === day && e.slot_index === slot,
                            );
                            return (
                              <td key={slot} className="p-2">
                                {cellEntries.length === 0 ? (
                                  <span className="text-xs text-muted-foreground">—</span>
                                ) : (
                                  <div className="flex flex-col gap-1">
                                    {cellEntries.map((e) => (
                                      <span
                                        key={e.id}
                                        title={e._cancelled ? "Cancelled this week" : e._extra ? "Extra class" : e._moved_from ? `Moved from ${e._moved_from}` : undefined}
                                        className={`inline-block rounded-md border px-2 py-1.5 font-mono text-[11px] font-medium ${
                                          e._cancelled
                                            ? "border-destructive/40 bg-destructive/5 text-muted-foreground line-through"
                                            : e._extra || e._moved_from
                                              ? "border-warning bg-warning/10"
                                              : "border-border bg-secondary/50"
                                        }`}
                                      >
                                        {entryLabel(e)}
                                        {e._extra ? " +" : ""}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
