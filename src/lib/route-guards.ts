import { redirect } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { profileQueryOptions, type Role } from "@/hooks/use-profile";

// The real access-control boundary is RLS/is_admin() in Postgres (D8) — this
// guard exists so a plain STUDENT never even sees /cr or /admin's shell
// render before being bounced, not because it's the thing actually keeping
// their data safe. Runs in `beforeLoad`, so it fires during SSR on a direct
// URL load too, not just client-side navigation.
export function requireRole(allowed: readonly Role[]) {
  return async ({ context }: { context: { queryClient: QueryClient } }) => {
    const profile = await context.queryClient.fetchQuery(profileQueryOptions);
    if (!profile) {
      throw redirect({ to: "/login" });
    }
    if (!allowed.includes(profile.role)) {
      throw redirect({ to: "/dashboard" });
    }
    return { profile };
  };
}
