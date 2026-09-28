import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { CalendarClock } from "lucide-react";
import { apiGet } from "@/lib/api-client";
import { CATEGORY_LABELS, isAcademic } from "@/lib/cr";

export const Route = createFileRoute("/announcements")({
  head: () => ({
    meta: [
      { title: "Announcements — ORION Campus" },
      { name: "description", content: "Announcements for IIIT Kottayam students." },
      { property: "og:title", content: "Announcements — ORION" },
      { property: "og:description", content: "Campus notices." },
    ],
  }),
  component: AnnouncementsPage,
});

type Announcement = {
  id: number;
  title: string;
  content: string;
  category: string | null;
  department: string | null;
  batch: string | null;
  target_role: string | null;
  created_at: string;
  published_at: string | null;
  section: string | null;
  event_date: string | null;
  event_time: string | null;
  auto_published: boolean | null;
};

function eventLabel(a: Announcement): string | null {
  if (!a.event_date) return null;
  const d = new Date(`${a.event_date}T00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
  return a.event_time ? `${d} · ${a.event_time.slice(0, 5)}` : d;
}

function AnnouncementsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["announcements"],
    queryFn: () => apiGet<Announcement[]>("/announcements"),
  });

  const announcements = data ?? [];

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Notice board" title="Announcements" subtitle="From CRs and the admin team." />

        <SectionCard title="All announcements">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : announcements.length === 0 ? (
            <EmptyState title="No announcements yet" message="Check back later for campus notices." />
          ) : (
            <ul className="space-y-3">
              {announcements.map((a) => (
                <li key={a.id} className="rounded-lg border border-border p-3 hover-lift">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold">{a.title}</p>
                    <PixelBadge tone={isAcademic(a.category) ? "warning" : "primary"}>
                      {CATEGORY_LABELS[a.category ?? ""]?.split(" (")[0] ?? a.category ?? "General"}
                    </PixelBadge>
                    {a.section ? <PixelBadge tone="muted">Your class</PixelBadge> : null}
                  </div>
                  {eventLabel(a) ? (
                    <p className="mt-1.5 flex items-center gap-1.5 text-xs font-medium">
                      <CalendarClock className="size-3.5 text-primary" /> {eventLabel(a)}
                    </p>
                  ) : null}
                  <p className="mt-1.5 whitespace-pre-line text-xs text-muted-foreground">{a.content}</p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {new Date(a.published_at ?? a.created_at).toLocaleString()}
                    {a.auto_published ? " · posted by your CR" : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </AppShell>
  );
}
