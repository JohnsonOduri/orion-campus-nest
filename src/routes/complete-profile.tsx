import { useEffect } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PixelParticles, PixelMascot } from "@/components/pixel/pixel-art";
import { useAuth } from "@/hooks/use-auth";
import { completeOnboarding } from "@/lib/onboarding-api";

export const Route = createFileRoute("/complete-profile")({
  head: () => ({
    meta: [{ title: "Complete your profile — ORION" }],
  }),
  component: CompleteProfilePage,
});

const DEPARTMENTS = [
  "COMPUTER SCIENCE AND ENGINEERING",
  "ELECTRONICS AND COMMUNICATION ENGINEERING",
  "AI AND DATA SCIENCE",
  "CYBER SECURITY",
  "MATHEMATICS AND COMPUTING",
] as const;

const BATCHES = ["I", "II", "III", "IV", "V"] as const;
const CURRENT_ADMISSION_YEAR = new Date().getFullYear();
const ADMISSION_YEARS = Array.from({ length: 6 }, (_, i) => CURRENT_ADMISSION_YEAR - i);

const schema = z.object({
  fullName: z.string().min(2, "Enter your full name"),
  admissionYear: z.coerce.number().int(),
  department: z.enum(DEPARTMENTS, { message: "Select your programme/branch" }),
  semester: z.coerce.number().int().min(1).max(8),
  batch: z.enum(BATCHES, { message: "Select your batch" }),
});

type FormValues = z.infer<typeof schema>;

function CompleteProfilePage() {
  const navigate = useNavigate();
  const { context, loading, refresh } = useAuth();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      fullName: "",
      admissionYear: CURRENT_ADMISSION_YEAR,
      semester: 1,
    },
  });

  useEffect(() => {
    if (!loading && !context?.authenticated) {
      navigate({ to: "/login", search: { error: undefined } });
    }
    if (context?.fullName) {
      form.setValue("fullName", context.fullName);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, context]);

  async function onSubmit(values: FormValues) {
    try {
      await completeOnboarding({
        data: {
          fullName: values.fullName,
          admissionYear: values.admissionYear,
          programme: "B.Tech",
          department: values.department,
          semester: values.semester,
          batch: values.batch,
        },
      });
      await refresh();
      toast.success("Profile saved — welcome to ORION!");
      navigate({ to: context?.role === "CR" ? "/cr" : "/dashboard" });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save your profile.");
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-5 py-12">
      <PixelParticles count={16} />
      <div className="surface-card pixel-corners relative z-10 w-full max-w-lg p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <PixelMascot size={3} />
          <div>
            <p className="font-pixel text-[10px] text-primary">ORION</p>
            <h1 className="text-xl font-bold tracking-tight">Complete your profile</h1>
          </div>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          A few academic details so ORION can answer questions about your timetable, courses and faculty correctly.
        </p>

        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="fullName">Full name</Label>
            <Input id="fullName" {...form.register("fullName")} />
            {form.formState.errors.fullName && (
              <p className="text-xs text-destructive">{form.formState.errors.fullName.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Admission year</Label>
              <Controller
                control={form.control}
                name="admissionYear"
                render={({ field }) => (
                  <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Year" />
                    </SelectTrigger>
                    <SelectContent>
                      {ADMISSION_YEARS.map((y) => (
                        <SelectItem key={y} value={String(y)}>
                          {y}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="space-y-1.5">
              <Label>Semester</Label>
              <Controller
                control={form.control}
                name="semester"
                render={({ field }) => (
                  <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Semester" />
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
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Programme / branch</Label>
            <Controller
              control={form.control}
              name="department"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select your branch" />
                  </SelectTrigger>
                  <SelectContent>
                    {DEPARTMENTS.map((d) => (
                      <SelectItem key={d} value={d}>
                        B.Tech — {d.charAt(0) + d.slice(1).toLowerCase()}
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
            <Label>Batch</Label>
            <Controller
              control={form.control}
              name="batch"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select your batch" />
                  </SelectTrigger>
                  <SelectContent>
                    {BATCHES.map((b) => (
                      <SelectItem key={b} value={b}>
                        Batch {b}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {form.formState.errors.batch && (
              <p className="text-xs text-destructive">{form.formState.errors.batch.message}</p>
            )}
          </div>

          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Saving…" : "Save and continue"}
          </Button>
        </form>
      </div>
    </div>
  );
}
