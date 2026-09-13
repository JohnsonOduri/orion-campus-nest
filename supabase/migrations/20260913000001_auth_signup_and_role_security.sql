-- Authentication foundation: domain-restricted Google signup, safe role
-- assignment/escalation rules, and the RLS policies needed for a student to
-- complete their own onboarding and for an admin to manage users/approvals.
--
-- Google OAuth itself is already enabled on this project (external_google_*
-- config) — this migration only adds the domain gate and the app-level
-- authorization rules around it. See docs/auth.md for the full design.

-- ---------------------------------------------------------------------------
-- 1. Signup domain restriction (Before User Created Auth Hook)
--
-- Every sign-in must be an @iiitkottayam.ac.in institute email, except one
-- explicit test exception (oduri.johnson@gmail.com) for testing admin/CR
-- portals without a real institute account. Enforced server-side in the
-- database — the client can never bypass this by skipping a check.
-- ---------------------------------------------------------------------------
create or replace function public.hook_restrict_signup_by_email_domain(event jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(event->'user'->>'email');
begin
  if v_email is null then
    return jsonb_build_object('error', jsonb_build_object(
      'message', 'An email address is required to sign in.',
      'http_code', 400
    ));
  end if;

  if v_email = 'oduri.johnson@gmail.com' then
    return '{}'::jsonb;
  end if;

  if v_email like '%@iiitkottayam.ac.in' then
    return '{}'::jsonb;
  end if;

  return jsonb_build_object('error', jsonb_build_object(
    'message', 'Sign in with your IIIT Kottayam institute Google account (@iiitkottayam.ac.in).',
    'http_code', 403
  ));
end;
$$;

grant execute on function public.hook_restrict_signup_by_email_domain(jsonb) to supabase_auth_admin;
revoke execute on function public.hook_restrict_signup_by_email_domain(jsonb) from authenticated, anon, public;

-- ---------------------------------------------------------------------------
-- 2. handle_new_user: explicit initial role
--
-- Default STUDENT for every real institute signup. The one test exception
-- gets ADMIN directly (route guards treat ADMIN as allowed into the CR
-- portal too, so this single role satisfies "access to both admin and CR").
-- Every other STUDENT reaches CR only via the request -> admin-approval
-- workflow (approval_requests, §4 below) — never by self-assignment.
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
begin
  insert into public.profiles (id, full_name, email, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'),
    new.email,
    case when lower(new.email) = 'oduri.johnson@gmail.com' then 'ADMIN' else 'STUDENT' end
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- 3. Prevent self-service role escalation
--
-- profiles_update_own (existing policy) lets a user update their own row
-- with no column restriction — meaning, unguarded, any authenticated user
-- could PATCH their own role straight to 'ADMIN' or 'CR'. Block that at the
-- trigger level: a non-admin actor cannot change their own `role`. Role
-- changes only ever happen via admin_update_any_profile (§4) or the
-- SECURITY DEFINER approval RPC (§5).
-- ---------------------------------------------------------------------------
create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.profiles where id = auth.uid() and role = 'ADMIN'
  );
$$;

grant execute on function public.is_admin() to authenticated;

create or replace function public.prevent_role_self_escalation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.role is distinct from old.role and not public.is_admin() then
    raise exception 'Only an administrator can change a user''s role.';
  end if;
  return new;
end;
$$;

drop trigger if exists profiles_prevent_role_self_escalation on public.profiles;
create trigger profiles_prevent_role_self_escalation
  before update on public.profiles
  for each row
  execute function public.prevent_role_self_escalation();

-- ---------------------------------------------------------------------------
-- 4. RLS: admin can see/manage every profile and approval request;
--    a student can create and complete their own student_profiles row
--    (needed for the onboarding form — previously SELECT-only).
-- ---------------------------------------------------------------------------
create policy "profiles_select_admin_all"
  on public.profiles for select
  to authenticated
  using (public.is_admin());

create policy "profiles_update_admin_all"
  on public.profiles for update
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());

create policy "students_insert_own_profile"
  on public.student_profiles for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "students_update_own_profile"
  on public.student_profiles for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "admin_select_all_student_profiles"
  on public.student_profiles for select
  to authenticated
  using (public.is_admin());

create policy "admin_select_all_approval_requests"
  on public.approval_requests for select
  to authenticated
  using (public.is_admin());

create policy "admin_update_all_approval_requests"
  on public.approval_requests for update
  to authenticated
  using (public.is_admin())
  with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- 5. CR access request + approval RPC
--
-- A STUDENT requests CR access (inserts their own approval_requests row,
-- submission_type='cr_access_request', document_id NULL — already allowed
-- by the existing cr_submit_approvals policy). An admin approves/rejects via
-- this RPC only: it is the single place a profile's role can flip to CR,
-- always audited, and unreachable by a non-admin (security definer + an
-- explicit is_admin() check, not just RLS).
-- ---------------------------------------------------------------------------
create or replace function public.review_cr_access_request(
  p_request_id bigint,
  p_approve boolean,
  p_rejection_reason text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_request public.approval_requests;
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can review CR access requests.';
  end if;

  select * into v_request from public.approval_requests where id = p_request_id;
  if not found then
    raise exception 'Request % not found', p_request_id;
  end if;
  if v_request.submission_type <> 'cr_access_request' then
    raise exception 'Request % is not a CR access request', p_request_id;
  end if;

  update public.approval_requests
    set approval_status = case when p_approve then 'approved' else 'rejected' end,
        rejection_reason = case when p_approve then null else p_rejection_reason end,
        reviewed_by = auth.uid(),
        reviewed_at = now(),
        published_at = case when p_approve then now() else null end
    where id = p_request_id;

  if p_approve then
    update public.profiles set role = 'CR' where id = v_request.submitted_by;
  end if;

  insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
  values (
    auth.uid(),
    case when p_approve then 'cr_access_approved' else 'cr_access_rejected' end,
    'approval_requests',
    p_request_id::text,
    jsonb_build_object('submitted_by', v_request.submitted_by, 'rejection_reason', p_rejection_reason)
  );
end;
$$;

grant execute on function public.review_cr_access_request(bigint, boolean, text) to authenticated;
