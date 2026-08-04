import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge, PixelDivider } from "@/components/pixel/pixel-art";
import { calendarEvents } from "@/lib/mock-data";

export const Route = createFileRoute("/calendar")({
  head: () => ({
    meta: [
      { title: "Academic Calendar — ORION Campus" },
      { name: "description", content: "Semester timeline for IIIT Kottayam: exams, holidays, deadlines and campus events." },
      { property: "og:title", content: "Academic Calendar — ORION" },
      { property: "og:description", content: "Semester timeline, exams, holidays and deadlines." },
    ],
  }),
  component: CalendarPage,
});

const tone = { exam: "danger", holiday: "success", deadline: "warning", event: "primary" } as const;

function CalendarPage() {
  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Even semester 2026" title="Academic Calendar" subtitle="Key dates for the running semester." />

        <div className="grid gap-5 lg:grid-cols-3">
          <SectionCard className="lg:col-span-2" title="Semester timeline">
            <ol className="relative space-y-5 border-l border-border pl-6">
              {calendarEvents.map((e) => (
                <li key={e.label} className="relative">
                  <span className="absolute top-1.5 -left-[27px] size-2.5 pixelated bg-primary" />
                  <p className="font-mono text-[11px] text-muted-foreground">{e.date}</p>
                  <p className="mt-0.5 text-sm font-medium">{e.label}</p>
                  <PixelBadge tone={tone[e.type as keyof typeof tone]} className="mt-1.5">
                    {e.type}
                  </PixelBadge>
                </li>
              ))}
            </ol>
          </SectionCard>

          <SectionCard title="At a glance">
            <dl className="space-y-3 text-sm">
              {[
                ["Semester start", "12 Jan 2026"],
                ["Mid-sem exams", "18–26 Aug 2026"],
                ["Last working day", "14 Nov 2026"],
                ["End-sem exams", "20 Nov 2026"],
                ["Result declaration", "18 Dec 2026"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-mono text-xs font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <PixelDivider className="my-4" />
            <p className="text-xs text-muted-foreground">
              Dates are synced from the Academic Section and verified by administrators.
            </p>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
