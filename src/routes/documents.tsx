import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { documents } from "@/lib/mock-data";
import { Bookmark, Download, FileText, Search } from "lucide-react";

export const Route = createFileRoute("/documents")({
  head: () => ({
    meta: [
      { title: "Institute Documents — ORION Campus" },
      { name: "description", content: "Search, preview, bookmark and download official IIIT Kottayam documents and forms." },
      { property: "og:title", content: "Institute Documents — ORION" },
      { property: "og:description", content: "Regulations, handbooks, forms and policies in one place." },
    ],
  }),
  component: DocumentsPage,
});

function DocumentsPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Repository" title="Institute Documents" subtitle="Official circulars, forms and policies." />
        <div className="relative max-w-md">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search documents" className="h-9 pl-9" />
        </div>
        <SectionCard contentClassName="p-0">
          <ul className="divide-y divide-border">
            {documents.map((d) => (
              <li key={d.name} className="flex flex-wrap items-center gap-3 p-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                  <FileText className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{d.name}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {d.size} · updated {d.updated}
                  </p>
                </div>
                <PixelBadge tone="muted">{d.category}</PixelBadge>
                <Button variant="ghost" size="icon" aria-label="Bookmark">
                  <Bookmark className="size-4" />
                </Button>
                <Button variant="outline" size="sm">
                  <Download className="size-4" /> PDF
                </Button>
              </li>
            ))}
          </ul>
        </SectionCard>
      </div>
    </AppShell>
  );
}
