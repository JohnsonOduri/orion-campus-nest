import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { slotTimes, todaysClasses, weekTimetable } from "@/lib/mock-data";
import { Download, MapPin, Search } from "lucide-react";

export const Route = createFileRoute("/timetable")({
  head: () => ({
    meta: [
      { title: "Timetable — ORION Campus Companion" },
      { name: "description", content: "Weekly, daily and monthly class schedules with rooms, labs and faculty for IIIT Kottayam." },
      { property: "og:title", content: "ORION Timetable" },
      { property: "og:description", content: "Weekly and daily class schedules with rooms and faculty." },
    ],
  }),
  component: TimetablePage,
});

function TimetablePage() {
  const live = todaysClasses.find((c) => c.status === "live");
  const next = todaysClasses.find((c) => c.status === "upcoming");

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Semester 6"
          title="Timetable"
          subtitle="CSE · Batch 2022–2026 · Section A"
          actions={
            <>
              <Button variant="outline" size="sm">
                <Download className="size-4" /> Export
              </Button>
              <div className="relative hidden sm:block">
                <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input placeholder="Search course" className="h-9 w-48 pl-9" />
              </div>
            </>
          }
        />

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="surface-card p-4">
            <PixelBadge tone="success">Now</PixelBadge>
            <p className="mt-2 text-sm font-semibold">{live?.title ?? "Free period"}</p>
            <p className="font-mono text-xs text-muted-foreground">
              {live ? `${live.time}–${live.end} · ${live.room} · ${live.faculty}` : "Enjoy the break"}
            </p>
          </div>
          <div className="surface-card p-4">
            <PixelBadge>Next</PixelBadge>
            <p className="mt-2 text-sm font-semibold">{next?.title}</p>
            <p className="font-mono text-xs text-muted-foreground">
              {next ? `${next.time}–${next.end} · ${next.room} · ${next.faculty}` : "—"}
            </p>
          </div>
        </div>

        <Tabs defaultValue="week">
          <TabsList>
            <TabsTrigger value="day">Day</TabsTrigger>
            <TabsTrigger value="week">Week</TabsTrigger>
            <TabsTrigger value="month">Month</TabsTrigger>
          </TabsList>

          <TabsContent value="day" className="pt-4">
            <SectionCard title="Tuesday, 04 August" contentClassName="p-0">
              <ul className="divide-y divide-border">
                {todaysClasses.map((c) => (
                  <li key={c.code} className="flex items-center gap-3 p-4">
                    <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">{c.time}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{c.title}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {c.faculty} · <MapPin className="inline size-3" /> {c.room}
                      </p>
                    </div>
                    <PixelBadge tone={c.status === "live" ? "success" : c.status === "done" ? "muted" : "primary"}>
                      {c.status}
                    </PixelBadge>
                  </li>
                ))}
              </ul>
            </SectionCard>
          </TabsContent>

          <TabsContent value="week" className="pt-4">
            <SectionCard contentClassName="p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[46rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      <th className="p-3 text-left font-mono text-[11px] tracking-wider text-muted-foreground uppercase">
                        Day
                      </th>
                      {slotTimes.map((t) => (
                        <th key={t} className="p-3 text-left font-mono text-[11px] text-muted-foreground">
                          {t}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {weekTimetable.map((row) => (
                      <tr key={row.day} className="border-b border-border last:border-0">
                        <td className="p-3 font-semibold">{row.day}</td>
                        {row.slots.map((s, i) => (
                          <td key={i} className="p-2">
                            {s === "—" ? (
                              <span className="text-xs text-muted-foreground">—</span>
                            ) : (
                              <span className="inline-block rounded-md border border-border bg-secondary/50 px-2 py-1.5 font-mono text-[11px] font-medium">
                                {s}
                              </span>
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          </TabsContent>

          <TabsContent value="month" className="pt-4">
            <SectionCard title="August 2026">
              <div className="grid grid-cols-7 gap-1.5 text-center">
                {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                  <span key={i} className="font-mono text-[10px] text-muted-foreground">
                    {d}
                  </span>
                ))}
                {Array.from({ length: 31 }).map((_, i) => (
                  <div
                    key={i}
                    className="aspect-square rounded-md border border-border p-1 text-[11px] transition-colors hover:border-primary"
                  >
                    <span className={i + 1 === 4 ? "font-bold text-primary" : "text-muted-foreground"}>{i + 1}</span>
                    {[3, 17, 19, 21].includes(i) ? (
                      <span className="mx-auto mt-1 block size-1.5 pixelated bg-accent" />
                    ) : null}
                  </div>
                ))}
              </div>
            </SectionCard>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
