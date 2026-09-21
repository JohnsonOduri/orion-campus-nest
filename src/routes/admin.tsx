import { createFileRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { adminStats, usageTrend, users } from "@/lib/mock-data";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Users2, Sparkles, ScanText, HardDrive, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";

export const Route = createFileRoute("/admin")({
  beforeLoad: requireRole(["ADMIN"]),
  head: () => ({
    meta: [
      { title: "Admin Portal — ORION Campus" },
      { name: "description", content: "Administrator workspace: approvals, user and faculty management, analytics and storage." },
      { property: "og:title", content: "Admin Portal — ORION" },
      { property: "og:description", content: "Approvals, user management and campus analytics." },
    ],
  }),
  component: AdminPage,
});

const icons = [Users2, Sparkles, ScanText, HardDrive];

type CrRequest = {
  id: number;
  submitted_by: string;
  submitter_note: string | null;
  created_at: string;
};

type PendingAnnouncement = {
  id: number;
  title: string;
  content: string;
  category: string | null;
  department: string | null;
  batch: string | null;
  target_role: string | null;
  submitted_by: string;
  created_at: string;
};

function ReviewRow({
  children,
  onApprove,
  onReject,
  pending,
}: {
  children: ReactNode;
  onApprove: () => void;
  onReject: (reason: string) => void;
  pending: boolean;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  return (
    <li className="space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">{children}</div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" disabled={pending} onClick={onApprove}>
            <CheckCircle2 className="size-4" /> Approve
          </Button>
          <Button size="sm" variant="destructive" disabled={pending} onClick={() => setRejecting((v) => !v)}>
            <XCircle className="size-4" /> Reject
          </Button>
        </div>
      </div>
      {rejecting && (
        <div className="flex gap-2">
          <Input
            placeholder="Reason for rejection"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="h-8 text-xs"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() => {
              onReject(reason);
              setRejecting(false);
              setReason("");
            }}
          >
            Confirm
          </Button>
        </div>
      )}
    </li>
  );
}

function AdminPage() {
  const queryClient = useQueryClient();

  const crRequestsQuery = useQuery({
    queryKey: ["admin", "cr-requests"],
    queryFn: () => apiGet<CrRequest[]>("/admin/cr-requests"),
  });
  const announcementsQuery = useQuery({
    queryKey: ["admin", "announcements"],
    queryFn: () => apiGet<PendingAnnouncement[]>("/admin/announcements"),
  });

  const reviewCr = useMutation({
    mutationFn: ({ id, approve, rejection_reason }: { id: number; approve: boolean; rejection_reason?: string }) =>
      apiPost(`/admin/cr-requests/${id}/review`, { approve, rejection_reason }),
    onSuccess: (_data, vars) => {
      toast.success(vars.approve ? "CR access approved" : "CR access request rejected");
      queryClient.invalidateQueries({ queryKey: ["admin", "cr-requests"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Review failed"),
  });

  const reviewAnnouncement = useMutation({
    mutationFn: ({ id, approve, rejection_reason }: { id: number; approve: boolean; rejection_reason?: string }) =>
      apiPost(`/admin/announcements/${id}/review`, { approve, rejection_reason }),
    onSuccess: (_data, vars) => {
      toast.success(vars.approve ? "Announcement published" : "Announcement rejected");
      queryClient.invalidateQueries({ queryKey: ["admin", "announcements"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Review failed"),
  });

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Administrator" title="Admin Portal" subtitle="Institute-wide operations and analytics." />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {adminStats.map((s, i) => {
            const Icon = icons[i]!;
            return (
              <StatCard
                key={s.label}
                label={s.label}
                value={s.value.toLocaleString()}
                suffix={s.suffix ?? ""}
                delta={s.delta}
                icon={<Icon className="size-4" />}
                tone={i % 2 ? "accent" : "primary"}
              />
            );
          })}
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title="Daily active users">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={usageTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="day" fontSize={11} stroke="var(--color-muted-foreground)" />
                  <YAxis fontSize={11} stroke="var(--color-muted-foreground)" />
                  <Tooltip contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 10, fontSize: 12 }} />
                  <Line type="monotone" dataKey="users" stroke="var(--color-chart-1)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          <SectionCard title="AI queries">
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={usageTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="day" fontSize={11} stroke="var(--color-muted-foreground)" />
                  <YAxis fontSize={11} stroke="var(--color-muted-foreground)" />
                  <Tooltip contentStyle={{ background: "var(--color-card)", border: "1px solid var(--color-border)", borderRadius: 10, fontSize: 12 }} />
                  <Bar dataKey="queries" fill="var(--color-chart-2)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        </div>

        <SectionCard
          title="CR access requests"
          description={`${crRequestsQuery.data?.length ?? 0} pending`}
          contentClassName="p-0"
        >
          {crRequestsQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !crRequestsQuery.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">No pending CR access requests.</p>
          ) : (
            <ul className="divide-y divide-border">
              {crRequestsQuery.data.map((r) => (
                <ReviewRow
                  key={r.id}
                  pending={reviewCr.isPending}
                  onApprove={() => reviewCr.mutate({ id: r.id, approve: true })}
                  onReject={(reason) => reviewCr.mutate({ id: r.id, approve: false, rejection_reason: reason })}
                >
                  <p className="truncate font-mono text-xs">{r.submitted_by}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {r.submitter_note ?? "No reason given"} · {new Date(r.created_at).toLocaleString()}
                  </p>
                </ReviewRow>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard
          title="Announcement approvals"
          description={`${announcementsQuery.data?.length ?? 0} pending`}
          contentClassName="p-0"
        >
          {announcementsQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !announcementsQuery.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">No pending announcements.</p>
          ) : (
            <ul className="divide-y divide-border">
              {announcementsQuery.data.map((a) => (
                <ReviewRow
                  key={a.id}
                  pending={reviewAnnouncement.isPending}
                  onApprove={() => reviewAnnouncement.mutate({ id: a.id, approve: true })}
                  onReject={(reason) =>
                    reviewAnnouncement.mutate({ id: a.id, approve: false, rejection_reason: reason })
                  }
                >
                  <p className="truncate text-sm font-medium">{a.title}</p>
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{a.content}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {a.category ?? "General"} · {new Date(a.created_at).toLocaleString()}
                  </p>
                </ReviewRow>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title="User management" contentClassName="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Department</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="text-sm font-medium">{u.name}</TableCell>
                    <TableCell className="font-mono text-xs">{u.id}</TableCell>
                    <TableCell className="text-xs">{u.role}</TableCell>
                    <TableCell className="text-xs">{u.dept}</TableCell>
                    <TableCell>
                      <PixelBadge tone={u.status === "active" ? "success" : "danger"}>{u.status}</PixelBadge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
