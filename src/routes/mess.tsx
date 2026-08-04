import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { messMenu } from "@/lib/mock-data";
import { Star } from "lucide-react";

export const Route = createFileRoute("/mess")({
  head: () => ({
    meta: [
      { title: "Mess Schedule — ORION Campus" },
      { name: "description", content: "Today's mess menu, meal timings, weekly plan and student ratings at IIIT Kottayam." },
      { property: "og:title", content: "Mess Schedule — ORION" },
      { property: "og:description", content: "Menus, timings and ratings for every meal." },
    ],
  }),
  component: MessPage,
});

const week = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function MessPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Week 32" title="Mess Schedule" subtitle="Central dining hall · Block A" />

        <div className="grid gap-4 sm:grid-cols-2">
          {messMenu.map((m) => (
            <article key={m.meal} className="surface-card hover-lift p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">{m.meal}</h2>
                {m.special ? <PixelBadge tone="warning">Today&apos;s special</PixelBadge> : null}
              </div>
              <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">{m.time}</p>
              <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                {m.items.map((i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="size-1.5 pixelated bg-accent" /> {i}
                  </li>
                ))}
              </ul>
              <p className="mt-3 flex items-center gap-1 text-xs font-medium text-warning-foreground">
                <Star className="size-3.5 fill-current" /> {m.rating} / 5
              </p>
            </article>
          ))}
        </div>

        <SectionCard title="Weekly plan" contentClassName="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="p-3 text-left font-mono text-[11px] uppercase text-muted-foreground">Meal</th>
                  {week.map((d) => (
                    <th key={d} className="p-3 text-left font-mono text-[11px] text-muted-foreground">
                      {d}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {messMenu.map((m) => (
                  <tr key={m.meal} className="border-b border-border last:border-0">
                    <td className="p-3 font-medium">{m.meal}</td>
                    {week.map((d) => (
                      <td key={d} className="p-3 text-xs text-muted-foreground">
                        {m.items[0]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
