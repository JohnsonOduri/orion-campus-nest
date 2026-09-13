import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

import { getSupabaseSessionClient } from "@/lib/supabase-server";

export type OnboardingInput = {
  fullName: string;
  admissionYear: number;
  programme: string;
  department: string;
  semester: number;
  batch: string;
};

/**
 * Saves the academic context ORION's chat/timetable RPCs read
 * (orion_student_context reads student_profiles — docs/query-router.md).
 * `batch` and `section` are the same value here: the ingested timetable
 * data always sets them equal (backend/timetable/normalizer.py:
 * `section=meta.batch`), so collecting one field from the student and
 * mirroring it into both columns matches how the data actually models it,
 * rather than asking for a distinction the source data doesn't have.
 */
export const completeOnboarding = createServerFn({ method: "POST" })
  .validator((input: unknown) => input as OnboardingInput)
  .handler(async ({ data }) => {
    const request = getRequest();
    const client = getSupabaseSessionClient(request);
    if (!client) throw new Error("Not signed in.");

    const {
      data: { user },
    } = await client.auth.getUser();
    if (!user) throw new Error("Not signed in.");

    const { error: spError } = await client.from("student_profiles").upsert({
      user_id: user.id,
      display_name: data.fullName,
      semester: data.semester,
      programme: data.programme,
      department: data.department,
      batch: data.batch,
      section: data.batch,
    });
    if (spError) throw new Error(spError.message);

    const { error: profileError } = await client
      .from("profiles")
      .update({ full_name: data.fullName, admission_year: data.admissionYear })
      .eq("id", user.id);
    if (profileError) throw new Error(profileError.message);

    return { ok: true };
  });
