import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader, SectionCard } from "@/components/shared/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { apiGet } from "@/lib/api-client";

export const Route = createFileRoute("/mess")({
  head: () => ({
    meta: [
      { title: "Mess Schedule — ORION Campus" },
      { name: "description", content: "Weekly mess menu at IIIT Kottayam." },
      { property: "og:title", content: "Mess Schedule — ORION" },
      { property: "og:description", content: "Menus by day of the week." },
    ],
  }),
  component: MessPage,
});

type MessRow = {
  id: number;
  meal: string;
  items: string[];
  display_date: string; // the calendar day this menu is shown for (this week)
  source_date: string; // the day the data actually came from
  is_actual: boolean; // display_date === source_date
};

function titleCase(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const MEAL_ORDER = ["breakfast", "lunch", "snacks", "dinner"];

function weekdayKey(dateStr: string): string {
  return new Date(dateStr + "T00:00:00").toLocaleDateString(undefined, { weekday: "long" });
}

function MessPage() {
  const weekQuery = useQuery({
    queryKey: ["mess", "week"],
    queryFn: () => apiGet<MessRow[]>("/mess/week"),
  });

  const rows = weekQuery.data ?? [];
  const byDay = new Map<string, MessRow[]>();
  for (const r of rows) {
    const key = r.display_date;
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key)!.push(r);
  }
  const days = Array.from(byDay.keys()).sort();
  const today = new Date().toISOString().slice(0, 10);
  const defaultDay = days.includes(today) ? today : (days[0] ?? today);

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Mess" title="Mess Schedule" subtitle="Central dining hall" />

        {weekQuery.isLoading ? (
          <div className="surface-card">
            <EmptyState title="Loading…" message="Fetching the weekly menu." />
          </div>
        ) : days.length === 0 ? (
          <div className="surface-card">
            <EmptyState title="No menu published" message="The mess menu hasn't been uploaded yet." />
          </div>
        ) : (
          <SectionCard title="Weekly plan">
            <Tabs defaultValue={defaultDay}>
              <TabsList className="flex-wrap">
                {days.map((d) => (
                  <TabsTrigger key={d} value={d}>
                    {new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short" })}
                    {d === today ? " · Today" : ""}
                  </TabsTrigger>
                ))}
              </TabsList>

              {days.map((d) => {
                const dayRows = [...(byDay.get(d) ?? [])].sort(
                  (a, b) => MEAL_ORDER.indexOf(a.meal) - MEAL_ORDER.indexOf(b.meal),
                );
                const anyRepeated = dayRows.some((r) => !r.is_actual);
                return (
                  <TabsContent key={d} value={d} className="pt-4">
                    <p className="mb-3 text-xs text-muted-foreground">{weekdayKey(d)}</p>
                    {anyRepeated && (
                      <div className="mb-3">
                        <PixelBadge tone="muted">
                          Repeated from {new Date(dayRows[0]!.source_date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })} · next update pending
                        </PixelBadge>
                      </div>
                    )}
                    <div className="grid gap-4 sm:grid-cols-2">
                      {dayRows.map((m) => (
                        <article key={m.id} className="surface-card hover-lift p-4">
                          <h2 className="text-sm font-semibold">{titleCase(m.meal)}</h2>
                          <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                            {m.items.map((i) => (
                              <li key={i} className="flex items-center gap-2">
                                <span className="size-1.5 pixelated bg-accent" /> {i}
                              </li>
                            ))}
                          </ul>
                        </article>
                      ))}
                    </div>
                  </TabsContent>
                );
              })}
            </Tabs>
          </SectionCard>
        )}
      </div>
    </AppShell>
  );
}
