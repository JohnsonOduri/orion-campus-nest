import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";

import { getSupabaseSessionClient } from "@/lib/supabase-server";

/**
 * A STUDENT asks to become a CR. Inserts their own approval_requests row
 * (RLS: cr_submit_approvals already allows a self-insert with
 * submitted_by = auth.uid()); the role change itself only ever happens via
 * the admin-only review_cr_access_request RPC (never here) — see
 * supabase/migrations/20260913000001_auth_signup_and_role_security.sql.
 */
export const requestCrAccess = createServerFn({ method: "POST" }).handler(async () => {
  const request = getRequest();
  const client = getSupabaseSessionClient(request);
  if (!client) throw new Error("Not signed in.");

  const {
    data: { user },
  } = await client.auth.getUser();
  if (!user) throw new Error("Not signed in.");

  const { error } = await client
    .from("approval_requests")
    .insert({ submission_type: "cr_access_request", submitted_by: user.id });
  if (error) throw new Error(error.message);
  return { ok: true };
});
