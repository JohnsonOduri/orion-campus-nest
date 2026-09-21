import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { courses, documents, events } from "@/lib/mock-data";
import { apiGet } from "@/lib/api-client";
import { Search } from "lucide-react";

type FacultyMember = { id: number; full_name: string };
type Announcement = { id: number; title: string };

export const Route = createFileRoute("/search")({
  head: () => ({
    meta: [
      { title: "Search — ORION Campus Companion" },
      { name: "description", content: "Search faculty, courses, events, announcements and documents across IIIT Kottayam." },
      { property: "og:title", content: "Search — ORION" },
      { property: "og:description", content: "One search box for the whole campus." },
    ],
  }),
  component: SearchPage,
});

function SearchPage() {
  const facultyQuery = useQuery({
    queryKey: ["faculty"],
    queryFn: () => apiGet<FacultyMember[]>("/faculty"),
  });
  const announcementsQuery = useQuery({
    queryKey: ["announcements"],
    queryFn: () => apiGet<Announcement[]>("/announcements"),
  });

  const groups = [
    { label: "Faculty", items: (facultyQuery.data ?? []).slice(0, 3).map((f) => f.full_name) },
    { label: "Courses", items: courses.slice(0, 3).map((c) => `${c.code} · ${c.title}`) },
    { label: "Events", items: events.slice(0, 3).map((e) => e.name) },
    { label: "Announcements", items: (announcementsQuery.data ?? []).slice(0, 3).map((a) => a.title) },
    { label: "Documents", items: documents.slice(0, 3).map((d) => d.name) },
  ];

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Global" title="Search campus" subtitle="Faculty, courses, events, notices and documents." />
        <div className="relative">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input autoFocus placeholder="Try “compiler design” or “mess timing”" className="h-11 pl-9" />
        </div>
        <div className="flex flex-wrap gap-2">
          {["Recent: hall ticket", "Recent: Dr. Rekha", "AI: exam plan"].map((r) => (
            <PixelBadge key={r} tone="muted">{r}</PixelBadge>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {groups.map((g) => (
            <SectionCard key={g.label} title={g.label} contentClassName="p-0">
              <ul className="divide-y divide-border">
                {g.items.map((i) => (
                  <li key={i} className="px-4 py-3 text-sm transition-colors hover:bg-muted/50">
                    {i}
                  </li>
                ))}
              </ul>
            </SectionCard>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
