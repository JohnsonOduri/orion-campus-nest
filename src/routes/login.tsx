import { useEffect, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Mail, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  PixelClouds,
  PixelParticles,
  PixelSkyline,
  PixelMascot,
  PixelDivider,
} from "@/components/pixel/pixel-art";
import { apiPost, apiBaseUrl, ApiError } from "@/lib/api-client";
import { useQueryClient } from "@tanstack/react-query";
import { profileQueryOptions } from "@/hooks/use-profile";
import { RedirectOverlay } from "@/components/shared/redirect-overlay";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in to ORION — IIIT Kottayam" },
      { name: "description", content: "Sign in to ORION with your IIIT Kottayam email, student ID or Google account." },
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

const schema = z.object({
  email: z.string().email("Enter a valid campus email"),
  password: z.string().min(6, "At least 6 characters"),
  remember: z.boolean().optional(),
});

type LoginResponse = { ok: true; redirect_to: string };

function LoginPage() {
  const { error } = Route.useSearch();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (error) {
      toast.error(decodeURIComponent(error));
      // Remove it from the URL so it doesn't stay stuck there
      navigate({ to: "/login", replace: true });
    }
  }, [error, navigate]);

  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", remember: true },
  });

  async function onSubmit(values: z.infer<typeof schema>) {
    try {
      const result = await apiPost<LoginResponse>("/auth/login", {
        email: values.email,
        password: values.password,
      });
      await queryClient.invalidateQueries({ queryKey: profileQueryOptions.queryKey });
      toast.success("Welcome back to ORION");
      setRedirecting(true);
      await navigate({ to: result.redirect_to });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Sign in failed. Try again.";
      toast.error(message);
    }
  }

  function onGoogleSignIn() {
    window.location.href = `${apiBaseUrl()}/auth/oauth/google/authorize`;
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      {redirecting && <RedirectOverlay label="Taking you to your workspace…" />}
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
          <p className="mt-1 text-sm text-muted-foreground">Use your campus credentials to continue.</p>

          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Campus email</Label>
              <div className="relative">
                <Mail className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input id="email" className="pl-9" {...form.register("email")} />
              </div>
              {form.formState.errors.email && (
                <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Lock className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input id="password" type="password" className="pl-9" {...form.register("password")} />
              </div>
              {form.formState.errors.password && (
                <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
              )}
            </div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <Checkbox defaultChecked /> Remember me
              </label>
            </div>
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Signing in…" : "Continue"}
            </Button>
          </form>

          <div className="my-5 flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="font-mono text-[10px] tracking-widest text-muted-foreground uppercase">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <Button variant="outline" className="w-full" onClick={onGoogleSignIn}>
            Continue with Google
          </Button>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            New here?{" "}
            <Link to="/register" className="font-medium text-primary hover:underline">
              Create an account
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
