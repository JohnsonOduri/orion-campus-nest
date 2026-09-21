-- ORION — Capture live auth drift + drop dead duplicate profiles columns
--
-- supabase/migrations/ has never captured is_admin(), the current
-- handle_new_user() (sets role + has an admin-bootstrap exemption),
-- prevent_role_self_escalation(), hook_restrict_signup_by_email_domain(),
-- or 8 RLS policies on profiles/student_profiles that already exist live.
-- This migration re-declares all of it so migration history matches
-- production. Every function/trigger/policy statement below is a verified
-- no-op against the live DB (checked via pg_proc/pg_policies before and
-- after applying).
--
-- It also makes one real change: drops profiles.department/admission_year/
-- semester/section/batch. Verified by reading every live function body —
-- nothing reads these columns; student_profiles holds the real academic
-- context for every timetable RPC (orion_student_context and everything
-- built on it). Only one non-null value existed across all 5 live rows
-- (a test account's admission_year), confirmed before dropping.

-- ---------------------------------------------------------------- functions

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path to 'public'
as $$
  select exists (
    select 1 from public.profiles where id = auth.uid() and role = 'ADMIN'
  );
$$;

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

create or replace function public.prevent_role_self_escalation()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
begin
  if new.role is distinct from old.role and not public.is_admin() then
    raise exception 'Only an administrator can change a user''s role.';
  end if;
  return new;
end;
$$;

create or replace function public.hook_restrict_signup_by_email_domain(event jsonb)
returns jsonb
language plpgsql
security definer
set search_path to 'public'
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

-- ----------------------------------------------------------------- triggers

drop trigger if exists profiles_prevent_role_self_escalation on public.profiles;
create trigger profiles_prevent_role_self_escalation
  before update on public.profiles
  for each row execute function public.prevent_role_self_escalation();

-- profiles_updated_at / on_auth_user_created already exist and are
-- unrelated to this capture — left untouched.

-- ------------------------------------------------------------- RLS policies

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles for select
  using ((select auth.uid()) = id);

drop policy if exists "profiles_select_admin_all" on public.profiles;
create policy "profiles_select_admin_all"
  on public.profiles for select
  using (public.is_admin());

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

drop policy if exists "profiles_update_admin_all" on public.profiles;
create policy "profiles_update_admin_all"
  on public.profiles for update
  using (public.is_admin())
  with check (public.is_admin());

drop policy if exists "students read own profile" on public.student_profiles;
create policy "students read own profile"
  on public.student_profiles for select
  using (auth.uid() = user_id);

drop policy if exists "students_insert_own_profile" on public.student_profiles;
create policy "students_insert_own_profile"
  on public.student_profiles for insert
  with check (auth.uid() = user_id);

drop policy if exists "students_update_own_profile" on public.student_profiles;
create policy "students_update_own_profile"
  on public.student_profiles for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "admin_select_all_student_profiles" on public.student_profiles;
create policy "admin_select_all_student_profiles"
  on public.student_profiles for select
  using (public.is_admin());

-- ------------------------------------------------------- dead-column drop

alter table public.profiles
  drop column if exists department,
  drop column if exists admission_year,
  drop column if exists semester,
  drop column if exists section,
  drop column if exists batch;
