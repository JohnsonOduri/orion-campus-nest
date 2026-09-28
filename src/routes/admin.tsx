import { createFileRoute } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Link } from "@tanstack/react-router";
import { DiffSummary, IssueList, TimetableEditor } from "@/components/cr/timetable-editor";
import { ExamDiffSummary, ExamEditor } from "@/components/cr/exam-editor";
import { CheckCircle2, EyeOff, FileText, Search, Upload, UserCog, XCircle } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";
import {
  CATEGORY_LABELS,
  type ClassKey,
  type DraftEntry,
  type DraftIssue,
  type ExamDiff,
  type ExamEntry,
  type TimetableDiff,
} from "@/lib/cr";

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

type ExamSubmission = {
  id: number;
  submitted_by: Person;
  note: string | null;
  created_at: string;
  scope_label: string;
  exam_type_label: string;
  entries: ExamEntry[];
  issues: DraftIssue[];
  diff: ExamDiff;
  current_count: number;
  source_file_path: string | null;
};

type UserRow = {
  id: string;
  full_name: string | null;
  email: string;
  role: "STUDENT" | "CR" | "ADMIN" | "FACULTY";
  student: { semester: number; department: string; section: string | null; roll_number: string | null } | null;
};

type RoleGrant = { email: string; role: string; created_at: string };

const DEFAULT_ADMIN = "oduri.johnson@gmail.com";

function PeopleAndRoles() {
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("CR");
  const users = useQuery({
    queryKey: ["admin", "users", search],
    queryFn: () => apiGet<UserRow[]>(`/admin/users?q=${encodeURIComponent(search)}`),
  });
  const grants = useQuery({ queryKey: ["admin", "role-grants"], queryFn: () => apiGet<RoleGrant[]>("/admin/role-grants") });
  const setUserRole = useMutation({
    mutationFn: (v: { email: string; role: string }) =>
      apiPost<{ role: string; pending_sign_in?: boolean }>("/admin/roles", v),
    onSuccess: (r, v) => {
      toast.success(
        r.pending_sign_in
          ? `${v.email} will be ${v.role} when they first sign in`
          : `${v.email} is now ${v.role}`,
      );
      setEmail("");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "role-grants"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "cr-requests"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Couldn't change the role"),
  });
  const selectClass = "h-8 rounded-md border border-input bg-background px-2 text-xs";
  return (
    <SectionCard title="People & roles" description="Give or remove CR / admin access — also to someone who hasn't signed in yet">
      <div className="space-y-4">
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (email.trim()) setUserRole.mutate({ email: email.trim(), role });
          }}
        >
          <div className="min-w-56 flex-1 space-y-1">
            <label className="text-xs font-medium" htmlFor="grant-email">
              Email
            </label>
            <Input id="grant-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@iiitkottayam.ac.in" className="h-8 text-xs" />
          </div>
          <select className={selectClass} value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role">
            <option value="CR">Class Representative</option>
            <option value="ADMIN">Administrator</option>
            <option value="STUDENT">Student (remove access)</option>
          </select>
          <Button size="sm" type="submit" disabled={setUserRole.isPending || !email.trim()}>
            <UserCog className="size-4" /> Set role
          </Button>
        </form>

        {grants.data?.length ? (
          <div className="rounded-md bg-muted/40 p-2 text-xs">
            <p className="mb-1 font-medium">Waiting for first sign-in</p>
            {grants.data.map((g) => (
              <p key={g.email} className="font-mono">
                {g.email} → {g.role}
              </p>
            ))}
          </div>
        ) : null}

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q);
          }}
        >
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or email" className="h-8 text-xs" />
          <Button size="sm" variant="outline" type="submit">
            <Search className="size-4" /> Search
          </Button>
        </form>
        <ul className="divide-y divide-border rounded-md border border-border">
          {(users.data ?? []).map((u) => (
            <li key={u.id} className="flex flex-wrap items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{u.full_name || u.email}</p>
                <p className="truncate text-[11px] text-muted-foreground">
                  {u.email}
                  {u.student
                    ? ` · Sem ${u.student.semester} ${u.student.department}${u.student.section ? ` Sec ${u.student.section}` : ""}`
                    : ""}
                  {u.student?.roll_number ? ` · ${u.student.roll_number}` : ""}
                </p>
              </div>
              <PixelBadge tone={u.role === "ADMIN" ? "danger" : u.role === "CR" ? "warning" : "muted"}>{u.role}</PixelBadge>
              {u.email.toLowerCase() === DEFAULT_ADMIN ? (
                <span className="text-[11px] text-muted-foreground">default admin</span>
              ) : (
                <select
                  className={selectClass}
                  value={u.role}
                  disabled={setUserRole.isPending}
                  aria-label={`Role for ${u.email}`}
                  onChange={(e) => setUserRole.mutate({ email: u.email, role: e.target.value })}
                >
                  <option value="STUDENT">Student</option>
                  <option value="CR">CR</option>
                  <option value="ADMIN">Admin</option>
                </select>
              )}
            </li>
          ))}
          {users.data && users.data.length === 0 ? <li className="p-3 text-xs text-muted-foreground">No one matches.</li> : null}
        </ul>
      </div>
    </SectionCard>
  );
}

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

  const examQuery = useQuery({
    queryKey: ["admin", "exam-submissions"],
    queryFn: () => apiGet<ExamSubmission[]>("/admin/exam-submissions"),
  });
  const reviewExams = useMutation({
    mutationFn: ({ id, approve, rejection_reason }: { id: number; approve: boolean; rejection_reason?: string }) =>
      apiPost<{ inserted?: number; superseded?: number }>(`/admin/exam-submissions/${id}/review`, { approve, rejection_reason }),
    onSuccess: (data, vars) => {
      toast.success(
        vars.approve
          ? `Exam schedule published: ${data.inserted ?? 0} exams (${data.superseded ?? 0} older ones replaced)`
          : "Exam schedule rejected",
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "exam-submissions"] });
      queryClient.invalidateQueries({ queryKey: ["exams"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Review failed"),
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
          subtitle="Approval queues, roles, and everything live on campus."
          actions={
            <Button asChild size="sm">
              <Link to="/cr">
                <Upload className="size-4" /> Publish & uploads
              </Link>
            </Button>
          }
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
          title="Exam schedules"
          description={`${examQuery.data?.length ?? 0} pending · approving replaces that scope's current exam schedule`}
          contentClassName="p-0"
        >
          {examQuery.isLoading ? (
            <p className="p-4 text-sm text-muted-foreground">Loading…</p>
          ) : !examQuery.data?.length ? (
            <p className="p-4 text-sm text-muted-foreground">No pending exam schedules.</p>
          ) : (
            <ul className="divide-y divide-border">
              {examQuery.data.map((x) => {
                const blocking = x.issues.filter((i) => i.severity === "error").length;
                return (
                  <ReviewRow
                    key={x.id}
                    pending={reviewExams.isPending}
                    onApprove={() => reviewExams.mutate({ id: x.id, approve: true })}
                    onReject={(reason) => reviewExams.mutate({ id: x.id, approve: false, rejection_reason: reason })}
                  >
                    <p className="text-sm font-medium">
                      {x.exam_type_label} exams · {x.scope_label}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {who(x.submitted_by)} · {new Date(x.created_at).toLocaleString()} · {x.entries.length} exams
                    </p>
                    {x.note ? <p className="mt-1 text-xs italic">“{x.note}”</p> : null}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <ExamDiffSummary diff={x.diff} currentCount={x.current_count} />
                      {x.source_file_path ? (
                        <Button size="sm" variant="outline" className="h-7" onClick={() => openOriginal(x.source_file_path!)}>
                          <FileText className="size-3.5" /> Original file
                        </Button>
                      ) : null}
                    </div>
                    {blocking ? (
                      <p className="mt-2 text-xs text-destructive">
                        {blocking} problem{blocking > 1 ? "s" : ""} — approving will fail. Reject with a reason instead.
                      </p>
                    ) : null}
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium text-primary">Show exams</summary>
                      <div className="mt-2">
                        <ExamEditor entries={x.entries} issues={x.issues} readOnly showDepartment />
                      </div>
                    </details>
                  </ReviewRow>
                );
              })}
            </ul>
          )}
        </SectionCard>

        <PeopleAndRoles />

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
