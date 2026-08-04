import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  CalendarDays,
  CheckCircle2,
  Clock,
  CloudSun,
  GraduationCap,
  MapPin,
  Sparkles,
  TrendingUp,
  UtensilsCrossed,
  Users,
  Megaphone,
  FileText,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  PixelBadge,
  PixelDivider,
  PixelParticles,
  PixelSkyline,
  PixelSprite,
  SPRITES,
} from "@/components/pixel/pixel-art";
import {
  announcements,
  assignments,
  attendanceTrend,
  conversations,
  courses,
  exams,
  faculty,
  messMenu,
  student,
  todaysClasses,
  aiSuggestions,
} from "@/lib/mock-data";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

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

function Dashboard() {
  const live = todaysClasses.find((c) => c.status === "live");
  const next = todaysClasses.find((c) => c.status === "upcoming");

  return (
    <AppShell>
      <div className="space-y-5">
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
                {live ? `${live.title} is live in ${live.room}.` : "No class running right now."}{" "}
                {next ? `Next: ${next.title} at ${next.time}.` : ""}
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

        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Attendance" value={student.attendance} suffix="%" delta="+2.4%" icon={<CheckCircle2 className="size-4" />} />
          <StatCard label="CGPA" value={student.cgpa} icon={<GraduationCap className="size-4" />} tone="accent" />
          <StatCard label="Credits earned" value={student.credits.earned} suffix={`/${student.credits.total}`} icon={<TrendingUp className="size-4" />} tone="success" />
          <StatCard label="Open assignments" value={assignments.length} icon={<FileText className="size-4" />} tone="warning" />
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <SectionCard
            className="lg:col-span-2"
            title="Today's classes"
            description="Tuesday · 5 sessions"
            action={
              <Button asChild variant="ghost" size="sm">
                <Link to="/timetable">View week</Link>
              </Button>
            }
            contentClassName="p-0"
          >
            <ul className="divide-y divide-border">
              {todaysClasses.map((c) => (
                <li key={c.code} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50 sm:px-5">
                  <div className="w-14 shrink-0 font-mono text-xs text-muted-foreground">
                    <p className="font-semibold text-foreground">{c.time}</p>
                    <p>{c.end}</p>
                  </div>
                  <span
                    className="h-10 w-1 shrink-0 pixelated"
                    style={{
                      background:
                        c.status === "live" ? "var(--accent)" : c.status === "done" ? "var(--border)" : "var(--primary)",
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">
                      {c.title} <span className="font-mono text-xs text-muted-foreground">{c.code}</span>
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {c.faculty} · <MapPin className="inline size-3" /> {c.room}
                    </p>
                  </div>
                  {c.status === "live" ? (
                    <PixelBadge tone="success">Live</PixelBadge>
                  ) : c.status === "done" ? (
                    <PixelBadge tone="muted">Done</PixelBadge>
                  ) : (
                    <PixelBadge tone="primary">Soon</PixelBadge>
                  )}
                </li>
              ))}
            </ul>
          </SectionCard>

          <div className="space-y-5">
            <SectionCard title="AI suggestions" description="Personalised for today">
              <div className="space-y-2">
                {aiSuggestions.slice(0, 3).map((s) => (
                  <Link
                    key={s}
                    to="/ai"
                    className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-2.5 text-xs transition-colors hover:border-primary/60"
                  >
                    <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    <span>{s}</span>
                  </Link>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Attendance trend" description="Last 6 months">
              <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={attendanceTrend} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                    <defs>
                      <linearGradient id="att" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--color-chart-2)" stopOpacity={0.6} />
                        <stop offset="100%" stopColor="var(--color-chart-2)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={11} stroke="var(--color-muted-foreground)" />
                    <Tooltip
                      contentStyle={{
                        background: "var(--color-card)",
                        border: "1px solid var(--color-border)",
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Area type="monotone" dataKey="value" stroke="var(--color-chart-1)" strokeWidth={2} fill="url(#att)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          </div>
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

          <SectionCard title="Today at the mess" description="Ratings from 214 students">
            <ul className="space-y-2.5">
              {messMenu.map((m) => (
                <li key={m.meal} className="rounded-lg border border-border p-2.5">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{m.meal}</p>
                    <span className="font-mono text-[11px] text-muted-foreground">{m.time}</span>
                  </div>
                  <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{m.items.join(" · ")}</p>
                </li>
              ))}
            </ul>
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
            <ul className="space-y-3">
              {announcements.slice(0, 3).map((a) => (
                <li key={a.id} className="flex gap-3 rounded-lg border border-border p-3 hover-lift">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                    <Megaphone className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-semibold">{a.title}</p>
                      <Badge variant="secondary" className="text-[10px]">
                        {a.tag}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{a.body}</p>
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {a.author} · {a.time}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </SectionCard>

          <div className="space-y-5">
            <SectionCard title="Faculty availability" description="Right now">
              <ul className="space-y-2.5">
                {faculty.slice(0, 4).map((f) => (
                  <li key={f.name} className="flex items-center gap-2.5">
                    <span className="grid size-8 place-items-center rounded-lg bg-secondary/60 text-[11px] font-bold">
                      {f.name.split(" ").slice(-1)[0]?.[0]}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">{f.name}</p>
                      <p className="truncate font-mono text-[10px] text-muted-foreground">{f.cabin}</p>
                    </div>
                    <span
                      className="size-2 shrink-0 pixelated"
                      style={{ background: f.available ? "var(--success)" : "var(--muted-foreground)" }}
                    />
                  </li>
                ))}
              </ul>
              <Button asChild variant="outline" size="sm" className="mt-4 w-full">
                <Link to="/faculty">
                  <Users className="size-4" /> Directory
                </Link>
              </Button>
            </SectionCard>

            <SectionCard title="Recent conversations">
              <ul className="space-y-2">
                {conversations.slice(0, 4).map((c) => (
                  <li key={c.title} className="flex items-center gap-2 text-xs">
                    <Clock className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{c.title}</span>
                    <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">{c.time}</span>
                  </li>
                ))}
              </ul>
            </SectionCard>
          </div>
        </div>

        <SectionCard title="Academic progress" description={`${courses.length} active courses`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {courses.map((c) => (
              <div key={c.code} className="rounded-lg border border-border p-3 hover-lift">
                <div className="flex items-center justify-between">
                  <p className="font-mono text-xs font-bold text-primary">{c.code}</p>
                  <PixelSprite size={2} rows={[...SPRITES.star]} />
                </div>
                <p className="mt-1 truncate text-sm font-medium">{c.title}</p>
                <Progress value={c.progress} className="mt-2 h-1.5" />
                <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">
                  {c.progress}% complete · {c.attendance}% attendance
                </p>
              </div>
            ))}
          </div>
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link to="/courses">Open courses</Link>
          </Button>
        </SectionCard>
      </div>
    </AppShell>
  );
}
