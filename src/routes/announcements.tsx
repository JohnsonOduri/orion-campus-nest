import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { announcements } from "@/lib/mock-data";
import { Pin } from "lucide-react";

export const Route = createFileRoute("/announcements")({
  head: () => ({
    meta: [
      { title: "Announcements — ORION Campus" },
      { name: "description", content: "Pinned, departmental and general announcements for IIIT Kottayam students." },
      { property: "og:title", content: "Announcements — ORION" },
      { property: "og:description", content: "Campus notices with priority badges and search." },
    ],
  }),
  component: AnnouncementsPage,
});

const tone = { high: "danger", medium: "warning", low: "muted" } as const;

function AnnouncementsPage() {
  const pinned = announcements.filter((a) => a.pinned);
  const rest = announcements.filter((a) => !a.pinned);

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Notice board" title="Announcements" subtitle="From the academic section, hostel and departments." />

        <SectionCard title="Pinned">
          <ul className="space-y-3">
            {pinned.map((a) => (
              <li key={a.id} className="rounded-lg border border-primary/30 bg-primary/5 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Pin className="size-3.5 text-primary" />
                  <p className="text-sm font-semibold">{a.title}</p>
                  <PixelBadge tone={tone[a.priority as keyof typeof tone]}>{a.priority}</PixelBadge>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">{a.body}</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">{a.author} · {a.time}</p>
              </li>
            ))}
          </ul>
        </SectionCard>

        <SectionCard title="All announcements">
          <ul className="space-y-3">
            {rest.map((a) => (
              <li key={a.id} className="rounded-lg border border-border p-3 hover-lift">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold">{a.title}</p>
                  <PixelBadge tone={tone[a.priority as keyof typeof tone]}>{a.tag}</PixelBadge>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">{a.body}</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">{a.author} · {a.time}</p>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>
    </AppShell>
  );
}
