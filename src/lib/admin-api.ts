import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

import { getSupabaseSessionClient } from "@/lib/supabase-server";

export type CrAccessRequest = {
  id: number;
  submittedBy: string;
  submitterName: string | null;
  submitterEmail: string | null;
  status: "pending" | "approved" | "rejected";
  createdAt: string;
};

/**
 * Admin-only by RLS (admin_select_all_approval_requests requires
 * is_admin()) — a non-admin calling this simply gets an empty list, never
 * an error that leaks that the table has rows.
 */
export const listCrAccessRequests = createServerFn({ method: "GET" }).handler(
  async (): Promise<CrAccessRequest[]> => {
    const request = getRequest();
    const client = getSupabaseSessionClient(request);
    if (!client) return [];

    // approval_requests.submitted_by and profiles.id both reference
    // auth.users independently — no direct FK between the two tables for
    // PostgREST to embed, so resolve names with a second query instead.
    const { data, error } = await client
      .from("approval_requests")
      .select("id,submitted_by,approval_status,created_at")
      .eq("submission_type", "cr_access_request")
      .order("created_at", { ascending: false });
    if (error || !data) return [];

    const ids = [...new Set(data.map((r) => r.submitted_by))];
    const { data: profiles } = ids.length
      ? await client.from("profiles").select("id,full_name,email").in("id", ids)
      : { data: [] as { id: string; full_name: string | null; email: string | null }[] };
    const byId = new Map((profiles ?? []).map((p) => [p.id, p]));

    return data.map((r) => {
      const profile = byId.get(r.submitted_by);
      return {
        id: r.id,
        submittedBy: r.submitted_by,
        submitterName: profile?.full_name ?? null,
        submitterEmail: profile?.email ?? null,
        status: r.approval_status,
        createdAt: r.created_at,
      };
    });
  },
);

export const reviewCrAccessRequest = createServerFn({ method: "POST" })
  .validator((input: unknown) => input as { requestId: number; approve: boolean; reason?: string })
  .handler(async ({ data }) => {
    const request = getRequest();
    const client = getSupabaseSessionClient(request);
    if (!client) throw new Error("Not signed in.");

    const { error } = await client.rpc("review_cr_access_request", {
      p_request_id: data.requestId,
      p_approve: data.approve,
      p_rejection_reason: data.reason ?? null,
    });
    if (error) throw new Error(error.message);
    return { ok: true };
  });
