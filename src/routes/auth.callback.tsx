import { useEffect, useRef } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { apiPost, ApiError } from "@/lib/api-client";
import { profileQueryOptions } from "@/hooks/use-profile";
import { RedirectOverlay } from "@/components/shared/redirect-overlay";
import { supabase } from "@/lib/supabase-browser";
import type { LoginResponse } from "@/routes/login";

export const Route = createFileRoute("/auth/callback")({
  component: AuthCallbackPage,
});

function AuthCallbackPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // StrictMode/effect re-runs must not fire this twice — a second run would
  // find no session left (or worse, race the first run's own sign-out).
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    (async () => {
      // supabase-js has already exchanged the ?code=... param in this URL
      // for a session by the time this resolves (detectSessionInUrl: true
      // in supabase-browser.ts).
      const { data, error: sessionError } = await supabase.auth.getSession();
      const session = data.session;

      if (sessionError || !session) {
        toast.error(sessionError?.message ?? "Google sign-in failed. Try again.");
        await navigate({ to: "/login", replace: true });
        return;
      }

      try {
        const result = await apiPost<LoginResponse>("/auth/oauth/google/set-session", {
          access_token: session.access_token,
          refresh_token: session.refresh_token,
        });

        // Tokens are now in the backend's httpOnly cookies (the source of
        // truth for every subsequent request) — wipe the sessionStorage
        // copy supabase-js made during the handshake rather than leaving it
        // there for the rest of the tab's lifetime.
        await supabase.auth.signOut({ scope: "local" });

        await queryClient.invalidateQueries({ queryKey: profileQueryOptions.queryKey });
        await navigate({ to: result.redirect_to, replace: true });
      } catch (err) {
        await supabase.auth.signOut({ scope: "local" });
        const message = err instanceof ApiError ? err.message : "Sign-in failed. Try again.";
        toast.error(message);
        await navigate({ to: "/login", replace: true });
      }
    })();
  }, [navigate, queryClient]);

  return <RedirectOverlay label="Signing you in with Google…" />;
}
