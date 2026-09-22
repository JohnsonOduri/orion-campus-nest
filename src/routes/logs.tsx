import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { EmptyState, PageHeader, SectionCard } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Search } from "lucide-react";
import { apiGet } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";

export const Route = createFileRoute("/logs")({
  beforeLoad: requireRole(["ADMIN"]),
  head: () => ({
    meta: [
      { title: "Audit Logs — ORION Campus" },
      { name: "description", content: "Who changed what, and when — the institute-wide audit trail." },
      { property: "og:title", content: "Audit Logs — ORION" },
      { property: "og:description", content: "Institute-wide audit trail." },
    ],
  }),
  component: LogsPage,
});

type Actor = { id: string; full_name: string | null; email: string; role: string };

type AuditLog = {
  id: number;
  actor_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  old_data: Record<string, unknown> | null;
  new_data: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  actor: Actor | null;
};

// An action names what happened; colour is just a fast scan aid for the two
// outcomes that matter most in a review queue.
function actionTone(action: string): "success" | "danger" | "primary" {
  if (action.includes("approved") || action.includes("published")) return "success";
  if (action.includes("rejected") || action.includes("deleted")) return "danger";
  return "primary";
}

function humanAction(action: string) {
  return action.replace(/_/g, " ");
}

function LogsPage() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "logs"],
    queryFn: () => apiGet<AuditLog[]>("/admin/logs"),
  });

  const logs = data ?? [];
  const query = q.trim().toLowerCase();
  const list = logs.filter(
    (l) =>
      !query ||
      l.action.toLowerCase().includes(query) ||
      (l.entity_type ?? "").toLowerCase().includes(query) ||
      (l.actor?.full_name ?? "").toLowerCase().includes(query) ||
      (l.actor?.email ?? "").toLowerCase().includes(query),
  );

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Administrator"
          title="Audit Logs"
          subtitle={`${logs.length} recorded action${logs.length === 1 ? "" : "s"}`}
        />

        <div className="relative min-w-[12rem] sm:max-w-sm">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by action, person or entity"
            className="h-9 pl-9"
          />
        </div>

        <SectionCard title="Activity" description="Newest first" contentClassName="p-0">
          {isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : list.length === 0 ? (
            <EmptyState
              title={logs.length === 0 ? "No activity recorded yet" : "No matching entries"}
              message={
                logs.length === 0
                  ? "Approvals, rejections and other tracked changes will appear here as they happen."
                  : "Try a different search term."
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {list.map((l) => (
                <li key={l.id} className="flex flex-wrap items-start gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <PixelBadge tone={actionTone(l.action)}>{humanAction(l.action)}</PixelBadge>
                      {l.entity_type && (
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {l.entity_type}
                          {l.entity_id ? ` #${l.entity_id}` : ""}
                        </span>
                      )}
                    </div>
                    <p className="mt-1.5 text-sm">
                      <span className="font-medium">
                        {l.actor?.full_name ?? l.actor?.email ?? "Unknown user"}
                      </span>
                      {l.actor?.role && (
                        <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">{l.actor.role}</span>
                      )}
                    </p>
                    {typeof l.new_data?.["rejection_reason"] === "string" && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        Reason: {String(l.new_data["rejection_reason"])}
                      </p>
                    )}
                  </div>
                  <p className="shrink-0 font-mono text-[11px] text-muted-foreground">
                    {new Date(l.created_at).toLocaleString()}
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
