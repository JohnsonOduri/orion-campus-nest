import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";

import { useAuth } from "@/hooks/use-auth";
import type { AppRole } from "@/lib/auth-api";
import { PixelSprite, SPRITES } from "@/components/pixel/pixel-art";

function roleHome(role: AppRole | null): string {
  if (role === "ADMIN") return "/admin";
  if (role === "CR") return "/cr";
  return "/dashboard";
}

/**
 * Client-side navigation guard: redirects an unauthenticated visitor to
 * /login, an authenticated-but-incomplete-profile student/CR to
 * /complete-profile, and anyone whose role isn't in `allow` back to their
 * own portal. ADMIN always passes (CLAUDE.md-style trusted-account
 * exception, matching "admin should reach both admin and CR portals").
 *
 * This is a UX convenience, not the security boundary — every data access
 * behind these pages is independently protected by RLS + is_admin()/
 * orion_resolve_user() regardless of whether this redirect fires first
 * (AGENTS.md §7: never trust client-side role checks for authorization).
 */
export function AuthGate({
  allow,
  children,
}: {
  allow: AppRole[];
  children: React.ReactNode;
}) {
  const { context, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading) return;
    if (!context?.authenticated) {
      navigate({ to: "/login", search: { error: undefined } });
      return;
    }
    if (context.role !== "ADMIN" && (context.role === "STUDENT" || context.role === "CR") && !context.profileComplete) {
      navigate({ to: "/complete-profile" });
      return;
    }
    if (context.role !== "ADMIN" && !allow.includes(context.role as AppRole)) {
      navigate({ to: roleHome(context.role) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, context]);

  if (loading || !context?.authenticated) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <PixelSprite size={4} rows={[...SPRITES.mascot]} />
          <p className="text-sm text-muted-foreground">Loading ORION…</p>
        </div>
      </div>
    );
  }

  const allowed =
    context.role === "ADMIN" ||
    (allow.includes(context.role as AppRole) &&
      !((context.role === "STUDENT" || context.role === "CR") && !context.profileComplete));

  if (!allowed) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <p className="text-sm text-muted-foreground">Redirecting…</p>
      </div>
    );
  }

  return <>{children}</>;
}
