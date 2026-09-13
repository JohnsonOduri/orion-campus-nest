import { useQuery, useQueryClient } from "@tanstack/react-query";

import { getCurrentUserContext, type UserContext } from "@/lib/auth-api";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

const AUTH_QUERY_KEY = ["orion-auth-context"] as const;

/**
 * The real (server-verified) auth/role/profile state — see
 * src/lib/auth-api.ts. Every protected page reads from here, never from a
 * client-chosen value, per AGENTS.md §7/§17.
 */
export function useAuth() {
  const queryClient = useQueryClient();
  const query = useQuery<UserContext>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: () => getCurrentUserContext(),
    staleTime: 30_000,
    retry: false,
  });

  async function signOut() {
    const client = getSupabaseBrowserClient();
    await client?.auth.signOut();
    await queryClient.invalidateQueries({ queryKey: AUTH_QUERY_KEY });
    window.location.href = "/login";
  }

  function refresh() {
    return queryClient.invalidateQueries({ queryKey: AUTH_QUERY_KEY });
  }

  return {
    context: query.data ?? null,
    loading: query.isLoading,
    error: query.error,
    signOut,
    refresh,
  };
}
