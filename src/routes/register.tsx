import { useEffect, useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Hash, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PixelClouds, PixelParticles, PixelSkyline, PixelMascot } from "@/components/pixel/pixel-art";
import { apiGet, apiPost, ApiError } from "@/lib/api-client";
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
const CURRENT_YEAR = new Date().getFullYear();

// Batch and section are the same thing on this campus ("Section III") — one field.
const schema = z.object({
  full_name: z.string().min(2, "Enter your full name"),
  roll_number: z
    .string()
    .trim()
    .transform((v) => v.toUpperCase())
    .pipe(z.string().regex(/^[A-Z0-9]{6,15}$/, "6–15 letters and digits, e.g. 2024BCS0066")),
  programme: z.string().min(1, "Required"),
  semester: z.coerce.number({ invalid_type_error: "Required" }).int().min(1, "Required").max(8),
  department: z.string().min(1, "Required"),
  section: z.string().min(1, "Required"),
  admission_year: z.coerce
    .number({ invalid_type_error: "Required" })
    .int()
    .min(2015, "Invalid year")
    .max(CURRENT_YEAR, "Can't be in the future"),
});

type ClassOption = { programme: string; semester: number; department: string; section: string };
type Options = { classes: ClassOption[]; admission_years: number[] };

function titleCaseDept(d: string) {
  return d
    .toLowerCase()
    .replace(/\b(\w)/g, (m) => m.toUpperCase())
    .replace(/\bAi\b/g, "AI")
    .replace(/\bCse\b/g, "CSE")
    .replace(/ And /g, " and ")
    .replace(/ In /g, " in ")
    .replace(/ With /g, " with ");
}

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
      roll_number: "",
      semester: "" as any,
      department: "",
      section: "",
      admission_year: "" as any,
      programme: "B.Tech",
    },
  });

  const options = useQuery({
    queryKey: ["register", "options"],
    queryFn: () => apiGet<Options>("/auth/register/options"),
    enabled: Boolean(profile && !profile.onboarded),
    staleTime: 10 * 60 * 1000,
  });
  const programme = form.watch("programme");
  const semester = form.watch("semester");
  const department = form.watch("department");
  const roll = form.watch("roll_number");
  const classes = options.data?.classes ?? [];
  const programmes = useMemo(() => [...new Set(classes.map((c) => c.programme))].sort(), [classes]);
  const semesters = useMemo(
    () => [...new Set(classes.filter((c) => c.programme === programme).map((c) => c.semester))].sort((a, b) => a - b),
    [classes, programme],
  );
  const departments = useMemo(
    () =>
      [...new Set(classes.filter((c) => c.programme === programme && c.semester === Number(semester)).map((c) => c.department))].sort(),
    [classes, programme, semester],
  );
  const sections = useMemo(
    () =>
      classes
        .filter((c) => c.programme === programme && c.semester === Number(semester) && c.department === department)
        .map((c) => c.section),
    [classes, programme, semester, department],
  );
  const years = options.data?.admission_years ?? Array.from({ length: 8 }, (_, i) => CURRENT_YEAR - i);

  // "2024BCS0066": suggest the admission year from the roll number's prefix.
  useEffect(() => {
    const m = /^(20\d\d)/.exec((roll || "").trim());
    if (m && !form.getValues("admission_year")) {
      const y = Number(m[1]);
      if (y <= CURRENT_YEAR && y >= 2015) form.setValue("admission_year", y as any);
    }
  }, [roll, form]);

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
        roll_number: values.roll_number,
        semester: values.semester,
        department: values.department,
        batch: values.section,
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

            <div className="space-y-1.5">
              <Label htmlFor="roll_number">Roll number</Label>
              <div className="relative">
                <Hash className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="roll_number"
                  className="pl-9 font-mono uppercase"
                  placeholder="e.g. 2024BCS0066"
                  autoComplete="off"
                  {...form.register("roll_number")}
                />
              </div>
              {form.formState.errors.roll_number && (
                <p className="text-xs text-destructive">{form.formState.errors.roll_number.message}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="programme">Programme</Label>
                <Controller
                  control={form.control}
                  name="programme"
                  render={({ field }) => (
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        form.setValue("semester", "" as any);
                        form.setValue("department", "");
                        form.setValue("section", "");
                      }}
                    >
                      <SelectTrigger id="programme">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        {(programmes.length ? programmes : ["B.Tech"]).map((p) => (
                          <SelectItem key={p} value={p}>
                            {p}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="admission_year">Admission year</Label>
                <Controller
                  control={form.control}
                  name="admission_year"
                  render={({ field }) => (
                    <Select value={field.value ? String(field.value) : ""} onValueChange={(v) => field.onChange(Number(v))}>
                      <SelectTrigger id="admission_year">
                        <SelectValue placeholder="Select..." />
                      </SelectTrigger>
                      <SelectContent>
                        {years.map((y) => (
                          <SelectItem key={y} value={String(y)}>
                            {y}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
                {form.formState.errors.admission_year && (
                  <p className="text-xs text-destructive">{form.formState.errors.admission_year.message}</p>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="semester">Semester</Label>
              <Controller
                control={form.control}
                name="semester"
                render={({ field }) => (
                  <Select
                    value={field.value ? String(field.value) : ""}
                    onValueChange={(v) => {
                      field.onChange(Number(v));
                      form.setValue("department", "");
                      form.setValue("section", "");
                    }}
                  >
                    <SelectTrigger id="semester">
                      <SelectValue placeholder={options.isLoading ? "Loading…" : "Select..."} />
                    </SelectTrigger>
                    <SelectContent>
                      {semesters.map((s) => (
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
              <Label htmlFor="department">Department</Label>
              <Controller
                control={form.control}
                name="department"
                render={({ field }) => (
                  <Select
                    value={field.value}
                    disabled={!semester}
                    onValueChange={(v) => {
                      field.onChange(v);
                      form.setValue("section", "");
                    }}
                  >
                    <SelectTrigger id="department">
                      <SelectValue placeholder={semester ? "Select..." : "Pick a semester first"} />
                    </SelectTrigger>
                    <SelectContent>
                      {departments.map((d) => (
                        <SelectItem key={d} value={d}>
                          {titleCaseDept(d)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {form.formState.errors.department && (
                <p className="text-xs text-destructive">{form.formState.errors.department.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="section">Batch / section</Label>
              <Controller
                control={form.control}
                name="section"
                render={({ field }) => (
                  <Select value={field.value} disabled={!department} onValueChange={field.onChange}>
                    <SelectTrigger id="section">
                      <SelectValue placeholder={department ? "Select..." : "Pick a department first"} />
                    </SelectTrigger>
                    <SelectContent>
                      {sections.map((s) => (
                        <SelectItem key={s} value={s}>
                          Section {s}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {form.formState.errors.section && (
                <p className="text-xs text-destructive">{form.formState.errors.section.message}</p>
              )}
              <p className="text-[11px] text-muted-foreground">
                Only classes with a published timetable are listed, so ORION can show yours.
              </p>
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
