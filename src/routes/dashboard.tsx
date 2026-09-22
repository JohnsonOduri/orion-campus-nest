import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { CalendarDays, Sparkles, UtensilsCrossed, Users, Megaphone, Upload } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { SectionCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
import { useProfile } from "@/hooks/use-profile";
import { Badge } from "@/components/ui/badge";
import {
  PixelBadge,
  PixelDivider,
  PixelParticles,
  PixelSkyline,
} from "@/components/pixel/pixel-art";
import { titleCase, useCalendar, useMyCourses } from "@/lib/campus";
import { daysFromToday, formatDate, relativeDays } from "@/lib/dates";
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
type MessRow = { id: number; meal: string; items: string[] };
type Announcement = {
  id: number;
  title: string;
  content: string;
  category: string | null;
  created_at: string;
  published_at: string | null;
};

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — ORION Campus Companion" },
      {
        name: "description",
        content: "Today's classes, upcoming dates, the mess menu and announcements at a glance.",
      },
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
    <SectionCard
      title="Become a Class Representative"
      description="Author announcements once approved by an admin"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Upload className="size-4" />
          {status?.approval_status === "pending" &&
            "Your CR access request is pending admin review."}
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

function useIstNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function istParts(d: Date) {
  const time = d.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
  const date = d.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Asia/Kolkata",
  });
  const hour = Number(
    d.toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }),
  );
  return {
    time,
    date,
    greeting: hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening",
  };
}

function Dashboard() {
  const { data: profile } = useProfile();
  const clock = useIstNow();
  const parts = clock ? istParts(clock) : null;
  const firstName = (profile?.display_name || profile?.full_name || "").split(/\s+/)[0] ?? "";
  const calendar = useCalendar();
  const myCourses = useMyCourses();
  const upcoming = (calendar.data ?? []).filter((e) => daysFromToday(e.event_date) >= 0);
  const examWindows = upcoming
    .filter((e) => e.event_type === "exam" || e.event_type === "result")
    .slice(0, 3);
  const comingUp = upcoming.filter((e) => e.event_type !== "exam").slice(0, 4);
  const teachers = [
    ...new Map(
      (myCourses.data ?? []).flatMap((c) => c.faculty.map((f) => [f, c] as const)),
    ).entries(),
  ].slice(0, 5);
  const dayQuery = useQuery({
    queryKey: ["timetable", "day"],
    queryFn: () => apiGet<TimetableResponse>("/timetable/day"),
  });
  const now = new Date();
  const dayEntries = todaysEntries(dayQuery.data?.entries ?? [], now);
  const withStatus = dayEntries.map((e) => ({ entry: e, status: deriveStatus(e, now) }));
  const live = withStatus.find((x) => x.status === "live")?.entry;
  const next = withStatus.find((x) => x.status === "upcoming")?.entry;

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
              {profile?.semester ? (
                <PixelBadge
                  tone="muted"
                  className="bg-primary-foreground/15 text-primary-foreground"
                >
                  Semester {profile.semester} · Section {profile.section}
                </PixelBadge>
              ) : null}
              <h1 className="mt-3 text-2xl font-bold tracking-tight text-primary-foreground sm:text-3xl">
                {parts ? parts.greeting : "Welcome"}
                {firstName ? `, ${firstName}` : ""}
              </h1>
              <p className="mt-1.5 max-w-md text-sm text-primary-foreground/85">
                {live
                  ? `${entryLabel(live)} is live${live.room ? ` in ${live.room}` : ""}.`
                  : "No class running right now."}{" "}
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
            {parts ? (
              <div
                className="hidden shrink-0 text-right sm:block"
                aria-label="Current time in Kottayam"
              >
                <p className="font-mono text-3xl font-bold text-primary-foreground">{parts.time}</p>
                <p className="text-xs text-primary-foreground/80">{parts.date} · Kottayam</p>
              </div>
            ) : null}
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
                  <li
                    key={c.id}
                    className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50 sm:px-5"
                  >
                    <div className="w-14 shrink-0 font-mono text-xs text-muted-foreground">
                      <p className="font-semibold text-foreground">{formatTime(c.start_time)}</p>
                      <p>{formatTime(c.end_time)}</p>
                    </div>
                    <span
                      className="h-10 w-1 shrink-0 pixelated"
                      style={{
                        background:
                          status === "live"
                            ? "var(--accent)"
                            : status === "done"
                              ? "var(--border)"
                              : "var(--primary)",
                      }}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold">
                        {entryLabel(c)}{" "}
                        {c.course_name && (
                          <span className="font-mono text-xs text-muted-foreground">
                            {c.course_name}
                          </span>
                        )}
                      </p>
                      {(c.faculty_names ?? []).length || c.room ? (
                        <p className="truncate text-xs text-muted-foreground">
                          {[(c.faculty_names ?? []).join(", "), c.room].filter(Boolean).join(" · ")}
                        </p>
                      ) : null}
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
          <SectionCard
            title="Coming up"
            description="From the academic calendar"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link to="/calendar">Calendar</Link>
              </Button>
            }
          >
            {calendar.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : comingUp.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nothing else on the calendar this semester.
              </p>
            ) : (
              <ul className="space-y-3">
                {comingUp.map((e) => (
                  <li key={e.id} className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{e.event_name}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {formatDate(e.event_date, { weekday: true })}
                      </p>
                    </div>
                    <PixelBadge tone={e.event_type === "deadline" ? "warning" : "primary"}>
                      {relativeDays(e.event_date)}
                    </PixelBadge>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title="Exams" description="Exam windows this semester">
            {calendar.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : examWindows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No upcoming exams on the calendar.</p>
            ) : (
              <ul className="space-y-3">
                {examWindows.map((e) => (
                  <li
                    key={e.id}
                    className="flex items-center gap-3 rounded-lg border border-border p-2.5"
                  >
                    <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary/60 text-center font-mono text-[10px] leading-tight font-bold whitespace-pre-line">
                      {formatDate(e.event_date).replace(" ", "\n")}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{e.event_name}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {relativeDays(e.event_date)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild variant="outline" size="sm" className="mt-4 w-full">
              <Link to="/exams">All exam dates</Link>
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
                    <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">
                      {m.items.join(" · ")}
                    </p>
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
                  <li
                    key={a.id}
                    className="flex gap-3 rounded-lg border border-border p-3 hover-lift"
                  >
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

          <SectionCard title="Your teachers" description="From your courses this semester">
            {myCourses.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : teachers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No teachers found in your timetable.</p>
            ) : (
              <ul className="space-y-2.5">
                {teachers.map(([name, course]) => (
                  <li key={name} className="flex items-center gap-2.5">
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-secondary/60 text-[11px] font-bold">
                      {name.replace(/^(Dr|Prof|Mr|Ms|Mrs)\.?\s*/i, "").charAt(0)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">{name}</p>
                      <p className="truncate font-mono text-[10px] text-muted-foreground">
                        {course.course_code} · {titleCase(course.course_name)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <Button asChild variant="outline" size="sm" className="mt-4 w-full">
              <Link to="/faculty">
                <Users className="size-4" /> Faculty directory
              </Link>
            </Button>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
