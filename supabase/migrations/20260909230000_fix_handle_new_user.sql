-- ORION — Repair the auth signup trigger function.
--
-- Discovered during live import verification (STEP 12): user creation failed
-- with GoTrue 500 "Database error creating new user". Root cause: the
-- `on_auth_user_created` trigger calls public.handle_new_user(), which had
-- been recreated WITHOUT `security definer`. It therefore executes as
-- `supabase_auth_admin`, which holds no INSERT policy on the RLS-protected
-- public.profiles table -> every signup fails project-wide.
--
-- Fix: restore the canonical Supabase pattern (security definer, pinned
-- search_path). The function remains insert-only into profiles and does not
-- elevate any client-facing capability; RLS is not weakened.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, email)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'), new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;
