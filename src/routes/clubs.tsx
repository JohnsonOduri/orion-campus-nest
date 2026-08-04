import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { clubs, events } from "@/lib/mock-data";
import { CalendarDays, MapPin, Users } from "lucide-react";

export const Route = createFileRoute("/clubs")({
  head: () => ({
    meta: [
      { title: "Clubs & Events — ORION Campus" },
      { name: "description", content: "Discover IIIT Kottayam clubs, memberships and upcoming campus events with registration." },
      { property: "og:title", content: "Clubs & Events — ORION" },
      { property: "og:description", content: "Clubs, memberships and upcoming campus events." },
    ],
  }),
  component: ClubsPage,
});

function ClubsPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Campus life" title="Clubs & Events" subtitle="Six active clubs · four upcoming events." />

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {clubs.map((c) => (
            <article key={c.name} className="surface-card hover-lift pixel-corners p-4">
              <div className="flex items-start justify-between">
                <PixelSprite size={4} rows={[...SPRITES.star]} />
                <PixelBadge tone="muted">{c.category}</PixelBadge>
              </div>
              <h2 className="mt-3 text-sm font-semibold">{c.name}</h2>
              <p className="mt-1 text-xs text-muted-foreground">{c.desc}</p>
              <div className="mt-3 flex items-center justify-between">
                <span className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground">
                  <Users className="size-3.5" /> {c.members}
                </span>
                <Button size="sm" variant={c.joined ? "outline" : "default"}>
                  {c.joined ? "Joined" : "Join"}
                </Button>
              </div>
            </article>
          ))}
        </div>

        <SectionCard title="Upcoming events" contentClassName="p-0">
          <ul className="divide-y divide-border">
            {events.map((e) => (
              <li key={e.name} className="flex flex-wrap items-center gap-3 p-4">
                <div className="grid size-12 shrink-0 place-items-center rounded-xl bg-secondary/60">
                  <span className="font-mono text-[11px] font-bold">{e.date}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold">{e.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    <CalendarDays className="inline size-3" /> {e.time} · <MapPin className="inline size-3" /> {e.venue}
                  </p>
                </div>
                <PixelBadge>{e.tag}</PixelBadge>
                <Button size="sm" variant="outline">
                  Register
                </Button>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>
    </AppShell>
  );
}
