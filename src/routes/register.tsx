import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PixelClouds, PixelParticles, PixelSkyline, PixelMascot } from "@/components/pixel/pixel-art";
import { apiPost, ApiError } from "@/lib/api-client";
import { profileQueryOptions, useProfile } from "@/hooks/use-profile";
import { RedirectOverlay } from "@/components/shared/redirect-overlay";

export const Route = createFileRoute("/register")({
  head: () => ({
    meta: [
      { title: "Complete your ORION profile — IIIT Kottayam" },
      { name: "description", content: "Finish setting up your ORION account with your academic details." },
    ],
  }),
  component: RegisterPage,
});

// Every visitor here has already signed in with Google (src/routes/login.tsx,
// src/routes/auth.callback.tsx) — this page only ever completes the academic
// profile for an already-authenticated, not-yet-onboarded account. There is
// no separate email/password signup path anymore.
const schema = z.object({
  full_name: z.string().min(2, "Enter your full name"),
  semester: z.coerce.number({ invalid_type_error: "Required" }).int().min(1, "Required").max(8),
  department: z.string().min(1, "Required"),
  batch: z.string().min(1, "Required"),
  section: z.string().min(1, "Required"),
  admission_year: z.coerce.number({ invalid_type_error: "Required" }).int().min(2015, "Invalid year").max(2035, "Invalid year"),
  programme: z.string().min(1, "Required"),
});

type FormValues = z.infer<typeof schema>;

type RegisterResponse = { success: true; cohort: string };

function RegisterPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: profile, isLoading } = useProfile();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    if (!profile) {
      // Never signed in — nothing to complete. Google sign-in creates the
      // account, so this page has no standalone entry point of its own.
      setRedirecting(true);
      navigate({ to: "/login", replace: true });
      return;
    }
    if (profile.onboarded) {
      setRedirecting(true);
      navigate({ to: "/dashboard", replace: true });
    }
  }, [isLoading, profile, navigate]);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      semester: "" as any,
      department: "",
      batch: "",
      section: "",
      admission_year: "" as any,
      programme: "",
    },
  });

  useEffect(() => {
    if (profile?.full_name && !form.getValues("full_name")) {
      form.setValue("full_name", profile.full_name);
    }
  }, [profile, form]);

  if (isLoading || !profile || profile.onboarded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  async function onSubmit(values: FormValues) {
    try {
      await apiPost<RegisterResponse>("/auth/register", {
        full_name: values.full_name,
        semester: values.semester,
        department: values.department,
        batch: values.batch,
        section: values.section,
        admission_year: values.admission_year,
        programme: values.programme,
      });

      await queryClient.invalidateQueries({ queryKey: profileQueryOptions.queryKey });
      toast.success("Welcome to ORION!");
      setRedirecting(true);
      await navigate({ to: "/dashboard" });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Registration failed. Try again.";
      toast.error(message);
    }
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      {redirecting && <RedirectOverlay label="Setting up your workspace…" />}
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
          <h2 className="text-3xl font-bold tracking-tight text-primary-foreground">Join the campus workspace.</h2>
          <p className="mt-3 text-sm text-primary-foreground/85">
            One account for timetables, mess menus, faculty hours, clubs and AI answers.
          </p>
        </div>
        <div className="relative z-10 opacity-90">
          <PixelSkyline />
        </div>
      </div>

      <div className="flex items-center justify-center px-5 py-12">
        <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
          <div className="flex items-center gap-3 lg:hidden">
            <PixelMascot size={4} />
            <span className="font-pixel text-xs text-primary">ORION</span>
          </div>
          <h1 className="mt-6 text-2xl font-bold tracking-tight">Complete your profile</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Fill in your academic details to continue to your dashboard.
          </p>

          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="full_name">Full name</Label>
              <div className="relative">
                <User className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input id="full_name" className="pl-9" {...form.register("full_name")} />
              </div>
              {form.formState.errors.full_name && (
                <p className="text-xs text-destructive">{form.formState.errors.full_name.message}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="programme">Programme</Label>
                <Controller
                  control={form.control}
                  name="programme"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id="programme">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="B.Tech">B.Tech</SelectItem>
                        <SelectItem value="M.Tech">M.Tech</SelectItem>
                        <SelectItem value="Ph.D">Ph.D</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
                {form.formState.errors.programme && (
                  <p className="text-xs text-destructive">{form.formState.errors.programme.message}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="department">Department</Label>
                <Input id="department" placeholder="e.g. CSE" {...form.register("department")} />
                {form.formState.errors.department && (
                  <p className="text-xs text-destructive">{form.formState.errors.department.message}</p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="semester">Semester</Label>
                <Controller
                  control={form.control}
                  name="semester"
                  render={({ field }) => (
                    <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                      <SelectTrigger id="semester">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        {Array.from({ length: 8 }, (_, i) => i + 1).map((s) => (
                          <SelectItem key={s} value={String(s)}>
                            Semester {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                {form.formState.errors.semester && (
                  <p className="text-xs text-destructive">{form.formState.errors.semester.message}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="admission_year">Admission Year</Label>
                <Input id="admission_year" type="number" placeholder="e.g. 2024" {...form.register("admission_year")} />
                {form.formState.errors.admission_year && (
                  <p className="text-xs text-destructive">{form.formState.errors.admission_year.message}</p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="batch">Batch</Label>
                <Input id="batch" placeholder="e.g. 2024" {...form.register("batch")} />
                {form.formState.errors.batch && (
                  <p className="text-xs text-destructive">{form.formState.errors.batch.message}</p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="section">Section</Label>
                <Input id="section" placeholder="e.g. C" {...form.register("section")} />
                {form.formState.errors.section && (
                  <p className="text-xs text-destructive">{form.formState.errors.section.message}</p>
                )}
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Saving…" : "Save and continue"}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            Wrong account?{" "}
            <button
              type="button"
              onClick={async () => {
                await apiPost("/auth/logout", {});
                queryClient.invalidateQueries({ queryKey: profileQueryOptions.queryKey });
                navigate({ to: "/login" });
              }}
              className="font-medium text-primary hover:underline"
            >
              Sign out
            </button>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
