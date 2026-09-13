import { useState } from "react";
import { createFileRoute, useSearch } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  PixelClouds,
  PixelParticles,
  PixelSkyline,
  PixelMascot,
  PixelDivider,
} from "@/components/pixel/pixel-art";
import { getSupabaseBrowserClient } from "@/lib/supabase-browser";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in to ORION — IIIT Kottayam" },
      { name: "description", content: "Sign in to ORION with your IIIT Kottayam institute Google account." },
      { property: "og:title", content: "Sign in to ORION" },
      { property: "og:description", content: "Access your IIIT Kottayam campus workspace." },
    ],
  }),
  validateSearch: (search: Record<string, unknown>) => ({
    error: typeof search["error"] === "string" ? search["error"] : undefined,
  }),
  component: LoginPage,
});

const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
    <path
      fill="#4285F4"
      d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.53 5.53 0 0 1-2.4 3.63v3h3.87c2.27-2.09 3.58-5.17 3.58-8.82z"
    />
    <path
      fill="#34A853"
      d="M12 24c3.24 0 5.96-1.07 7.94-2.91l-3.87-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.27v3.11A12 12 0 0 0 12 24z"
    />
    <path
      fill="#FBBC05"
      d="M5.27 14.28A7.2 7.2 0 0 1 4.89 12c0-.79.14-1.56.38-2.28V6.61H1.27A12 12 0 0 0 0 12c0 1.94.46 3.77 1.27 5.39l4-3.11z"
    />
    <path
      fill="#EA4335"
      d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.27 6.61l4 3.11C6.22 6.86 8.87 4.75 12 4.75z"
    />
  </svg>
);

function LoginPage() {
  const { error } = useSearch({ from: "/login" });
  const [pending, setPending] = useState(false);

  async function signInWithGoogle() {
    const client = getSupabaseBrowserClient();
    if (!client) {
      toast.error("Sign-in isn't configured in this environment.");
      return;
    }
    setPending(true);
    const { error: signInError } = await client.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (signInError) {
      toast.error(signInError.message);
      setPending(false);
    }
    // on success the browser navigates away to Google; nothing else to do here.
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
            Use your IIIT Kottayam institute Google account to continue.
          </p>

          {error ? (
            <div className="mt-5 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <p>{decodeURIComponent(error)}</p>
            </div>
          ) : null}

          <Button
            variant="outline"
            className="mt-6 h-11 w-full gap-2.5"
            onClick={signInWithGoogle}
            disabled={pending}
          >
            <GoogleIcon />
            {pending ? "Redirecting to Google…" : "Continue with Google"}
          </Button>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            Only @iiitkottayam.ac.in institute accounts can sign in.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
