import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { CardSkeleton, EmptyState, PageHeader, SectionCard } from "@/components/shared/primitives";
import { PixelBadge } from "@/components/pixel/pixel-art";
import { Button } from "@/components/ui/button";
import { useProfile } from "@/hooks/use-profile";
import { titleCase, useMyAcademic } from "@/lib/campus";

export const Route = createFileRoute("/profile")({
  head: () => ({
    meta: [
      { title: "Profile — ORION Campus" },
      { name: "description", content: "Your ORION account and academic details." },
      { property: "og:title", content: "Profile — ORION" },
      { property: "og:description", content: "Your account and academic details." },
    ],
  }),
  component: ProfilePage,
});

const ROLE_LABEL = {
  STUDENT: "Student",
  CR: "Class Representative",
  FACULTY: "Faculty",
  ADMIN: "Administrator",
} as const;

function initials(name: string | null | undefined, email: string): string {
  const src = (name || email.split("@")[0] || "?").replace(/[^A-Za-z ]/g, " ").trim();
  const parts = src.split(/\s+/).filter(Boolean);
  return (
    (parts[0]?.[0] ?? "?") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

function ProfilePage() {
  const { data: profile, isLoading } = useProfile();
  const academic = useMyAcademic();

  return (
    <AppShell>
      <div className="space-y-5">
        <PageHeader
          badge={profile ? ROLE_LABEL[profile.role] : "Account"}
          title="Profile"
          subtitle={profile?.email ?? ""}
        />
        {isLoading ? (
          <CardSkeleton rows={5} />
        ) : !profile ? (
          <SectionCard>
            <EmptyState
              title="You're signed out"
              message="Sign in with your institute Google account to see your profile."
            />
          </SectionCard>
        ) : (
          <div className="grid gap-5 lg:grid-cols-3">
            <SectionCard className="lg:col-span-2" title="Account">
              <div className="flex flex-wrap items-center gap-4 pb-3">
                <span className="grid size-16 place-items-center rounded-2xl bg-primary text-xl font-bold text-primary-foreground">
                  {initials(profile.display_name || profile.full_name, profile.email)}
                </span>
                <div className="min-w-0">
                  <p className="truncate text-lg font-semibold">
                    {profile.display_name || profile.full_name || profile.email}
                  </p>
                  <p className="truncate text-sm text-muted-foreground">{profile.email}</p>
                  <PixelBadge tone="primary" className="mt-1.5">
                    {ROLE_LABEL[profile.role]}
                  </PixelBadge>
                </div>
              </div>
              <dl className="divide-y divide-border border-t border-border">
                <Row label="Programme" value={profile.programme} />
                <Row label="Department" value={titleCase(profile.department)} />
                <Row label="Semester" value={profile.semester} />
                <Row label="Section" value={profile.section} />
              </dl>
              {!profile.onboarded ? (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-muted p-3 text-sm">
                  <p>Finish registration so ORION can show your timetable.</p>
                  <Button asChild size="sm">
                    <Link to="/register">Complete registration</Link>
                  </Button>
                </div>
              ) : null}
            </SectionCard>

            <SectionCard title="Academic details" description="Worked out from your registration.">
              {academic.isLoading ? (
                <CardSkeleton rows={2} />
              ) : (
                <dl className="divide-y divide-border">
                  <Row label="Regulations" value={academic.data?.regulations ?? "—"} />
                  <Row label="Section classroom" value={academic.data?.classroom?.room_no ?? "—"} />
                </dl>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Something wrong here? Your details come from registration — contact the Academic
                Office to correct them.
              </p>
            </SectionCard>
          </div>
        )}
      </div>
    </AppShell>
  );
}
