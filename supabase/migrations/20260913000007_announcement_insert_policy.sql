-- Migration 5 (20260913000005_announcement_workflow.sql) added SELECT/UPDATE
-- RLS policies for `announcements` but missed an INSERT policy. This left
-- submit_announcement() (SECURITY INVOKER) unable to insert at all, since
-- RLS has no policy granting CR/ADMIN an insert. Found via live verification
-- of the CR announcement-authoring flow.
drop policy if exists cr_admin_insert_announcements on public.announcements;
create policy cr_admin_insert_announcements on public.announcements
  for insert
  with check (
    submitted_by = (select auth.uid())
    and (
      public.is_admin()
      or (select role from public.profiles where id = (select auth.uid())) = 'CR'
    )
  );
