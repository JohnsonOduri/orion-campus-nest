import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Browser-side Supabase client for the real login flow (Google OAuth only —
 * see src/routes/login.tsx). Session is stored in cookies (not
 * localStorage) via @supabase/ssr so the same session is visible to server
 * functions/API routes through the request's Cookie header
 * (src/lib/supabase-server.ts's getSupabaseSessionClient), without manually
 * forwarding a bearer token from the client.
 *
 * Only the public anon key is used here — safe for the browser bundle by
 * design; RLS is what actually protects data (CLAUDE.md §13).
 */
let cached: SupabaseClient | null = null;

export function getSupabaseBrowserClient(): SupabaseClient | null {
  if (cached) return cached;
  const url = import.meta.env["VITE_SUPABASE_URL"] as string | undefined;
  const anonKey = import.meta.env["VITE_SUPABASE_ANON_KEY"] as string | undefined;
  if (!url || !anonKey) return null;
  cached = createBrowserClient(url, anonKey);
  return cached;
}
