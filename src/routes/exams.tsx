import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { exams } from "@/lib/mock-data";
import { Download, MapPin, Timer } from "lucide-react";

export const Route = createFileRoute("/exams")({
  head: () => ({
    meta: [
      { title: "Exams & Hall Tickets — ORION Campus" },
      { name: "description", content: "Upcoming exams, venues, seat numbers, countdowns, hall tickets and past results." },
      { property: "og:title", content: "Exams — ORION" },
      { property: "og:description", content: "Hall tickets, venues, seat numbers and results." },
    ],
  }),
  component: ExamsPage,
});

function ExamsPage() {
  const upcoming = exams.filter((e) => e.status === "upcoming");
  const completed = exams.filter((e) => e.status === "completed");

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Mid-semester"
          title="Exams"
          subtitle="Reporting time is 30 minutes before each session."
          actions={
            <Button size="sm">
              <Download className="size-4" /> Hall ticket
            </Button>
          }
        />

        <div className="surface-card flex flex-wrap items-center gap-4 p-5">
          <PixelSprite size={5} rows={[...SPRITES.trophy]} />
          <div>
            <p className="text-sm font-semibold">First exam in 14 days</p>
            <p className="font-mono text-xs text-muted-foreground">CS304 · 18 Aug 2026 · 09:30 · Hall A · Seat A-42</p>
          </div>
          <PixelBadge tone="warning" className="ml-auto">
            <Timer className="size-3" /> Countdown active
          </PixelBadge>
        </div>

        <Tabs defaultValue="upcoming">
          <TabsList>
            <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
            <TabsTrigger value="completed">Results</TabsTrigger>
          </TabsList>

          <TabsContent value="upcoming" className="grid gap-3 pt-4 sm:grid-cols-2 lg:grid-cols-3">
            {upcoming.map((e) => (
              <div key={e.code} className="surface-card hover-lift p-4">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-primary">{e.code}</span>
                  <PixelBadge tone="primary">{e.date}</PixelBadge>
                </div>
                <p className="mt-2 text-sm font-semibold">{e.title}</p>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">{e.time}</p>
                <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                  <MapPin className="size-3.5" /> {e.venue} · Seat {e.seat}
                </p>
              </div>
            ))}
          </TabsContent>

          <TabsContent value="completed" className="pt-4">
            <SectionCard contentClassName="p-0">
              <ul className="divide-y divide-border">
                {completed.map((e) => (
                  <li key={e.code} className="flex items-center gap-3 p-4">
                    <span className="font-mono text-xs font-bold text-primary">{e.code}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{e.title}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {e.date} · {e.venue}
                      </p>
                    </div>
                    <PixelBadge tone="success">{e.grade}</PixelBadge>
                  </li>
                ))}
              </ul>
            </SectionCard>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}
