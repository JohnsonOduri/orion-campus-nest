import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Progress } from "@/components/ui/progress";
import { PixelBadge, PixelSprite, SPRITES } from "@/components/pixel/pixel-art";
import { student, courses } from "@/lib/mock-data";

export const Route = createFileRoute("/profile")({
  head: () => ({
    meta: [
      { title: "Profile — ORION Campus Companion" },
      { name: "description", content: "Student profile with campus QR ID, attendance summary, achievements and documents." },
      { property: "og:title", content: "Profile — ORION" },
      { property: "og:description", content: "Your campus identity, attendance and achievements." },
    ],
  }),
  component: ProfilePage,
});

function QrPixel() {
  const cells = Array.from({ length: 121 }, (_, i) => (i * 7919) % 3 !== 0);
  return (
    <div className="grid w-fit grid-cols-11 gap-[2px] bg-card p-2">
      {cells.map((on, i) => (
        <span key={i} className="size-2 pixelated" style={{ background: on ? "var(--foreground)" : "transparent" }} />
      ))}
    </div>
  );
}

function ProfilePage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Student" title="Profile" subtitle={student.email} />

        <div className="grid gap-5 lg:grid-cols-3">
          <SectionCard className="lg:col-span-2" title="Student information">
            <div className="flex flex-wrap items-center gap-4">
              <span className="grid size-16 place-items-center rounded-2xl bg-primary text-xl font-bold text-primary-foreground">
                AM
              </span>
              <div>
                <p className="text-lg font-semibold">{student.name}</p>
                <p className="font-mono text-xs text-muted-foreground">{student.id}</p>
                <p className="text-xs text-muted-foreground">{student.branch} · {student.batch}</p>
              </div>
            </div>
            <dl className="mt-5 grid gap-3 sm:grid-cols-3">
              {[
                ["CGPA", student.cgpa],
                ["Attendance", `${student.attendance}%`],
                ["Credits", `${student.credits.earned}/${student.credits.total}`],
              ].map(([k, v]) => (
                <div key={String(k)} className="rounded-lg border border-border p-3">
                  <dt className="text-xs text-muted-foreground">{k}</dt>
                  <dd className="mt-1 font-mono text-lg font-bold">{v}</dd>
                </div>
              ))}
            </dl>
          </SectionCard>

          <SectionCard title="Campus QR ID" description="Scan at gates, library and mess">
            <div className="flex justify-center">
              <QrPixel />
            </div>
            <p className="mt-3 text-center font-mono text-[11px] text-muted-foreground">{student.id}</p>
          </SectionCard>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <SectionCard title="Achievements">
            <div className="flex flex-wrap gap-3">
              {["Perfect week", "Top 10 CGPA", "Hackathon winner", "Club lead"].map((a, i) => (
                <div key={a} className="flex items-center gap-2 rounded-lg border border-border p-2.5">
                  <PixelSprite size={3} rows={[...(i % 2 ? SPRITES.trophy : SPRITES.star)]} />
                  <span className="text-xs font-medium">{a}</span>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Attendance summary">
            <ul className="space-y-3">
              {courses.slice(0, 4).map((c) => (
                <li key={c.code}>
                  <div className="flex justify-between text-xs">
                    <span className="font-medium">{c.code} · {c.title}</span>
                    <span className="font-mono text-muted-foreground">{c.attendance}%</span>
                  </div>
                  <Progress value={c.attendance} className="mt-1.5 h-1.5" />
                </li>
              ))}
            </ul>
            <PixelBadge tone="success" className="mt-4">Eligible for exams</PixelBadge>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
