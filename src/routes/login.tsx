import { useEffect } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  PixelClouds,
  PixelParticles,
  PixelSkyline,
  PixelMascot,
  PixelDivider,
} from "@/components/pixel/pixel-art";
import { supabase } from "@/lib/supabase-browser";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in to ORION — IIIT Kottayam" },
      { name: "description", content: "Sign in to ORION with your IIIT Kottayam Google account." },
      { property: "og:title", content: "Sign in to ORION" },
      { property: "og:description", content: "Access your IIIT Kottayam campus workspace." },
    ],
  }),
  validateSearch: (search: Record<string, unknown>): { error?: string | undefined } => {
    return {
      error: search['error'] as string | undefined,
    };
  },
  component: LoginPage,
});

// Shared with src/routes/auth.callback.tsx, which is the only other caller
// of a backend auth endpoint that returns this shape.
export type LoginResponse = { ok: true; redirect_to: string };

function LoginPage() {
  const { error } = Route.useSearch();
  const navigate = useNavigate();

  useEffect(() => {
    if (error) {
      toast.error(decodeURIComponent(error));
      // Remove it from the URL so it doesn't stay stuck there
      navigate({ to: "/login", replace: true });
    }
  }, [error, navigate]);

  async function onGoogleSignIn() {
    // Frontend-driven: the browser talks to Supabase directly, so this
    // works even if the FastAPI backend isn't running yet — the backend is
    // only needed once for the /auth/callback handoff (see
    // src/routes/auth.callback.tsx), the same way it's needed for every
    // other feature (timetable, mess, etc.) once you're signed in.
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) toast.error(error.message);
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-10">
        <div className="absolute inset-0 gradient-campus opacity-95" />
        <PixelClouds />
        <PixelParticles count={20} />
        <div className="relative z-10">
          <p className="font-pixel text-sm text-primary-foreground">ORION</p>
          <p className="mt-2 font-mono text-[11px] tracking-widest text-primary-foreground/80 uppercase">
            IIIT Kottayam
          </p>
        </div>
        <div className="relative z-10 max-w-sm">
          <h2 className="text-3xl font-bold tracking-tight text-primary-foreground">
            Your intelligent campus assistant.
          </h2>
          <p className="mt-3 text-sm text-primary-foreground/85">
            Timetables, attendance, mess menus, faculty hours, clubs and AI answers — one calm workspace for the whole
            campus.
          </p>
          <PixelDivider className="mt-6 opacity-60" />
        </div>
        <div className="relative z-10 opacity-90">
          <PixelSkyline />
        </div>
      </div>

      <div className="flex items-center justify-center px-5 py-12">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-sm"
        >
          <div className="flex items-center gap-3 lg:hidden">
            <PixelMascot size={4} />
            <span className="font-pixel text-xs text-primary">ORION</span>
          </div>
          <h1 className="mt-6 text-2xl font-bold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Use your @iiitkottayam.ac.in Google account to continue.
          </p>

          <Button className="mt-6 w-full" onClick={onGoogleSignIn}>
            Continue with Google
          </Button>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            First time here? Signing in with Google creates your account automatically.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
