import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useOrion } from "@/store/orion";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — ORION Campus Companion" },
      { name: "description", content: "Theme, notifications, privacy, accessibility, security and AI preferences for ORION." },
      { property: "og:title", content: "Settings — ORION" },
      { property: "og:description", content: "Personalise appearance, notifications and AI behaviour." },
    ],
  }),
  component: SettingsPage,
});

const groups: { title: string; items: { label: string; hint: string; on: boolean }[] }[] = [
  {
    title: "Notifications",
    items: [
      { label: "Class reminders", hint: "10 minutes before each session", on: true },
      { label: "Assignment deadlines", hint: "Daily digest at 8 PM", on: true },
      { label: "Announcements", hint: "High priority only", on: false },
    ],
  },
  {
    title: "Privacy & security",
    items: [
      { label: "Show availability to faculty", hint: "Share your class status", on: true },
      { label: "Two-factor authentication", hint: "OTP on new devices", on: false },
    ],
  },
  {
    title: "AI preferences",
    items: [
      { label: "Personalised answers", hint: "Use my timetable and attendance", on: true },
      { label: "Voice replies", hint: "Read answers aloud", on: false },
    ],
  },
  {
    title: "Accessibility",
    items: [
      { label: "Reduce motion", hint: "Minimise pixel animations", on: false },
      { label: "Large text", hint: "Increase base font size", on: false },
    ],
  },
];

function SettingsPage() {
  const { theme, setTheme } = useOrion();

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader badge="Preferences" title="Settings" subtitle="Tune ORION to how you work." />

        <SectionCard title="Appearance">
          <div className="flex items-center justify-between gap-4">
            <div>
              <Label className="text-sm">Dark mode</Label>
              <p className="text-xs text-muted-foreground">Switch between the campus day and night themes.</p>
            </div>
            <Switch checked={theme === "dark"} onCheckedChange={(v) => setTheme(v ? "dark" : "light")} />
          </div>
        </SectionCard>

        {groups.map((g) => (
          <SectionCard key={g.title} title={g.title}>
            <ul className="space-y-4">
              {g.items.map((i) => (
                <li key={i.label} className="flex items-center justify-between gap-4">
                  <div>
                    <Label className="text-sm">{i.label}</Label>
                    <p className="text-xs text-muted-foreground">{i.hint}</p>
                  </div>
                  <Switch defaultChecked={i.on} />
                </li>
              ))}
            </ul>
          </SectionCard>
        ))}
      </div>
    </AppShell>
  );
}
