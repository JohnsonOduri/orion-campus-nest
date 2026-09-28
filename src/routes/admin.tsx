import { createFileRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { DiffSummary, IssueList, TimetableEditor } from "@/components/cr/timetable-editor";
import { CheckCircle2, EyeOff, FileText, XCircle } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";
import { CATEGORY_LABELS, type ClassKey, type DraftEntry, type DraftIssue, type TimetableDiff } from "@/lib/cr";

export const Route = createFileRoute("/admin")({
  beforeLoad: requireRole(["ADMIN"]),
  head: () => ({
    meta: [
      { title: "Admin Portal — ORION Campus" },
      { name: "description", content: "Administrator workspace: CR access, timetable changes and announcements." },
      { property: "og:title", content: "Admin Portal — ORION" },
      { property: "og:description", content: "CR access, timetable and announcement approvals." },
    ],
  }),
  component: AdminPage,
});

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

type Person = { id: string; full_name?: string | null; email?: string | null };

type TimetableSubmission = {
  id: number;
  submitted_by: Person;
  note: string | null;
  created_at: string;
  class: ClassKey;
  class_label: string;
  valid_from: string | null;
  valid_until: string | null;
  entries: DraftEntry[];
  issues: DraftIssue[];
  diff: TimetableDiff;
  current_count: number;
  source_file_path: string | null;
};

type LiveAnnouncement = {
  id: number;
  title: string;
  content: string;
  category: string | null;
  semester: number | null;
  department: string | null;
  section: string | null;
  event_date: string | null;
  event_time: string | null;
  valid_until: string | null;
  auto_published: boolean;
  submitted_by: Person;
  published_at: string | null;
};

const who = (p: Person) => p.full_name || p.email || p.id.slice(0, 8);

async function openOriginal(path: string) {
  // Open the tab synchronously (popup blockers), then point it at the signed URL.
  const tab = window.open("", "_blank");
  try {
    const { url } = await apiGet<{ url: string }>(`/cr/uploads/url?path=${encodeURIComponent(path)}`);
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (err) {
    tab?.close();
    toast.error(err instanceof ApiError ? err.message : "Couldn't open the file");
  }
}

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

  const timetableQuery = useQuery({
    queryKey: ["admin", "timetable-submissions"],
    queryFn: () => apiGet<TimetableSubmission[]>("/admin/timetable-submissions"),
  });
  const liveQuery = useQuery({
    queryKey: ["admin", "announcements", "live"],
    queryFn: () => apiGet<LiveAnnouncement[]>("/admin/announcements/live"),
  });

  const reviewTimetable = useMutation({
    mutationFn: ({ id, approve, rejection_reason }: { id: number; approve: boolean; rejection_reason?: string }) =>
      apiPost<{ inserted?: number; closed?: number; valid_from?: string }>(`/admin/timetable-submissions/${id}/review`, {
        approve,
        rejection_reason,
      }),
    onSuccess: (data, vars) => {
      toast.success(
        vars.approve
          ? `Timetable updated: ${data.inserted ?? 0} periods live from ${data.valid_from ?? "today"} (${data.closed ?? 0} old ones closed)`
          : "Timetable change rejected",
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "timetable-submissions"] });
      queryClient.invalidateQueries({ queryKey: ["timetable"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Review failed"),
  });

  const takeDown = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      apiPost(`/admin/announcements/${id}/archive`, { reason: reason || undefined }),
    onSuccess: () => {
      toast.success("Announcement taken down");
      queryClient.invalidateQueries({ queryKey: ["admin", "announcements", "live"] });
      queryClient.invalidateQueries({ queryKey: ["announcements"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Couldn't take it down"),
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
        <PageHeader
          badge="Administrator"
          title="Admin Portal"
          subtitle="Approval queues for CR access, timetable changes and announcements."
        />

        <SectionCard
          title="Timetable changes from CRs"
          description={`${timetableQuery.data?.length ?? 0} pending · approving replaces the class's current periods`}
          contentClassName="p-0"
        >
          {timetableQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !timetableQuery.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">No pending timetable changes.</p>
          ) : (
            <ul className="divide-y divide-border">
              {timetableQuery.data.map((t) => {
                const blocking = t.issues.filter((i) => i.severity === "error").length;
                return (
                  <ReviewRow
                    key={t.id}
                    pending={reviewTimetable.isPending}
                    onApprove={() => reviewTimetable.mutate({ id: t.id, approve: true })}
                    onReject={(reason) => reviewTimetable.mutate({ id: t.id, approve: false, rejection_reason: reason })}
                  >
                    <p className="text-sm font-medium">{t.class_label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {who(t.submitted_by)} · {new Date(t.created_at).toLocaleString()} · {t.entries.length} periods · from{" "}
                      {t.valid_from ?? "approval"}
                      {t.valid_until ? ` to ${t.valid_until}` : ""}
                    </p>
                    {t.note ? <p className="mt-1 text-xs italic">“{t.note}”</p> : null}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <DiffSummary diff={t.diff} currentCount={t.current_count} />
                      {t.source_file_path ? (
                        <Button size="sm" variant="outline" className="h-7" onClick={() => openOriginal(t.source_file_path!)}>
                          <FileText className="size-3.5" /> Original file
                        </Button>
                      ) : null}
                    </div>
                    {blocking ? (
                      <p className="mt-2 text-xs text-destructive">
                        {blocking} period{blocking > 1 ? "s" : ""} no longer match the directory — approving will fail
                        until the CR fixes them. Reject with a reason instead.
                      </p>
                    ) : null}
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium text-primary">Show proposed timetable</summary>
                      <div className="mt-2 space-y-2">
                        <TimetableEditor entries={t.entries} issues={t.issues} readOnly />
                        <IssueList issues={t.issues} entries={t.entries} />
                      </div>
                    </details>
                  </ReviewRow>
                );
              })}
            </ul>
          )}
        </SectionCard>

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

        <SectionCard
          title="Live announcements"
          description="Including class notices CRs shared directly — take down anything that shouldn't be there"
          contentClassName="p-0"
        >
          {liveQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !liveQuery.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">Nothing is live right now.</p>
          ) : (
            <ul className="divide-y divide-border">
              {liveQuery.data.map((a) => (
                <TakeDownRow key={a.id} a={a} pending={takeDown.isPending} onTakeDown={(reason) => takeDown.mutate({ id: a.id, reason })} />
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </AppShell>
  );
}

function TakeDownRow({
  a,
  pending,
  onTakeDown,
}: {
  a: LiveAnnouncement;
  pending: boolean;
  onTakeDown: (reason: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const scope = a.section
    ? `Sem ${a.semester} · ${a.department} · Sec ${a.section}`
    : "Everyone";
  return (
    <li className="space-y-2 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium">{a.title}</p>
            {a.auto_published ? <PixelBadge tone="warning">posted by CR</PixelBadge> : null}
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{a.content}</p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            {CATEGORY_LABELS[a.category ?? ""] ?? a.category ?? "General"} · {scope} · {who(a.submitted_by)}
            {a.event_date ? ` · event ${a.event_date}` : ""}
            {a.valid_until ? ` · until ${a.valid_until.slice(0, 10)}` : ""}
          </p>
        </div>
        <Button size="sm" variant="outline" disabled={pending} onClick={() => setOpen((v) => !v)}>
          <EyeOff className="size-4" /> Take down
        </Button>
      </div>
      {open ? (
        <div className="flex gap-2">
          <Input
            placeholder="Reason (shown to the CR)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="h-8 text-xs"
          />
          <Button
            size="sm"
            variant="destructive"
            disabled={pending}
            onClick={() => {
              onTakeDown(reason);
              setOpen(false);
            }}
          >
            Confirm
          </Button>
        </div>
      ) : null}
    </li>
  );
}
