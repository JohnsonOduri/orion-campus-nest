import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader, SectionCard } from "@/components/shared/primitives";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useOrion } from "@/store/orion";
import { VoiceSettingsCard } from "@/components/ai/voice-settings-card";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings — ORION Campus Companion" },
      {
        name: "description",
        content: "Appearance and voice settings for ORION.",
      },
      { property: "og:title", content: "Settings — ORION" },
      {
        property: "og:description",
        content: "Appearance and ORION voice.",
      },
    ],
  }),
  component: SettingsPage,
});

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
              <p className="text-xs text-muted-foreground">
                Switch between the campus day and night themes.
              </p>
            </div>
            <Switch
              aria-label="Dark mode"
              checked={theme === "dark"}
              onCheckedChange={(v) => setTheme(v ? "dark" : "light")}
            />
          </div>
        </SectionCard>

        <VoiceSettingsCard />
      </div>
    </AppShell>
  );
}
