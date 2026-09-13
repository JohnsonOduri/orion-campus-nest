import { createFileRoute } from "@tanstack/react-router";

import { getSupabaseSessionClient, serializeCookieHeader } from "@/lib/supabase-server";

/**
 * Google OAuth callback (PKCE). Exchanges the ?code for a session, writes
 * the session cookies, decides the destination (complete-profile or the
 * user's portal by role) server-side, and redirects there in one hop.
 *
 * Domain restriction and role assignment already happened at the database
 * layer (the before-user-created auth hook + handle_new_user trigger) —
 * this route only needs to read the result, never re-implement the check.
 */
export const Route = createFileRoute("/auth/callback")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url);
        const code = url.searchParams.get("code");
        const oauthError = url.searchParams.get("error_description") || url.searchParams.get("error");

        const setCookies: string[] = [];
        const client = getSupabaseSessionClient(request, (cookies) => {
          for (const { name, value, options } of cookies) {
            setCookies.push(serializeCookieHeader(name, value, options));
          }
        });

        function redirect(path: string): Response {
          const res = new Response(null, {
            status: 302,
            headers: { Location: new URL(path, url.origin).toString() },
          });
          for (const cookie of setCookies) res.headers.append("set-cookie", cookie);
          return res;
        }

        if (oauthError) {
          return redirect(`/login?error=${encodeURIComponent(oauthError)}`);
        }
        if (!code || !client) {
          return redirect("/login?error=missing_code");
        }

        const { error: exchangeError } = await client.auth.exchangeCodeForSession(code);
        if (exchangeError) {
          // The domain-restriction hook rejects here with its own message
          // (AGENTS.md-style safe fallback: never guess, surface what happened).
          return redirect(`/login?error=${encodeURIComponent(exchangeError.message)}`);
        }

        const {
          data: { user },
        } = await client.auth.getUser();
        if (!user) {
          return redirect("/login?error=no_session");
        }

        const { data: profile } = await client.from("profiles").select("role").eq("id", user.id).maybeSingle();
        const role = profile?.role ?? "STUDENT";

        if (role === "ADMIN") {
          return redirect("/admin");
        }

        const { data: studentProfile } = await client
          .from("student_profiles")
          .select("semester,programme,department,batch,section")
          .eq("user_id", user.id)
          .maybeSingle();
        const complete = Boolean(
          studentProfile?.semester != null &&
            studentProfile?.programme &&
            studentProfile?.department &&
            studentProfile?.batch &&
            studentProfile?.section,
        );
        if (!complete) {
          return redirect("/complete-profile");
        }

        return redirect(role === "CR" ? "/cr" : "/dashboard");
      },
    },
  },
});
