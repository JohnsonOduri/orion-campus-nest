import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import { apiGet, ApiError } from "@/lib/api-client";

export type Role = "STUDENT" | "FACULTY" | "CR" | "ADMIN";

export type Profile = {
  id: string;
  full_name: string | null;
  email: string;
  role: Role;
  onboarded: boolean;
  pending_cr_request: boolean;
  department: string | null;
  semester: number | null;
  batch: string | null;
  section: string | null;
  display_name: string | null;
  programme: string | null;
  cohort: string | null;
};

// Shared between useProfile() and the route `beforeLoad` guards (see
// src/lib/route-guards.ts) so both draw on the same TanStack Query cache
// entry instead of issuing a duplicate /auth/me request on every navigation.
// retry: false lives here (not just on the useProfile() wrapper) because
// requireRole()'s SSR beforeLoad calls queryClient.fetchQuery(profileQueryOptions)
// directly — without it, a single failed /auth/me call (backend briefly
// unreachable, a real 401, anything) triggers TanStack Query's default 3
// retries with exponential backoff, stalling every /cr and /admin page load
// for several seconds before it even gets to redirect to /login.
export const profileQueryOptions = {
  queryKey: ["profile"] as const,
  queryFn: async (): Promise<Profile | null> => {
    try {
      return await apiGet<Profile>("/auth/me");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return null;
      throw err;
    }
  },
  staleTime: 60_000,
  retry: false,
} satisfies UseQueryOptions<Profile | null>;

// The real source of truth for "who is signed in and what can they do" —
// backed by GET /auth/me, which itself is backed by RLS/is_admin(), not a
// client-editable store. Returns null (not an error state) when signed out,
// so callers can branch on `profile === null` without special-casing 401s.
export function useProfile() {
  return useQuery(profileQueryOptions);
}
