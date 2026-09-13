import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

import { getSupabaseSessionClient } from "@/lib/supabase-server";

export type AppRole = "STUDENT" | "FACULTY" | "CR" | "ADMIN";

export type UserContext = {
  authenticated: boolean;
  id: string | null;
  email: string | null;
  fullName: string | null;
  role: AppRole | null;
  /** true once student_profiles has the fields the chat/timetable context needs. */
  profileComplete: boolean;
  studentProfile: {
    displayName: string | null;
    semester: number | null;
    programme: string | null;
    department: string | null;
    batch: string | null;
    section: string | null;
  } | null;
  /** the requester's own pending/most-recent CR access request, if any. */
  crRequestStatus: "none" | "pending" | "approved" | "rejected";
};

const EMPTY_CONTEXT: UserContext = {
  authenticated: false,
  id: null,
  email: null,
  fullName: null,
  role: null,
  profileComplete: false,
  studentProfile: null,
  crRequestStatus: "none",
};

/**
 * The single source of truth for "who is logged in, what role, is their
 * academic profile complete" — used by the client-side route guard
 * (src/components/auth/auth-gate.tsx) and the complete-profile form. Reads
 * the session from cookies (never trusts anything the client claims about
 * itself); role/profile data comes from RLS-scoped queries as the resolved
 * user, so it can never see another user's data even if this function were
 * called with a forged argument (there are none — everything comes from the
 * verified session).
 */
export const getCurrentUserContext = createServerFn({ method: "GET" }).handler(
  async (): Promise<UserContext> => {
    const request = getRequest();
    const client = getSupabaseSessionClient(request);
    if (!client) return EMPTY_CONTEXT;

    const {
      data: { user },
    } = await client.auth.getUser();
    if (!user) return EMPTY_CONTEXT;

    const { data: profile } = await client
      .from("profiles")
      .select("full_name,email,role")
      .eq("id", user.id)
      .maybeSingle();

    const role = (profile?.role as AppRole | undefined) ?? "STUDENT";

    const { data: studentProfile } = await client
      .from("student_profiles")
      .select("display_name,semester,programme,department,batch,section")
      .eq("user_id", user.id)
      .maybeSingle();

    const profileComplete = Boolean(
      studentProfile &&
        studentProfile.semester != null &&
        studentProfile.programme &&
        studentProfile.department &&
        studentProfile.batch &&
        studentProfile.section,
    );

    const { data: crRequests } = await client
      .from("approval_requests")
      .select("approval_status")
      .eq("submitted_by", user.id)
      .eq("submission_type", "cr_access_request")
      .order("created_at", { ascending: false })
      .limit(1);

    const crRequestStatus = (crRequests?.[0]?.approval_status as UserContext["crRequestStatus"]) ?? "none";

    return {
      authenticated: true,
      id: user.id,
      email: profile?.email ?? user.email ?? null,
      fullName: profile?.full_name ?? (user.user_metadata?.["full_name"] as string | undefined) ?? null,
      role,
      profileComplete,
      studentProfile: studentProfile
        ? {
            displayName: studentProfile.display_name,
            semester: studentProfile.semester,
            programme: studentProfile.programme,
            department: studentProfile.department,
            batch: studentProfile.batch,
            section: studentProfile.section,
          }
        : null,
      crRequestStatus,
    };
  },
);
