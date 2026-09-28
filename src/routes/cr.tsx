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
import { CalendarClock, CheckCircle2, Clock, FileUp, Megaphone, PenLine, Send, ShieldCheck, Table2 } from "lucide-react";
import { toast } from "sonner";
import { apiGet, apiPost, apiUpload, ApiError } from "@/lib/api-client";
import { requireRole } from "@/lib/route-guards";
import {
  ACADEMIC_CATEGORIES,
  CATEGORY_LABELS,
  MAX_UPLOAD_BYTES,
  METHOD_LABELS,
  OTHER_CATEGORIES,
  prepareUpload,
  stripResolved,
  type AnnouncementDraft,
  type DraftEntry,
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

function CrPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("upload");
  const [lastUpload, setLastUpload] = useState<UploadResult | null>(null);
  const [timetable, setTimetable] = useState<TimetablePayload | null>(null);
  const [timetableSource, setTimetableSource] = useState<{ method: string; confidence: number; path: string | null } | null>(
    null,
  );
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

  const announcements = announcementsQuery.data ?? [];
  const submissions = submissionsQuery.data ?? [];
  const live = announcements.filter((a) => a.status === "active").length;
  const waiting =
    announcements.filter((a) => a.status === "pending").length +
    submissions.filter((s) => s.approval_status === "pending").length;

  const onUploaded = (result: UploadResult) => {
    setLastUpload(result);
    if (result.kind === "timetable" && result.timetable) {
      setTimetable(result.timetable);
      setTimetableSource({ method: result.method, confidence: result.confidence, path: result.upload_path });
      setTab("timetable");
    } else {
      setAnnouncementSeed((s) => ({ draft: result.announcement, path: result.upload_path, key: s.key + 1 }));
      setTab("announcement");
    }
  };

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge="Class representative"
          title="CR Portal"
          subtitle="Upload a timetable or notice — ORION reads it, you check it, and it reaches your class."
        />

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
          <StatCard label="Live announcements" value={live} tone="success" icon={<CheckCircle2 className="size-4" />} />
          <StatCard label="Waiting for admin" value={waiting} tone="warning" icon={<Clock className="size-4" />} />
          <StatCard
            label="Timetable changes"
            value={submissions.length}
            icon={<Table2 className="size-4" />}
          />
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value="upload">
              <FileUp className="size-4" /> Upload
            </TabsTrigger>
            <TabsTrigger value="timetable">
              <Table2 className="size-4" /> Timetable
            </TabsTrigger>
            <TabsTrigger value="announcement">
              <Megaphone className="size-4" /> Announcement
            </TabsTrigger>
            <TabsTrigger value="history">
              <Clock className="size-4" /> History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="upload" className="space-y-4 pt-4">
            <UploadPanel onUploaded={onUploaded} />
            {lastUpload?.text ? (
              <SectionCard title="Text ORION read from your last file" description={METHOD_LABELS[lastUpload.method] ?? ""}>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">
                  {lastUpload.text}
                </pre>
              </SectionCard>
            ) : null}
            <HowItWorks />
          </TabsContent>

          <TabsContent value="timetable" className="pt-4">
            <TimetablePanel
              payload={timetable}
              source={timetableSource}
              onPayload={setTimetable}
              onStartManual={(p) => {
                setTimetable(p);
                setTimetableSource({ method: "manual", confidence: 1, path: null });
              }}
              onSubmitted={() => {
                setTimetable(null);
                setTimetableSource(null);
                queryClient.invalidateQueries({ queryKey: ["cr", "timetable-submissions"] });
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
              onPosted={() => {
                queryClient.invalidateQueries({ queryKey: ["cr", "announcements"] });
                queryClient.invalidateQueries({ queryKey: ["announcements"] });
                setAnnouncementSeed((s) => ({ draft: null, path: null, key: s.key + 1 }));
                setTab("history");
              }}
            />
          </TabsContent>

          <TabsContent value="history" className="space-y-4 pt-4">
            <SectionCard title="Timetable changes" contentClassName="p-0">
              {submissionsQuery.isLoading ? (
                <p className="p-4 text-sm text-muted-foreground">Loading…</p>
              ) : submissions.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No timetable changes submitted yet.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {submissions.map((s) => (
                    <li key={s.id} className="flex flex-wrap items-center gap-3 p-4">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">
                          {s.periods} periods{s.valid_from ? ` · from ${s.valid_from}` : ""}
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
                          {a.auto_published ? " · shared with your class directly" : ""}
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

function UploadPanel({ onUploaded }: { onUploaded: (r: UploadResult) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = await prepareUpload(file);
      if (body.size > MAX_UPLOAD_BYTES) throw new ApiError(400, "The file is larger than 4 MB. Take a smaller photo or compress the PDF.");
      return apiUpload<UploadResult>("/cr/uploads", body);
    },
    onSuccess: (result) => {
      if (result.kind === "timetable" && result.timetable && !result.timetable.entries.length) {
        toast.warning("No timetable for your class was found in that file.");
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
    <SectionCard title="Upload a timetable or notice" description="PDF, JPEG, PNG or WebP · up to 4 MB">
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
          A timetable becomes an editable grid for your class. A notice (quiz, assignment, class change…) becomes
          an announcement you can review before posting. Photos work too.
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

function HowItWorks() {
  const steps = [
    { icon: <FileUp className="size-4" />, title: "Upload", text: "PDF or photo of a timetable or notice." },
    { icon: <PenLine className="size-4" />, title: "Check & edit", text: "Fix anything ORION misread. Nothing is published yet." },
    {
      icon: <Megaphone className="size-4" />,
      title: "Academic notices go live",
      text: "Quizzes, exams, assignments and class changes reach your class right away.",
    },
    {
      icon: <ShieldCheck className="size-4" />,
      title: "Timetables need approval",
      text: "An admin approves the change before your class's timetable is updated.",
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
  onPayload,
  onStartManual,
  onSubmitted,
  onUpload,
}: {
  payload: TimetablePayload | null;
  source: { method: string; confidence: number; path: string | null } | null;
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
    mutationFn: () => apiGet<TimetablePayload>("/cr/timetable/current"),
    onSuccess: onStartManual,
    onError: (err) => toast.error(errorText(err, "Couldn't load your current timetable")),
  });

  const check = useMutation({
    mutationFn: (entries: DraftEntry[]) =>
      apiPost<TimetablePayload>("/cr/timetable/check", { entries: stripResolved(entries) }),
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
      }),
    onSuccess: () => {
      toast.success("Sent to an admin for approval. Your class's timetable changes once it's approved.");
      setNote("");
      onSubmitted();
    },
    onError: (err) => toast.error(errorText(err, "Couldn't submit the timetable")),
  });

  if (!payload) {
    return (
      <SectionCard title="Timetable" description="Propose a change to your class's timetable">
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <Table2 className="size-8 text-primary" />
          <p className="max-w-md text-sm text-muted-foreground">
            Upload the new timetable (PDF or photo), or start from your class's current timetable and edit it by hand.
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

      <SectionCard title="Send for approval" description="Nothing changes for your class until an admin approves it">
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
              <Send className="size-4" /> {submit.isPending ? "Sending…" : "Submit for approval"}
            </Button>
          </div>
        </div>
      </SectionCard>
    </div>
  );
}

// ------------------------------------------------------------ announcement

function AnnouncementPanel({
  seed,
  uploadPath,
  onPosted,
}: {
  seed: AnnouncementDraft | null;
  uploadPath: string | null;
  onPosted: () => void;
}) {
  const [title, setTitle] = useState(seed?.title ?? "");
  const [content, setContent] = useState(seed?.content ?? "");
  const [category, setCategory] = useState(seed?.category ?? "");
  const [eventDate, setEventDate] = useState(seed?.event_date ?? "");
  const [eventTime, setEventTime] = useState(seed?.event_time ?? "");
  const [validUntil, setValidUntil] = useState(seed?.valid_until ?? "");
  const [touched, setTouched] = useState({ category: !!seed, date: !!seed?.event_date });

  const preview = useMutation({
    mutationFn: () => apiPost<AnnouncementDraft>("/cr/announcements/preview", { title, content, category: category || undefined }),
    onSuccess: (d) => {
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
      }),
    onSuccess: (r) => {
      toast.success(r.status === "active" ? "Posted — your class can see it now" : "Sent to an admin for approval");
      onPosted();
    },
    onError: (err) => toast.error(errorText(err, "Couldn't post the announcement")),
  });

  const decision = preview.data?.decision;
  const sensitive = preview.data?.sensitive ?? [];
  const selectClass =
    "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

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
          disabled={!title.trim() || !content.trim() || post.isPending}
          onClick={() => post.mutate()}
        >
          <Send className="size-4" />
          {post.isPending ? "Posting…" : decision?.publish_now ? "Post to my class" : "Send for approval"}
        </Button>
      </div>
    </div>
  );
}
