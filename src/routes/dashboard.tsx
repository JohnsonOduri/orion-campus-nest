import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  CalendarDays,
  CloudSun,
  MapPin,
  Sparkles,
  UtensilsCrossed,
  Users,
  Megaphone,
  Upload,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { useProfile } from "@/hooks/use-profile";
import { Badge } from "@/components/ui/badge";
import { PixelBadge, PixelDivider, PixelParticles, PixelSkyline } from "@/components/pixel/pixel-art";
import { assignments, exams, student } from "@/lib/mock-data";
import {
  DAY_NAMES,
  deriveStatus,
  entryLabel,
  formatTime,
  todaysEntries,
  type StudentContext,
  type TimetableEntry,
} from "@/lib/timetable";

type TimetableResponse = { student: StudentContext | null; entries: TimetableEntry[] };
type FacultyMember = { id: number; full_name: string; initials: string | null; office_location: string | null };
type MessRow = { id: number; meal: string; items: string[] };
type Announcement = { id: number; title: string; content: string; category: string | null; created_at: string; published_at: string | null };

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — ORION Campus Companion" },
      { name: "description", content: "Today's classes, attendance, deadlines, mess menu and AI suggestions at a glance." },
      { property: "og:title", content: "ORION Dashboard" },
      { property: "og:description", content: "Your campus day, summarised by ORION." },
    ],
  }),
  component: Dashboard,
});

type CrRequestStatus = {
  id: number;
  approval_status: "pending" | "approved" | "rejected";
  rejection_reason: string | null;
} | null;

function CrAccessCard() {
  const { data: profile } = useProfile();
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ["cr", "access-request", "status"],
    queryFn: () => apiGet<CrRequestStatus>("/cr/access-request/status"),
    enabled: profile?.role === "STUDENT",
  });

  const submit = useMutation({
    mutationFn: () => apiPost("/cr/access-request", {}),
    onSuccess: () => {
      toast.success("CR access request submitted");
      queryClient.invalidateQueries({ queryKey: ["cr", "access-request", "status"] });
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Could not submit request");
    },
  });

  if (!profile || profile.role !== "STUDENT") return null;

  const status = statusQuery.data;

  return (
    <SectionCard title="Become a Class Representative" description="Author announcements once approved by an admin">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Upload className="size-4" />
          {status?.approval_status === "pending" && "Your CR access request is pending admin review."}
          {status?.approval_status === "rejected" &&
            `Your last request was rejected${status.rejection_reason ? `: ${status.rejection_reason}` : "."}`}
          {!status && "Request CR access to author campus announcements."}
        </div>
        <Button
          size="sm"
          disabled={status?.approval_status === "pending" || submit.isPending}
          onClick={() => submit.mutate()}
        >
          {status?.approval_status === "pending"
            ? "Pending"
            : status?.approval_status === "rejected"
              ? "Request again"
              : "Request CR access"}
        </Button>
      </div>
    </SectionCard>
  );
}

function Dashboard() {
  const dayQuery = useQuery({
    queryKey: ["timetable", "day"],
    queryFn: () => apiGet<TimetableResponse>("/timetable/day"),
  });
  const now = new Date();
  const dayEntries = todaysEntries(dayQuery.data?.entries ?? [], now);
  const withStatus = dayEntries.map((e) => ({ entry: e, status: deriveStatus(e, now) }));
  const live = withStatus.find((x) => x.status === "live")?.entry;
  const next = withStatus.find((x) => x.status === "upcoming")?.entry;

  const facultyQuery = useQuery({
    queryKey: ["faculty"],
    queryFn: () => apiGet<FacultyMember[]>("/faculty"),
  });
  const messQuery = useQuery({
    queryKey: ["mess", "today"],
    queryFn: () => apiGet<MessRow[]>("/mess/today"),
  });
  const announcementsQuery = useQuery({
    queryKey: ["announcements"],
    queryFn: () => apiGet<Announcement[]>("/announcements"),
  });

  return (
    <AppShell>
      <div className="space-y-5">
        <CrAccessCard />
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-2xl border border-border gradient-campus p-5 sm:p-7"
        >
          <PixelParticles count={14} />
          <div className="relative z-10 flex flex-wrap items-start justify-between gap-4">
            <div>
              <PixelBadge tone="muted" className="bg-primary-foreground/15 text-primary-foreground">
                Semester {student.semester} · {student.branch.split(" ")[0]}
              </PixelBadge>
              <h1 className="mt-3 text-2xl font-bold tracking-tight text-primary-foreground sm:text-3xl">
                Good morning, Aarav 👋
              </h1>
              <p className="mt-1.5 max-w-md text-sm text-primary-foreground/85">
                {live ? `${entryLabel(live)} is live${live.room ? ` in ${live.room}` : ""}.` : "No class running right now."}{" "}
                {next ? `Next: ${entryLabel(next)} at ${formatTime(next.start_time)}.` : ""}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild variant="secondary" size="sm">
                  <Link to="/ai">
                    <Sparkles className="size-4" /> Ask ORION
                  </Link>
                </Button>
                <Button asChild variant="secondary" size="sm">
                  <Link to="/timetable">
                    <CalendarDays className="size-4" /> Timetable
                  </Link>
                </Button>
                <Button asChild variant="secondary" size="sm">
                  <Link to="/mess">
                    <UtensilsCrossed className="size-4" /> Mess
                  </Link>
                </Button>
              </div>
            </div>
            <div className="hidden shrink-0 text-right sm:block">
              <p className="font-mono text-3xl font-bold text-primary-foreground">11:42</p>
              <p className="text-xs text-primary-foreground/80">Tue, 04 Aug 2026</p>
              <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-primary-foreground/85">
                <CloudSun className="size-4" /> 29°C · Humid, Kottayam
              </p>
            </div>
          </div>
          <div className="pointer-events-none absolute right-0 bottom-0 left-0 opacity-40">
            <PixelSkyline />
          </div>
        </motion.section>

        <div className="grid gap-5">
          <SectionCard
            title="Today's classes"
            description={`${DAY_NAMES[now.getDay()] ?? "Today"} · ${dayEntries.length} session${dayEntries.length === 1 ? "" : "s"}`}
            action={
              <Button asChild variant="ghost" size="sm">
                <Link to="/timetable">View week</Link>
              </Button>
            }
            contentClassName="p-0"
          >
            {dayQuery.isLoading ? (
              <p className="p-4 text-sm text-muted-foreground">Loading…</p>
            ) : dayEntries.length === 0 ? (
              <p className="p-4 text-sm text-muted-foreground">No classes scheduled today.</p>
            ) : (
              <ul className="divide-y divide-border">
                {withStatus.map(({ entry: c, status }) => (
                  <li key={c.id} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50 sm:px-5">
                    <div className="w-14 shrink-0 font-mono text-xs text-muted-foreground">
                      <p className="font-semibold text-foreground">{formatTime(c.start_time)}</p>
                      <p>{formatTime(c.end_time)}</p>
                    </div>
                    <span
                      className="h-10 w-1 shrink-0 pixelated"
                      style={{
                        background:
                          status === "live" ? "var(--accent)" : status === "done" ? "var(--border)" : "var(--primary)",
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">
                        {entryLabel(c)}{" "}
                        {c.course_name && <span className="font-mono text-xs text-muted-foreground">{c.course_name}</span>}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {(c.faculty_names ?? []).join(", ") || "—"} · <MapPin className="inline size-3" /> {c.room ?? "—"}
                      </p>
                    </div>
                    {status === "live" ? (
                      <PixelBadge tone="success">Live</PixelBadge>
                    ) : status === "done" ? (
                      <PixelBadge tone="muted">Done</PixelBadge>
                    ) : (
                      <PixelBadge tone="primary">Soon</PixelBadge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <SectionCard title="Assignments" description="Due this fortnight">
            <ul className="space-y-3.5">
              {assignments.map((a) => (
                <li key={a.title}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-medium">{a.title}</p>
                    <PixelBadge tone={a.progress === 0 ? "danger" : "warning"}>{a.left}</PixelBadge>
                  </div>
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {a.course} · due {a.due}
                  </p>
                  <Progress value={a.progress} className="mt-2 h-1.5" />
                </li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title="Upcoming exams" description="Mid-semester block">
            <ul className="space-y-3">
              {exams
                .filter((e) => e.status === "upcoming")
                .map((e) => (
                  <li key={e.code} className="flex items-center gap-3 rounded-lg border border-border p-2.5">
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary/60 font-mono text-[10px] font-bold">
                      {e.date.split(" ")[0]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{e.title}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {e.time} · {e.venue} · Seat {e.seat}
                      </p>
                    </div>
                  </li>
                ))}
            </ul>
            <Button asChild variant="outline" size="sm" className="mt-4 w-full">
              <Link to="/exams">Hall tickets</Link>
            </Button>
          </SectionCard>

          <SectionCard title="Today at the mess">
            {messQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (messQuery.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No menu published for today.</p>
            ) : (
              <ul className="space-y-2.5">
                {(messQuery.data ?? []).map((m) => (
                  <li key={m.id} className="rounded-lg border border-border p-2.5">
                    <p className="text-sm font-medium capitalize">{m.meal}</p>
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{m.items.join(" · ")}</p>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </div>

        <PixelDivider className="opacity-60" />

        <div className="grid gap-5 lg:grid-cols-3">
          <SectionCard
            className="lg:col-span-2"
            title="Announcements"
            description="Pinned & recent"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link to="/announcements">See all</Link>
              </Button>
            }
          >
            {announcementsQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (announcementsQuery.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No announcements yet.</p>
            ) : (
              <ul className="space-y-3">
                {(announcementsQuery.data ?? []).slice(0, 3).map((a) => (
                  <li key={a.id} className="flex gap-3 rounded-lg border border-border p-3 hover-lift">
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                      <Megaphone className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-semibold">{a.title}</p>
                        <Badge variant="secondary" className="text-[10px]">
                          {a.category ?? "General"}
                        </Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{a.content}</p>
                      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                        {new Date(a.published_at ?? a.created_at).toLocaleDateString()}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Faculty directory">
              {facultyQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (
                <ul className="space-y-2.5">
                  {(facultyQuery.data ?? []).slice(0, 4).map((f) => (
                    <li key={f.id} className="flex items-center gap-2.5">
                      <span className="grid size-8 place-items-center rounded-lg bg-secondary/60 text-[11px] font-bold">
                        {f.initials ?? f.full_name[0]}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-medium">{f.full_name}</p>
                        {f.office_location && (
                          <p className="truncate font-mono text-[10px] text-muted-foreground">{f.office_location}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            <Button asChild variant="outline" size="sm" className="mt-4 w-full">
              <Link to="/faculty">
                <Users className="size-4" /> Directory
              </Link>
            </Button>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
