import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { notifications } from "@/lib/mock-data";
import { Bell } from "lucide-react";

export const Route = createFileRoute("/notifications")({
  head: () => ({
    meta: [
      { title: "Notifications — ORION Campus" },
      { name: "description", content: "Grouped campus notifications: timetable changes, announcements, grades and clubs." },
      { property: "og:title", content: "Notifications — ORION" },
      { property: "og:description", content: "Everything that changed on campus today." },
    ],
  }),
  component: NotificationsPage,
});

function NotificationsPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="2 unread" title="Notifications" subtitle="Grouped by day." />
        {notifications.map((g) => (
          <SectionCard key={g.group} title={g.group} contentClassName="p-0">
            <ul className="divide-y divide-border">
              {g.items.map((n) => (
                <li key={n.title} className="flex items-center gap-3 p-4">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-secondary/60">
                    <Bell className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{n.title}</p>
                    <p className="font-mono text-[11px] text-muted-foreground">{n.time}</p>
                  </div>
                  {n.unread ? <PixelBadge tone="danger">New</PixelBadge> : <PixelBadge tone="muted">{n.type}</PixelBadge>}
                </li>
              ))}
            </ul>
          </SectionCard>
        ))}
      </div>
    </AppShell>
  );
}
