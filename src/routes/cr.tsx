import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PixelBadge, PixelLoadingBar } from "@/components/pixel/pixel-art";
import { DiffSummary, IssueList, TimetableEditor } from "@/components/cr/timetable-editor";
import { ExamDiffSummary, ExamEditor } from "@/components/cr/exam-editor";
import {
  CalendarClock,
  CheckCircle2,
  Clock,
  FileUp,
  GraduationCap,
  Megaphone,
  PenLine,
  Plus,
  Send,
  ShieldCheck,
  Table2,
  Trash2,
} from "lucide-react";
import { useProfile } from "@/hooks/use-profile";
import { toast } from "sonner";
import { apiGet, apiPost, apiUpload, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";
import {
  ACADEMIC_CATEGORIES,
  CATEGORY_LABELS,
  MAX_UPLOAD_BYTES,
  EXAM_TYPES,
  METHOD_LABELS,
  OTHER_CATEGORIES,
  prepareUpload,
  stripResolved,
  targetQuery,
  type AnnouncementDraft,
  type ClassChange,
  type ClassChangePreview,
  type ClassOption,
  type DraftEntry,
  type ExamEntry,
  type ExamPayload,
  type TargetClass,
  type TimetablePayload,
  type UploadResult,
} from "@/lib/cr";

export const Route = createFileRoute("/cr")({
  beforeLoad: requireRole(["CR", "ADMIN"]),
  head: () => ({
    meta: [
      { title: "CR Portal — ORION Campus" },
      {
        name: "description",
        content: "Class representative workspace: upload timetables and notices, post class announcements.",
      },
      { property: "og:title", content: "CR Portal — ORION" },
      { property: "og:description", content: "Timetable uploads, class announcements and approvals." },
    ],
  }),
  component: CrPage,
});

type MyAnnouncement = {
  id: number;
  semester?: number | null;
  department?: string | null;
  section?: string | null;
  title: string;
  status: string;
  category: string | null;
  rejection_reason: string | null;
  created_at: string;
  published_at: string | null;
  event_date: string | null;
  event_time: string | null;
  valid_until: string | null;
  auto_published: boolean;
};

type TimetableSubmission = {
  id: number;
  class_label?: string | null;
  exam_type?: string | null;
  approval_status: "pending" | "approved" | "rejected";
  rejection_reason: string | null;
  submitter_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  periods: number;
  valid_from: string | null;
};

const tone = {
  active: "success",
  approved: "success",
  pending: "warning",
  rejected: "danger",
  archived: "muted",
} as const;

const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.message : fallback);

function todayIso() {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const selectClass =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** Admins publish for a class they pick; a CR's class is always their own. */
function ClassPicker({ value, onChange }: { value: TargetClass | null; onChange: (t: TargetClass | null) => void }) {
  const classes = useQuery({
    queryKey: ["cr", "classes"],
    queryFn: () => apiGet<ClassOption[]>("/cr/classes"),
    staleTime: 10 * 60 * 1000,
  });
  const rows = classes.data ?? [];
  const semesters = [...new Set(rows.map((c) => c.semester))].sort((a, b) => a - b);
  const departments = [...new Set(rows.filter((c) => c.semester === value?.semester).map((c) => c.department))].sort();
  const sections = rows
    .filter((c) => c.semester === value?.semester && c.department === value?.department)
    .map((c) => c.section);
  return (
    <SectionCard
      title="Publishing for"
      description="Pick the class. For an exam schedule, the semester alone covers every department."
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="pk-sem">Semester</Label>
          <select
            id="pk-sem"
            className={selectClass}
            value={value?.semester ?? ""}
            onChange={(e) => onChange(e.target.value ? { semester: Number(e.target.value) } : null)}
          >
            <option value="">Choose…</option>
            {semesters.map((s) => (
              <option key={s} value={s}>
                Semester {s}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pk-dept">Department</Label>
          <select
            id="pk-dept"
            className={selectClass}
            disabled={!value?.semester}
            value={value?.department ?? ""}
            onChange={(e) => value && onChange({ semester: value.semester, department: e.target.value || null })}
          >
            <option value="">All departments</option>
            {departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pk-sec">Section</Label>
          <select
            id="pk-sec"
            className={selectClass}
            disabled={!value?.department}
            value={value?.section ?? ""}
            onChange={(e) => value && onChange({ ...value, section: e.target.value || null })}
          >
            <option value="">Choose…</option>
            {sections.map((s) => (
              <option key={s} value={s}>
                Section {s}
              </option>
            ))}
          </select>
        </div>
      </div>
    </SectionCard>
  );
}

function CrPage() {
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const isAdmin = profile?.role === "ADMIN";
  const [target, setTarget] = useState<TargetClass | null>(null);
  const classTarget = isAdmin ? target : null;
  const [tab, setTab] = useState("upload");
  const [lastUpload, setLastUpload] = useState<UploadResult | null>(null);
  const [timetable, setTimetable] = useState<TimetablePayload | null>(null);
  const [timetableSource, setTimetableSource] = useState<{ method: string; confidence: number; path: string | null } | null>(
    null,
  );
  const [exams, setExams] = useState<ExamPayload | null>(null);
  const [examPath, setExamPath] = useState<string | null>(null);
  const [announcementSeed, setAnnouncementSeed] = useState<{ draft: AnnouncementDraft | null; path: string | null; key: number }>(
    { draft: null, path: null, key: 0 },
  );

  const announcementsQuery = useQuery({
    queryKey: ["cr", "announcements"],
    queryFn: () => apiGet<MyAnnouncement[]>("/cr/announcements"),
  });
  const submissionsQuery = useQuery({
    queryKey: ["cr", "timetable-submissions"],
    queryFn: () => apiGet<TimetableSubmission[]>("/cr/timetable/submissions"),
  });
  const examSubmissionsQuery = useQuery({
    queryKey: ["cr", "exam-submissions"],
    queryFn: () => apiGet<TimetableSubmission[]>("/cr/exams/submissions"),
  });

  const announcements = announcementsQuery.data ?? [];
  const submissions = submissionsQuery.data ?? [];
  const examSubmissions = examSubmissionsQuery.data ?? [];
  const live = announcements.filter((a) => a.status === "active").length;
  const waiting =
    announcements.filter((a) => a.status === "pending").length +
    submissions.filter((s) => s.approval_status === "pending").length +
    examSubmissions.filter((s) => s.approval_status === "pending").length;

  const onUploaded = (result: UploadResult) => {
    setLastUpload(result);
    if (result.kind === "exam_timetable" && result.exams) {
      setExams(result.exams);
      setExamPath(result.upload_path);
      setTab("exams");
    } else if (result.kind === "timetable" && result.timetable) {
      setTimetable(result.timetable);
      setTimetableSource({ method: result.method, confidence: result.confidence, path: result.upload_path });
      setTab("timetable");
    } else {
      setAnnouncementSeed((s) => ({ draft: result.announcement, path: result.upload_path, key: s.key + 1 }));
      setTab("announcement");
    }
  };

  const openTimetableEditor = async () => {
    try {
      const p = await apiGet<TimetablePayload>(`/cr/timetable/current${targetQuery(classTarget)}`);
      setTimetable(p);
      setTimetableSource({ method: "manual", confidence: 1, path: null });
      setTab("timetable");
    } catch (err) {
      toast.error(errorText(err, "Couldn't load the current timetable"));
    }
  };

  const submissionList = (rows: TimetableSubmission[], empty: string, unit: string) =>
    rows.length === 0 ? (
      <p className="p-4 text-sm text-muted-foreground">{empty}</p>
    ) : (
      <ul className="divide-y divide-border">
        {rows.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {s.periods} {unit}
                {s.class_label ? ` · ${s.class_label}` : ""}
                {s.valid_from ? ` · from ${s.valid_from}` : ""}
              </p>
              <p className="text-[11px] text-muted-foreground">
                Submitted {new Date(s.created_at).toLocaleString()}
                {s.rejection_reason ? ` · ${s.rejection_reason}` : ""}
                {s.submitter_note ? ` · “${s.submitter_note}”` : ""}
              </p>
            </div>
            <PixelBadge tone={tone[s.approval_status] ?? "muted"}>{s.approval_status}</PixelBadge>
          </li>
        ))}
      </ul>
    );

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge={isAdmin ? "Administrator" : "Class representative"}
          title={isAdmin ? "Publish & uploads" : "CR Portal"}
          subtitle={
            isAdmin
              ? "Upload timetables, exam schedules and notices for any class — what you publish goes live at once."
              : "Upload a timetable, exam schedule or notice — ORION reads it, you check it, and it reaches your class."
          }
        />

        {isAdmin ? <ClassPicker value={target} onChange={setTarget} /> : null}

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Live announcements" value={live} tone="success" icon={<CheckCircle2 className="size-4" />} />
          <StatCard label="Waiting for admin" value={waiting} tone="warning" icon={<Clock className="size-4" />} />
          <StatCard label="Timetable changes" value={submissions.length} icon={<Table2 className="size-4" />} />
          <StatCard label="Exam schedules" value={examSubmissions.length} icon={<GraduationCap className="size-4" />} />
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value="upload">
              <FileUp className="size-4" /> Upload
            </TabsTrigger>
            <TabsTrigger value="timetable">
              <Table2 className="size-4" /> Timetable
            </TabsTrigger>
            <TabsTrigger value="exams">
              <GraduationCap className="size-4" /> Exams
            </TabsTrigger>
            <TabsTrigger value="announcement">
              <Megaphone className="size-4" /> Announcement
            </TabsTrigger>
            <TabsTrigger value="history">
              <Clock className="size-4" /> History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="space-y-4 pt-4">
            <UploadPanel onUploaded={onUploaded} target={classTarget} isAdmin={isAdmin} />
            {lastUpload?.text ? (
              <SectionCard title="Text ORION read from your last file" description={METHOD_LABELS[lastUpload.method] ?? ""}>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">
                  {lastUpload.text}
                </pre>
              </SectionCard>
            ) : null}
            <HowItWorks isAdmin={isAdmin} />
          </TabsContent>

          <TabsContent value="timetable" className="pt-4">
            <TimetablePanel
              payload={timetable}
              source={timetableSource}
              target={classTarget}
              isAdmin={isAdmin}
              onPayload={setTimetable}
              onStartManual={(p) => {
                setTimetable(p);
                setTimetableSource({ method: "manual", confidence: 1, path: null });
              }}
              onSubmitted={() => {
                setTimetable(null);
                setTimetableSource(null);
                queryClient.invalidateQueries({ queryKey: ["cr", "timetable-submissions"] });
                queryClient.invalidateQueries({ queryKey: ["timetable"] });
                setTab("history");
              }}
              onUpload={() => setTab("upload")}
            />
          </TabsContent>

          <TabsContent value="exams" className="pt-4">
            <ExamsPanel
              payload={exams}
              uploadPath={examPath}
              target={classTarget}
              isAdmin={isAdmin}
              onPayload={setExams}
              onSubmitted={() => {
                setExams(null);
                setExamPath(null);
                queryClient.invalidateQueries({ queryKey: ["cr", "exam-submissions"] });
                queryClient.invalidateQueries({ queryKey: ["exams"] });
                setTab("history");
              }}
              onUpload={() => setTab("upload")}
            />
          </TabsContent>

          <TabsContent value="announcement" className="pt-4">
            <AnnouncementPanel
              key={announcementSeed.key}
              seed={announcementSeed.draft}
              uploadPath={announcementSeed.path}
              target={classTarget}
              isAdmin={isAdmin}
              onPermanent={openTimetableEditor}
              onPosted={() => {
                queryClient.invalidateQueries({ queryKey: ["cr", "announcements"] });
                queryClient.invalidateQueries({ queryKey: ["announcements"] });
                queryClient.invalidateQueries({ queryKey: ["timetable"] });
                setAnnouncementSeed((s) => ({ draft: null, path: null, key: s.key + 1 }));
                setTab("history");
              }}
            />
          </TabsContent>

          <TabsContent value="history" className="space-y-4 pt-4">
            <SectionCard title="Timetable changes" contentClassName="p-0">
              {submissionsQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : (
                submissionList(submissions, "No timetable changes submitted yet.", "periods")
              )}
            </SectionCard>
            <SectionCard title="Exam schedules" contentClassName="p-0">
              {examSubmissionsQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : (
                submissionList(examSubmissions, "No exam schedules submitted yet.", "exams")
              )}
            </SectionCard>

            <SectionCard title="Announcements" contentClassName="p-0">
              {announcementsQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : announcements.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No announcements posted yet.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {announcements.map((a) => (
                    <li key={a.id} className="flex flex-wrap items-center gap-3 p-4">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{a.title}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {CATEGORY_LABELS[a.category ?? ""] ?? a.category ?? "General"}
                          {a.event_date ? ` · on ${a.event_date}${a.event_time ? ` ${a.event_time.slice(0, 5)}` : ""}` : ""}
                          {` · ${new Date(a.created_at).toLocaleString()}`}
                          {a.section ? ` · Sem ${a.semester} Sec ${a.section}` : " · everyone"}
                          {a.auto_published ? " · shared directly" : ""}
                          {a.rejection_reason ? ` · ${a.rejection_reason}` : ""}
                        </p>
                      </div>
                      <PixelBadge tone={tone[a.status as keyof typeof tone] ?? "muted"}>
                        {a.status === "active" ? "live" : a.status}
                      </PixelBadge>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}

// ------------------------------------------------------------------ upload

function UploadPanel({
  onUploaded,
  target,
  isAdmin,
}: {
  onUploaded: (r: UploadResult) => void;
  target: TargetClass | null;
  isAdmin: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = await prepareUpload(file);
      if (body.size > MAX_UPLOAD_BYTES) throw new ApiError(400, "The file is larger than 4 MB. Take a smaller photo or compress the PDF.");
      return apiUpload<UploadResult>(`/cr/uploads${targetQuery(target)}`, body);
    },
    onSuccess: (result) => {
      if (result.kind === "timetable" && result.timetable && !result.timetable.entries.length) {
        toast.warning("No timetable for this class was found in that file.");
      } else if (result.kind === "exam_timetable") {
        toast.success(`Exam schedule read — ${result.exams?.entries.length ?? 0} exams. Check them below.`);
      } else {
        toast.success(result.kind === "timetable" ? "Timetable read — check it below" : "Notice read — check it below");
      }
      onUploaded(result);
    },
    onError: (err) => toast.error(errorText(err, "Couldn't read that file")),
  });

  // OCR can take 15–40 s; show steady progress instead of a frozen button.
  useEffect(() => {
    if (!upload.isPending) {
      setProgress(0);
      return;
    }
    setProgress(8);
    const id = window.setInterval(() => setProgress((p) => Math.min(92, p + (100 - p) * 0.06)), 700);
    return () => window.clearInterval(id);
  }, [upload.isPending]);

  const pick = (file: File | undefined) => {
    if (!file || upload.isPending) return;
    setFileName(file.name);
    upload.mutate(file);
  };

  return (
    <SectionCard title="Upload a timetable, exam schedule or notice" description="PDF, JPEG, PNG or WebP · up to 4 MB">
      {isAdmin && !target ? (
        <p className="mb-3 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
          Pick a semester above first (and a department + section for a class timetable).
        </p>
      ) : null}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/60"
        }`}
      >
        <FileUp className="size-8 text-primary" />
        <p className="text-sm font-semibold">{upload.isPending ? `Reading ${fileName ?? "your file"}…` : "Drop a file here or tap to choose"}</p>
        <p className="max-w-md text-xs text-muted-foreground">
          A timetable becomes an editable grid; an exam timetable becomes an editable exam list; a notice (quiz,
          assignment, class change…) becomes an announcement you review before posting. Photos work too.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={(e) => {
            pick(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>
      {upload.isPending ? (
        <div className="mt-4 space-y-1.5">
          <PixelLoadingBar value={progress} />
          <p className="text-center text-[11px] text-muted-foreground">
            Photos and scans are read with OCR — this can take up to half a minute.
          </p>
        </div>
      ) : null}
    </SectionCard>
  );
}

function HowItWorks({ isAdmin }: { isAdmin: boolean }) {
  const steps = [
    { icon: <FileUp className="size-4" />, title: "Upload", text: "PDF or photo of a timetable, exam schedule or notice." },
    { icon: <PenLine className="size-4" />, title: "Check & edit", text: "Fix anything ORION misread. Nothing is published yet." },
    {
      icon: <Megaphone className="size-4" />,
      title: "Academic notices go live",
      text: "Quizzes, assignments and one-off class changes (cancelled, moved, extra) reach your class right away.",
    },
    {
      icon: <ShieldCheck className="size-4" />,
      title: isAdmin ? "You publish directly" : "Timetables & exams need approval",
      text: isAdmin
        ? "As an admin, what you publish goes live at once and is recorded in the audit log."
        : "An admin approves weekly timetable and exam schedule changes before they're updated.",
    },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {steps.map((s) => (
        <div key={s.title} className="surface-card p-4">
          <span className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary">{s.icon}</span>
          <p className="mt-2 text-sm font-semibold">{s.title}</p>
          <p className="text-xs text-muted-foreground">{s.text}</p>
        </div>
      ))}
    </div>
  );
}

// --------------------------------------------------------------- timetable

function TimetablePanel({
  payload,
  source,
  target,
  isAdmin,
  onPayload,
  onStartManual,
  onSubmitted,
  onUpload,
}: {
  payload: TimetablePayload | null;
  source: { method: string; confidence: number; path: string | null } | null;
  target: TargetClass | null;
  isAdmin: boolean;
  onPayload: (p: TimetablePayload) => void;
  onStartManual: (p: TimetablePayload) => void;
  onSubmitted: () => void;
  onUpload: () => void;
}) {
  const [validFrom, setValidFrom] = useState(todayIso());
  const [note, setNote] = useState("");

  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: () => apiGet<{ course_code: string; course_name: string }[]>("/courses"),
    staleTime: 10 * 60 * 1000,
  });

  const loadCurrent = useMutation({
    mutationFn: () => apiGet<TimetablePayload>(`/cr/timetable/current${targetQuery(target)}`),
    onSuccess: onStartManual,
    onError: (err) => toast.error(errorText(err, "Couldn't load your current timetable")),
  });

  const check = useMutation({
    mutationFn: (entries: DraftEntry[]) =>
      apiPost<TimetablePayload>("/cr/timetable/check", { entries: stripResolved(entries), target: target ?? undefined }),
    onSuccess: onPayload,
    onError: (err) => toast.error(errorText(err, "Couldn't check the timetable")),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiPost("/cr/timetable/submit", {
        entries: stripResolved(payload?.entries ?? []),
        valid_from: validFrom || undefined,
        note: note || undefined,
        upload_path: source?.path ?? undefined,
        target: target ?? undefined,
      }),
    onSuccess: () => {
      toast.success(
        isAdmin
          ? "Published — the class's timetable is updated."
          : "Sent to an admin for approval. Your class's timetable changes once it's approved.",
      );
      setNote("");
      onSubmitted();
    },
    onError: (err) => toast.error(errorText(err, "Couldn't submit the timetable")),
  });

  if (!payload) {
    return (
      <SectionCard title="Timetable" description={isAdmin ? "Change a class's weekly timetable" : "Propose a change to your class's weekly timetable"}>
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <Table2 className="size-8 text-primary" />
          <p className="max-w-md text-sm text-muted-foreground">
            Upload the new timetable (PDF or photo), or start from the current timetable and edit it by hand. Permanent
            changes (a class moving to another day for the rest of the term) are made here.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            <Button onClick={onUpload}>
              <FileUp className="size-4" /> Upload a file
            </Button>
            <Button variant="outline" onClick={() => loadCurrent.mutate()} disabled={loadCurrent.isPending}>
              <PenLine className="size-4" /> {loadCurrent.isPending ? "Loading…" : "Edit current timetable"}
            </Button>
          </div>
        </div>
      </SectionCard>
    );
  }

  const errors = payload.issues.filter((i) => i.severity === "error").length;

  return (
    <div className="space-y-4">
      <SectionCard
        title={payload.class_label}
        description={source ? `${METHOD_LABELS[source.method] ?? source.method}${source.method === "vision" ? ` · ${Math.round(source.confidence * 100)}% legible` : ""}` : ""}
        action={<DiffSummary diff={payload.diff} currentCount={payload.current_count} />}
      >
        <div className="space-y-3">
          {payload.notes.map((n) => (
            <p key={n} className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
              {n}
            </p>
          ))}
          <TimetableEditor
            entries={payload.entries}
            issues={payload.issues}
            courses={coursesQuery.data ?? []}
            busy={check.isPending}
            onChange={(entries) => {
              onPayload({ ...payload, entries });
              check.mutate(entries);
            }}
          />
          <IssueList issues={payload.issues} entries={payload.entries} />
        </div>
      </SectionCard>

      <SectionCard
        title={isAdmin ? "Publish" : "Send for approval"}
        description={isAdmin ? "The class's timetable changes as soon as you publish" : "Nothing changes for your class until an admin approves it"}
      >
        <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
          <div className="space-y-1.5">
            <Label htmlFor="tt-from">Takes effect from</Label>
            <Input id="tt-from" type="date" min={todayIso()} value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tt-note">Note for the admin (optional)</Label>
            <Input
              id="tt-note"
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. CSE 312 lab moved to Tuesday per the HoD's circular"
            />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {errors ? `${errors} problem${errors > 1 ? "s" : ""} to fix first.` : `${payload.entries.length} periods ready.`}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => loadCurrent.mutate()} disabled={loadCurrent.isPending}>
              Start over from current
            </Button>
            <Button onClick={() => submit.mutate()} disabled={!payload.can_submit || submit.isPending || check.isPending}>
              <Send className="size-4" /> {submit.isPending ? "Sending…" : isAdmin ? "Publish timetable" : "Submit for approval"}
            </Button>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

// -------------------------------------------------------------------- exams

function ExamsPanel({
  payload,
  uploadPath,
  target,
  isAdmin,
  onPayload,
  onSubmitted,
  onUpload,
}: {
  payload: ExamPayload | null;
  uploadPath: string | null;
  target: TargetClass | null;
  isAdmin: boolean;
  onPayload: (p: ExamPayload) => void;
  onSubmitted: () => void;
  onUpload: () => void;
}) {
  const [examType, setExamType] = useState(payload?.exam_type ?? "end_sem");
  const [note, setNote] = useState("");
  useEffect(() => {
    if (payload?.exam_type) setExamType(payload.exam_type);
  }, [payload?.exam_type]);

  const coursesQuery = useQuery({
    queryKey: ["courses"],
    queryFn: () => apiGet<{ course_code: string; course_name: string }[]>("/courses"),
    staleTime: 10 * 60 * 1000,
  });
  const scopeTarget = isAdmin
    ? target
      ? { semester: target.semester, department: target.department ?? undefined }
      : payload
        ? { semester: payload.scope.semester, department: payload.scope.department ?? undefined }
        : null
    : null;

  const loadCurrent = useMutation({
    mutationFn: () => {
      const q = new URLSearchParams({ exam_type: examType });
      if (scopeTarget) {
        q.set("semester", String(scopeTarget.semester));
        if (scopeTarget.department) q.set("department", scopeTarget.department);
      }
      return apiGet<ExamPayload>(`/cr/exams/current?${q.toString()}`);
    },
    onSuccess: onPayload,
    onError: (err) => toast.error(errorText(err, "Couldn't load the exam schedule")),
  });

  const strip = (entries: ExamEntry[]) => entries.map(({ in_catalogue: _c, ...rest }) => rest);

  const check = useMutation({
    mutationFn: (args: { entries: ExamEntry[]; exam_type: string }) =>
      apiPost<ExamPayload>("/cr/exams/check", {
        entries: strip(args.entries),
        exam_type: args.exam_type,
        target: scopeTarget ?? undefined,
      }),
    onSuccess: onPayload,
    onError: (err) => toast.error(errorText(err, "Couldn't check the exams")),
  });

  const submit = useMutation({
    mutationFn: () =>
      apiPost("/cr/exams/submit", {
        entries: strip(payload?.entries ?? []),
        exam_type: examType,
        note: note || undefined,
        upload_path: uploadPath ?? undefined,
        target: scopeTarget ?? undefined,
      }),
    onSuccess: () => {
      toast.success(isAdmin ? "Published — students can see the exam schedule now." : "Sent to an admin for approval.");
      setNote("");
      onSubmitted();
    },
    onError: (err) => toast.error(errorText(err, "Couldn't submit the exam schedule")),
  });

  if (!payload) {
    return (
      <SectionCard title="Exam schedule" description={isAdmin ? "Publish an exam timetable" : "Propose your department's exam timetable"}>
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <GraduationCap className="size-8 text-primary" />
          <p className="max-w-md text-sm text-muted-foreground">
            Upload the exam timetable (any layout — a date × department grid, a list, or a photo) and ORION turns it
            into an editable list. Or start from the current schedule.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button onClick={onUpload}>
              <FileUp className="size-4" /> Upload a file
            </Button>
            <select className={`${selectClass} w-44`} value={examType} onChange={(e) => setExamType(e.target.value)}>
              {EXAM_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            <Button
              variant="outline"
              onClick={() => loadCurrent.mutate()}
              disabled={loadCurrent.isPending || (isAdmin && !scopeTarget)}
            >
              <PenLine className="size-4" /> {loadCurrent.isPending ? "Loading…" : "Edit current / start new"}
            </Button>
          </div>
        </div>
      </SectionCard>
    );
  }

  const errors = payload.issues.filter((i) => i.severity === "error");
  const warnings = payload.issues.filter((i) => i.severity === "warning");
  const general = payload.issues.filter((i) => i.index < 0);

  return (
    <div className="space-y-4">
      <SectionCard
        title={`${payload.exam_type_label} exams · ${payload.scope_label}`}
        description={`${payload.entries.length} exam${payload.entries.length === 1 ? "" : "s"}${
          payload.departments.length > 1 ? ` across ${payload.departments.length} departments` : ""
        }`}
        action={<ExamDiffSummary diff={payload.diff} currentCount={payload.current_count} />}
      >
        <div className="space-y-3">
          {payload.notes.map((n) => (
            <p key={n} className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
              {n}
            </p>
          ))}
          {general.map((i) => (
            <p key={i.message} className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
              {i.message}
            </p>
          ))}
          <div className="flex items-center gap-2">
            <Label htmlFor="ex-type" className="text-xs">
              Exam type
            </Label>
            <select
              id="ex-type"
              className={`${selectClass} w-52`}
              value={examType}
              onChange={(e) => {
                setExamType(e.target.value);
                check.mutate({ entries: payload.entries, exam_type: e.target.value });
              }}
            >
              {EXAM_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <ExamEditor
            entries={payload.entries}
            issues={payload.issues}
            courses={coursesQuery.data ?? []}
            showDepartment={payload.departments.length > 1}
            onChange={(entries) => {
              onPayload({ ...payload, entries });
              check.mutate({ entries, exam_type: examType });
            }}
          />
          {errors.length || warnings.length ? (
            <div className="space-y-1 text-xs">
              {errors.filter((i) => i.index >= 0).slice(0, 8).map((i, n) => (
                <p key={`e${n}`} className="text-destructive">
                  ✕ {i.message}
                </p>
              ))}
              {warnings.length ? (
                <details>
                  <summary className="cursor-pointer text-warning-foreground">{warnings.length} worth a look (won't block)</summary>
                  {warnings.map((i, n) => (
                    <p key={`w${n}`}>⚠ {i.message}</p>
                  ))}
                </details>
              ) : null}
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title={isAdmin ? "Publish" : "Send for approval"}
        description={isAdmin ? "Replaces this scope's current exam schedule as soon as you publish" : "An admin approves it before students see it"}
      >
        <div className="space-y-1.5">
          <Label htmlFor="ex-note">Note (optional)</Label>
          <Input id="ex-note" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} placeholder="e.g. From the exam cell circular dated 25 Sep" />
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {errors.length ? `${errors.length} problem${errors.length > 1 ? "s" : ""} to fix first.` : `${payload.entries.length} exams ready.`}
          </p>
          <Button onClick={() => submit.mutate()} disabled={!payload.can_submit || submit.isPending || check.isPending}>
            <Send className="size-4" /> {submit.isPending ? "Sending…" : isAdmin ? "Publish exam schedule" : "Submit for approval"}
          </Button>
        </div>
      </SectionCard>
    </div>
  );
}

// ------------------------------------------------------------ announcement

const CHANGE_LABELS: Record<string, string> = { cancel: "Cancelled", reschedule: "Rescheduled", extra: "Extra class" };

/** The one-off class changes a class-update notice announces, editable. */
function ClassChangesForm({
  preview,
  onChange,
}: {
  preview: ClassChangePreview;
  onChange: (changes: ClassChange[]) => void;
}) {
  const changes = preview.changes;
  const byIndex = new Map<number, string[]>();
  for (const i of preview.issues) if (i.index >= 0) byIndex.set(i.index, [...(byIndex.get(i.index) ?? []), i.message]);
  const update = (i: number, patch: Partial<ClassChange>) => onChange(changes.map((c, n) => (n === i ? { ...c, ...patch } : c)));
  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3">
      <p className="text-xs font-semibold">
        Class changes for {preview.class_label} — these update the schedule students see, for that date only
      </p>
      {changes.map((c, i) => (
        <div key={i} className={`space-y-2 rounded-md border bg-background p-2 ${byIndex.get(i) ? "border-destructive/50" : "border-border"}`}>
          <div className="grid gap-2 sm:grid-cols-3">
            <select className={selectClass} value={c.change_type} onChange={(e) => update(i, { change_type: e.target.value })}>
              {Object.entries(CHANGE_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <select
              className={selectClass}
              value={c.course_code ?? ""}
              onChange={(e) => {
                const course = preview.courses.find((x) => x.course_code === e.target.value);
                update(i, { course_code: e.target.value || null, course_name: course?.course_name ?? null });
              }}
            >
              <option value="">Course…</option>
              {preview.courses.map((x) => (
                <option key={x.course_code} value={x.course_code}>
                  {x.course_code} {x.course_name ? `· ${x.course_name}` : ""}
                </option>
              ))}
            </select>
            <Input type="date" value={c.change_date ?? ""} onChange={(e) => update(i, { change_date: e.target.value || null })} />
          </div>
          {c.change_type !== "cancel" ? (
            <div className="grid gap-2 sm:grid-cols-3">
              {c.change_type === "reschedule" ? (
                <div className="space-y-1">
                  <Label className="text-[11px]">New date</Label>
                  <Input type="date" value={c.new_date ?? ""} onChange={(e) => update(i, { new_date: e.target.value || null })} />
                </div>
              ) : null}
              <div className="space-y-1">
                <Label className="text-[11px]">Starts</Label>
                <Input type="time" value={c.new_start ?? ""} onChange={(e) => update(i, { new_start: e.target.value || null })} />
              </div>
              <div className="space-y-1">
                <Label className="text-[11px]">Ends</Label>
                <Input type="time" value={c.new_end ?? ""} onChange={(e) => update(i, { new_end: e.target.value || null })} />
              </div>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-destructive">{(byIndex.get(i) ?? []).join(" ")}</p>
            <Button size="sm" variant="ghost" onClick={() => onChange(changes.filter((_, n) => n !== i))}>
              <Trash2 className="size-3.5" /> Remove
            </Button>
          </div>
        </div>
      ))}
      <Button
        size="sm"
        variant="outline"
        onClick={() => onChange([...changes, { change_type: "cancel", change_date: todayIso(), course_code: null }])}
      >
        <Plus className="size-4" /> Add a change
      </Button>
      {preview.notes.map((n) => (
        <p key={n} className="text-[11px] text-muted-foreground">
          {n}
        </p>
      ))}
    </div>
  );
}

function AnnouncementPanel({
  seed,
  uploadPath,
  target,
  isAdmin,
  onPermanent,
  onPosted,
}: {
  seed: AnnouncementDraft | null;
  uploadPath: string | null;
  target: TargetClass | null;
  isAdmin: boolean;
  onPermanent: () => void;
  onPosted: () => void;
}) {
  const [title, setTitle] = useState(seed?.title ?? "");
  const [content, setContent] = useState(seed?.content ?? "");
  const [category, setCategory] = useState(seed?.category ?? "");
  const [eventDate, setEventDate] = useState(seed?.event_date ?? "");
  const [eventTime, setEventTime] = useState(seed?.event_time ?? "");
  const [validUntil, setValidUntil] = useState(seed?.valid_until ?? "");
  const [touched, setTouched] = useState({ category: !!seed, date: !!seed?.event_date });
  const [everyone, setEveryone] = useState(false);
  const [changes, setChanges] = useState<ClassChangePreview | null>(null);
  const hasClass = !isAdmin || Boolean(target?.section);

  const changePreview = useMutation({
    mutationFn: (body: { text?: string; changes?: ClassChange[] }) =>
      apiPost<ClassChangePreview>("/cr/class-changes/preview", { ...body, target: target ?? undefined }),
    onSuccess: setChanges,
  });

  const preview = useMutation({
    mutationFn: () =>
      apiPost<AnnouncementDraft & { permanent_change?: boolean; class_changes?: boolean }>("/cr/announcements/preview", {
        title,
        content,
        category: category || undefined,
      }),
    onSuccess: (d) => {
      // A one-off class change: read the changes out of the text (once; the CR edits them after).
      if (d.class_changes && hasClass && !changes && !changePreview.isPending) {
        changePreview.mutate({ text: `${title}\n${content}` });
      }
      // Fill suggestions only where the CR hasn't chosen something.
      if (!touched.category && d.category) setCategory(d.category);
      if (!touched.date && d.event_date) {
        setEventDate(d.event_date);
        if (d.event_time && !eventTime) setEventTime(d.event_time);
      }
      if (!validUntil && d.valid_until) setValidUntil(d.valid_until);
      if (!title.trim() && d.title) setTitle(d.title);
    },
  });

  // Re-check the decision as the text changes (debounced).
  useEffect(() => {
    if (!content.trim()) return;
    const id = window.setTimeout(() => preview.mutate(), 600);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, content, category]);

  const post = useMutation({
    mutationFn: () =>
      apiPost<{ id: number; status: string; auto_published: boolean; reason: string }>("/cr/announcements", {
        title,
        content,
        category: category || undefined,
        event_date: eventDate || undefined,
        event_time: eventTime || undefined,
        valid_until: validUntil || undefined,
        upload_path: uploadPath ?? undefined,
        target: target ?? undefined,
        everyone: isAdmin && everyone,
        changes: category === "CLASS_UPDATE" && changes?.changes.length ? changes.changes : undefined,
      }),
    onSuccess: (r) => {
      toast.success(
        r.status === "active"
          ? category === "CLASS_UPDATE" && changes?.changes.length
            ? "Posted — the class's schedule now shows the change"
            : "Posted — it's live now"
          : "Sent to an admin for approval",
      );
      onPosted();
    },
    onError: (err) => toast.error(errorText(err, "Couldn't post the announcement")),
  });

  const decision = preview.data?.decision;
  const sensitive = preview.data?.sensitive ?? [];
  const isClassUpdate = category === "CLASS_UPDATE" || preview.data?.category === "CLASS_UPDATE";
  const blockedChanges = isClassUpdate && changes !== null && changes.changes.length > 0 && !changes.can_post;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <SectionCard
        title={seed ? "Check the notice ORION read" : "New announcement"}
        description={seed ? "Edit anything that's wrong before posting" : "Type it — ORION fills in the category and date"}
      >
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="an-title">Title</Label>
            <Input id="an-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. AI quiz 2 on Wednesday" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="an-content">Message</Label>
            <Textarea
              id="an-content"
              rows={6}
              value={content}
              maxLength={8000}
              onChange={(e) => setContent(e.target.value)}
              placeholder="CSE 311 quiz 2 on 14 Oct at 10:30 AM in LH-2. Units 3–4."
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="an-cat">Category</Label>
              <select
                id="an-cat"
                className={selectClass}
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setTouched((t) => ({ ...t, category: true }));
                }}
              >
                <option value="">Let ORION decide</option>
                <optgroup label="Academic — shared with your class right away">
                  {ACADEMIC_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Other — reviewed by an admin first">
                  {OTHER_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {CATEGORY_LABELS[c]}
                    </option>
                  ))}
                </optgroup>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="an-until">Show until</Label>
              <Input id="an-until" type="date" min={todayIso()} value={validUntil} onChange={(e) => setValidUntil(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="an-date">Event date (optional)</Label>
              <Input
                id="an-date"
                type="date"
                value={eventDate}
                onChange={(e) => {
                  setEventDate(e.target.value);
                  setTouched((t) => ({ ...t, date: true }));
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="an-time">Time (optional)</Label>
              <Input id="an-time" type="time" value={eventTime} onChange={(e) => setEventTime(e.target.value)} />
            </div>
          </div>
          {isAdmin ? (
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={everyone} onChange={(e) => setEveryone(e.target.checked)} />
              Send to everyone (otherwise it goes to the class picked above)
            </label>
          ) : null}
          {isClassUpdate && preview.data?.permanent_change ? (
            <div className="rounded-lg border border-warning/50 bg-warning/10 p-3 text-xs">
              <p className="font-semibold">This sounds like a permanent change to the weekly timetable.</p>
              <p className="mt-1 text-muted-foreground">
                Permanent changes are made in the timetable editor{isAdmin ? "" : " and approved by an admin"}; this
                notice alone won't change the timetable.
              </p>
              <Button size="sm" className="mt-2" onClick={onPermanent}>
                <Table2 className="size-4" /> Open the timetable editor
              </Button>
            </div>
          ) : isClassUpdate && hasClass ? (
            changes ? (
              <ClassChangesForm
                preview={changes}
                onChange={(list) => {
                  setChanges({ ...changes, changes: list });
                  changePreview.mutate({ changes: list });
                }}
              />
            ) : (
              <Button size="sm" variant="outline" onClick={() => changePreview.mutate({ text: `${title}\n${content}` })}>
                <CalendarClock className="size-4" /> {changePreview.isPending ? "Reading the changes…" : "Add the class changes"}
              </Button>
            )
          ) : null}
        </div>
      </SectionCard>

      <div className="space-y-4">
        <SectionCard title="What happens when you post">
          {!content.trim() ? (
            <p className="text-xs text-muted-foreground">Write the message to see where it goes.</p>
          ) : decision ? (
            <div className="space-y-2">
              <PixelBadge tone={decision.publish_now ? "success" : "warning"}>
                {decision.publish_now ? "Goes live now" : "Admin review"}
              </PixelBadge>
              <p className="text-xs text-muted-foreground">{decision.reason}</p>
              {sensitive.length ? (
                <p className="rounded-md border border-warning/40 bg-warning/10 p-2 text-xs">
                  Looks like it contains {sensitive.join(", ")}. Remove it if it isn't needed.
                </p>
              ) : null}
              {eventDate ? (
                <p className="flex items-center gap-1.5 text-xs">
                  <CalendarClock className="size-3.5 text-primary" />
                  {new Date(`${eventDate}T00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
                  {eventTime ? ` · ${eventTime}` : ""}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">Checking…</p>
          )}
        </SectionCard>
        <Button
          className="w-full"
          disabled={!title.trim() || !content.trim() || post.isPending || blockedChanges || (isAdmin && !everyone && !target?.section)}
          onClick={() => post.mutate()}
        >
          <Send className="size-4" />
          {post.isPending
            ? "Posting…"
            : isAdmin
              ? everyone
                ? "Post to everyone"
                : "Post to this class"
              : decision?.publish_now
                ? "Post to my class"
                : "Send for approval"}
        </Button>
        {blockedChanges ? <p className="text-center text-[11px] text-destructive">Fix the class changes first.</p> : null}
      </div>
    </div>
  );
}
