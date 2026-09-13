import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createServerClient, serializeCookieHeader, type CookieOptions } from "@supabase/ssr";

function supabaseUrl(): string | null {
  const env = process.env;
  return env["SUPABASE_URL"] ?? env["VITE_SUPABASE_URL"] ?? env["PUBLIC_SUPABASE_URL"] ?? null;
}

function anonKey(): string | null {
  const env = process.env;
  return (
    env["SUPABASE_ANON_KEY"] ??
    env["SUPABASE_PUBLIC_ANON_KEY"] ??
    env["VITE_SUPABASE_ANON_KEY"] ??
    env["PUBLIC_SUPABASE_ANON_KEY"] ??
    null
  );
}

function parseCookieHeader(header: string | null): { name: string; value: string }[] {
  if (!header) return [];
  return header
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((pair) => {
      const idx = pair.indexOf("=");
      if (idx === -1) return { name: pair, value: "" };
      return { name: pair.slice(0, idx), value: decodeURIComponent(pair.slice(idx + 1)) };
    });
}

/**
 * Cookie-based session client (real browser login) — this is what makes
 * "sign in with Google" work across page loads and server functions without
 * manually forwarding a bearer header. The browser client
 * (src/lib/supabase-browser.ts) stores the session in cookies; this reads
 * them from the incoming request and, when `onSetCookies` is given (only the
 * OAuth callback route needs this — see src/routes/auth/callback.tsx),
 * forwards any refreshed session cookies back out. Still the anon key only,
 * still RLS-scoped to the resolved auth.uid() — never service-role.
 */
export function getSupabaseSessionClient(
  request: Request,
  onSetCookies?: (cookies: { name: string; value: string; options: CookieOptions }[]) => void,
): SupabaseClient | null {
  const url = supabaseUrl();
  const key = anonKey();
  if (!url || !key) return null;
  return createServerClient(url, key, {
    cookies: {
      getAll: () => parseCookieHeader(request.headers.get("cookie")),
      setAll: (cookiesToSet) => onSetCookies?.(cookiesToSet),
    },
  });
}

export { serializeCookieHeader };

/**
 * Server-side Supabase admin client (service role).
 *
 * Returns null when Supabase is not configured so the timetable API can
 * degrade to a clearly-flagged demo mode in local development. The secret
 * key NEVER reaches client bundles: this module is imported only from
 * server function handlers.
 *
 * NOTE: the admin client bypasses RLS. It must only be used for trusted
 * server-side work (ingestion, admin tooling) — never to serve user requests.
 */
let cached: SupabaseClient | null | undefined;

export function getSupabaseAdmin(): SupabaseClient | null {
  if (cached !== undefined) return cached;
  const env = process.env;
  const url = supabaseUrl();
  const key = env["SUPABASE_SECRET_KEY"] ?? env["SUPABASE_SERVICE_ROLE_KEY"];
  if (!url || !key) {
    cached = null;
    return cached;
  }
  cached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return cached;
}

/**
 * Build a request-scoped client whose identity is the CALLER's JWT.
 *
 * The bearer token is forwarded verbatim to Supabase, which verifies it and
 * exposes auth.uid() to the orion_* SQL functions (orion_resolve_user).
 * No client-supplied user id is ever trusted — identity comes only from the
 * verified JWT. Uses the public anon key, never the service-role key.
 */
export function getSupabaseForRequest(request: Request): SupabaseClient | null {
  const url = supabaseUrl();
  if (!url) return null;
  const env = process.env;
  const anonKey =
    env["SUPABASE_ANON_KEY"] ??
    env["SUPABASE_PUBLIC_ANON_KEY"] ??
    env["VITE_SUPABASE_ANON_KEY"] ??
    env["PUBLIC_SUPABASE_ANON_KEY"];
  const authorization = request.headers.get("authorization");
  if (!authorization?.toLowerCase().startsWith("bearer ")) return null;
  if (!anonKey) return null; // cannot safely forward without a public key
  return createClient(url, anonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { headers: { Authorization: authorization } },
  });
}
