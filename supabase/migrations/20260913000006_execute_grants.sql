-- ORION — tighten direct-RPC-callability per the security advisor findings.
-- handle_new_user/prevent_role_self_escalation only need to run via their
-- triggers (as the function owner); revoking direct EXECUTE closes the
-- "anyone can POST /rest/v1/rpc/handle_new_user" surface without touching
-- the trigger path at all. is_admin()/review_cr_access_request()/
-- submit_cr_access_request()/submit_announcement()/review_announcement()/
-- get_my_profile()/complete_registration() are all meant to be called
-- directly and already self-check — left as-is.

revoke execute on function public.handle_new_user() from public, anon, authenticated;
revoke execute on function public.prevent_role_self_escalation() from public, anon, authenticated;
