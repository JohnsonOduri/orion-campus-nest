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
import { parseRoll, rollContradictsEmail, rollFromEmail } from "@/lib/roll";

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
const schema = z
  .object({
    full_name: z.string().min(2, "Enter your full name"),
    roll_number: z
      .string()
      .trim()
      .transform((v) => v.toUpperCase())
      .pipe(z.string().regex(/^[A-Z0-9]{6,15}$/, "6–15 letters and digits, e.g. 2024BCS0066")),
    programme: z.string().min(1, "Required"),
    semester: z.coerce.number({ invalid_type_error: "Required" }).int().min(1, "Required").max(8),
    department: z.string(),
    section: z.string(),
    admission_year: z.coerce
      .number({ invalid_type_error: "Required" })
      .int()
      .min(2015, "Invalid year")
      .max(CURRENT_YEAR, "Can't be in the future"),
  })
  // Department and section are only *asked for* when the roll number can't
  // supply them. Requiring them unconditionally made the form impossible to
  // submit once the roll number was recognised: their inputs aren't rendered
  // in that case, so the cascade handlers below could blank them and the
  // "Required" error had nowhere to show — the button just did nothing.
  .superRefine((v, ctx) => {
    if (parseRoll(v.roll_number)) return;
    if (!v.department)
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["department"], message: "Required" });
    if (!v.section)
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["section"], message: "Required" });
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

  // "2024BCS0086" already says which branch and batch a student is in, so the
  // roll number fills those in rather than asking them to find themselves in a
  // dropdown. complete_registration re-derives the same values server-side and
  // ignores what we post, so this is purely so they can see it before saving.
  const derived = useMemo(() => parseRoll(roll), [roll]);
  // A one-letter slip in the branch code (BCS -> BCD) silently registers a
  // student into another department's timetable, and their institute address
  // already carries the same roll number — so cross-check the two. A warning,
  // not a block: not every address follows the pattern, and the Academic
  // Office is the authority on a genuine mismatch, not this form.
  const emailRoll = useMemo(() => rollFromEmail(profile?.email), [profile?.email]);
  const mismatch = useMemo(
    () => (rollContradictsEmail(roll, profile?.email) ? emailRoll : null),
    [roll, profile?.email, emailRoll],
  );

  useEffect(() => {
    if (!derived) return;
    if (derived.admissionYear <= CURRENT_YEAR && derived.admissionYear >= 2015) {
      form.setValue("admission_year", derived.admissionYear as any);
    }
    form.setValue("department", derived.department);
    form.setValue("section", derived.section);
  }, [derived, form]);

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
    // complete_registration re-derives these server-side and ignores what we
    // send when the roll number parses; sending the derived values anyway
    // keeps the request honest about what the student was shown.
    const fromRoll = parseRoll(values.roll_number);
    const department = fromRoll?.department ?? values.department;
    const section = fromRoll?.section ?? values.section;
    try {
      await apiPost<RegisterResponse>("/auth/register", {
        full_name: values.full_name,
        roll_number: values.roll_number,
        semester: values.semester,
        department,
        batch: section,
        section,
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
              {mismatch && (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs">
                  <p className="font-medium text-amber-700 dark:text-amber-400">
                    This doesn't match your email
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    {profile?.email} suggests{" "}
                    <span className="font-mono">
                      {mismatch.admissionYear}
                      {mismatch.branchCode}
                      {String(mismatch.serial).padStart(4, "0")}
                    </span>{" "}
                    ({mismatch.shortDepartment}, batch {mismatch.batchNo}). Double-check the roll
                    number — you can still continue if it's genuinely different.
                  </p>
                </div>
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
                        // Only reset the dependent dropdowns when they're the
                        // ones in use — when the roll number supplied the
                        // class, clearing it here left the form unsubmittable.
                        if (!derived) {
                          form.setValue("department", "");
                          form.setValue("section", "");
                        }
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
                      if (!derived) {
                        form.setValue("department", "");
                        form.setValue("section", "");
                      }
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

            {derived ? (
              <div className="space-y-1.5">
                <Label>Department and batch</Label>
                <div className="rounded-lg border border-border bg-muted/40 p-3">
                  <dl className="space-y-1.5 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-muted-foreground">Department</dt>
                      <dd className="text-right font-medium">{derived.shortDepartment}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-muted-foreground">Batch</dt>
                      <dd className="text-right font-medium">
                        Batch {derived.batchNo} · Section {derived.section}
                      </dd>
                    </div>
                  </dl>
                  <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                    from {derived.branchCode} · roll no. {derived.serial}
                  </p>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Taken from your roll number. If this looks wrong, check the roll number above —
                  contact the Academic Office if it still doesn't match.
                </p>
              </div>
            ) : (
              <>
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
              </>
            )}

            {/* A validation error on a field that isn't currently rendered
                would otherwise make the button look broken — say so instead. */}
            {form.formState.isSubmitted && !form.formState.isValid && (
              <p className="text-xs text-destructive">
                Some details are still missing or invalid — check the fields above.
              </p>
            )}

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
