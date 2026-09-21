-- ORION — Fix missing auth trigger
--
-- The on_auth_user_created trigger was completely missing from migrations!
-- It was assumed to be present, but local `supabase start` had no way to create it.
-- This ensures that new Google/Email signups correctly invoke handle_new_user()
-- and populate public.profiles. Without this, new accounts were completely broken.

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
