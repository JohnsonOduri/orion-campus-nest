import { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { FileText, Info, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, QueryState, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useMyAcademic, useDocuments, type DocumentMeta } from "@/lib/campus";

export const Route = createFileRoute("/documents")({
  head: () => ({
    meta: [
      { title: "Institute Documents — ORION Campus" },
      {
        name: "description",
        content: "Regulations, curricula, hostel rules and procedures that ORION answers from.",
      },
      { property: "og:title", content: "Institute Documents — ORION" },
      { property: "og:description", content: "Approved institute documents." },
    ],
  }),
  component: DocumentsPage,
});

const GROUPS: { key: string; label: string; match: (d: DocumentMeta) => boolean; ask: string }[] = [
  {
    key: "regulations",
    label: "Academic regulations",
    match: (d) => d.document_type === "regulations",
    ask: "What is the attendance requirement?",
  },
  {
    key: "hostel",
    label: "Hostel",
    match: (d) => d.category === "hostel",
    ask: "What are the hostel rules?",
  },
  {
    key: "ragging",
    label: "Anti-ragging",
    match: (d) => d.category === "anti-ragging",
    ask: "What are the anti-ragging rules?",
  },
  {
    key: "procedure",
    label: "Procedures",
    match: (d) => d.document_type === "procedure",
    ask: "How do I request transcript verification?",
  },
  {
    key: "curriculum",
    label: "Curricula",
    match: (d) => d.document_type === "curriculum",
    ask: "How many credits do I need to graduate?",
  },
];

function cohortLabel(c: string | null): string | null {
  if (!c) return null;
  if (/21\D+25|2021/.test(c)) return "2021–25 batches";
  if (/26|2026/.test(c)) return "2026 admission onwards";
  return c;
}

function DocumentsPage() {
  const query = useDocuments();
  const academic = useMyAcademic();
  const [q, setQ] = useState("");

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Approved"
          title="Institute Documents"
          subtitle="The documents ORION answers regulation and policy questions from."
        />
        <div className="flex gap-3 rounded-2xl border border-border bg-muted/40 p-4 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="text-muted-foreground">
            Ask ORION about any of these and it quotes the exact rule with its page.
            {academic.data?.regulations ? (
              <>
                {" "}
                For academic rules it uses{" "}
                <span className="font-medium text-foreground">{academic.data.regulations}</span>,
                which apply to you.
              </>
            ) : null}
          </p>
        </div>
        <div className="relative max-w-md">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search documents"
            aria-label="Search documents"
            className="h-10 pl-9"
          />
        </div>
        <QueryState
          query={query}
          isEmpty={(d) => d.length === 0}
          emptyTitle="No documents yet"
          emptyMessage="No approved documents have been published in ORION."
          skeletonRows={6}
        >
          {(docs) => <Grouped docs={docs} q={q} />}
        </QueryState>
      </div>
    </AppShell>
  );
}

function Grouped({ docs, q }: { docs: DocumentMeta[]; q: string }) {
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? docs.filter((d) => d.title.toLowerCase().includes(s)) : docs;
  }, [docs, q]);
  if (filtered.length === 0)
    return <p className="text-sm text-muted-foreground">No document matches “{q}”.</p>;

  return (
    <div className="space-y-5">
      {GROUPS.map((g) => {
        const items = filtered.filter(g.match);
        if (!items.length) return null;
        return (
          <SectionCard
            key={g.key}
            title={g.label}
            action={
              <Button asChild variant="ghost" size="sm">
                <Link to="/ai" search={{ q: g.ask }}>
                  <Sparkles className="size-3.5" /> Ask
                </Link>
              </Button>
            }
            contentClassName="p-0"
          >
            <ul className="divide-y divide-border">
              {items.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <FileText className="size-4" />
                  </span>
                  <p className="min-w-0 flex-1 text-sm font-medium">{d.title}</p>
                  {cohortLabel(d.cohort) ? (
                    <PixelBadge tone="muted">{cohortLabel(d.cohort)}</PixelBadge>
                  ) : null}
                </li>
              ))}
            </ul>
          </SectionCard>
        );
      })}
    </div>
  );
}
