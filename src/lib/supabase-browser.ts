import { createClient } from "@supabase/supabase-js";

// Browser-only Supabase client, used for exactly one thing: driving the
// Google OAuth redirect (src/routes/login.tsx) and completing the PKCE
// exchange on the way back (src/routes/auth.callback.tsx). Every other
// piece of session state (the actual signed-in session the rest of the app
// uses) lives in the httpOnly cookies backend/app/api/oauth.py's
// /auth/oauth/google/set-session sets — this client's own session is
// deliberately short-lived and gets explicitly signed out of once that
// handoff succeeds (see auth.callback.tsx).
//
// `persistSession: false` is NOT used here on purpose: supabase-js still
// needs *some* storage for the PKCE code verifier to survive the full-page
// redirect to accounts.google.com and back, and `persistSession: false`
// makes it fall back to a pure in-memory object that's wiped by that exact
// navigation (verified against node_modules/@supabase/auth-js/src/
// GoTrueClient.ts — `settings.storage` is only honored when
// `persistSession: true`). So instead: `persistSession: true` with an
// explicit `storage: sessionStorage` override — tab-scoped and cleared on
// tab close, unlike the library's own default of `localStorage` (which
// persists indefinitely and is shared across every tab). The tokens still
// sit in that storage for the (short) duration of the handshake — that's
// an inherent property of any frontend-driven OAuth flow, not something
// this config can fully eliminate — which is why auth.callback.tsx calls
// `supabase.auth.signOut({ scope: "local" })` immediately after relaying
// the tokens to the backend, to shrink the window down to just the
// handshake itself.
export const supabase = createClient(
  import.meta.env["VITE_SUPABASE_URL"],
  import.meta.env["VITE_SUPABASE_ANON_KEY"],
  {
    auth: {
      persistSession: true,
      storage: typeof window !== "undefined" ? window.sessionStorage : undefined,
      autoRefreshToken: false,
      detectSessionInUrl: true,
    },
  },
);
