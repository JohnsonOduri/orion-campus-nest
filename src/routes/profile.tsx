import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { student } from "@/lib/mock-data";

export const Route = createFileRoute("/profile")({
  head: () => ({
    meta: [
      { title: "Profile — ORION Campus Companion" },
      { name: "description", content: "Student profile and campus QR ID." },
      { property: "og:title", content: "Profile — ORION" },
      { property: "og:description", content: "Your campus identity." },
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
          </SectionCard>

          <SectionCard title="Campus QR ID" description="Scan at gates, library and mess">
            <div className="flex justify-center">
              <QrPixel />
            </div>
            <p className="mt-3 text-center font-mono text-[11px] text-muted-foreground">{student.id}</p>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
