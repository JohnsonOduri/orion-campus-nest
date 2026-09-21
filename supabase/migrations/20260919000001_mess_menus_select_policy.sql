-- mess_menus has RLS enabled but no SELECT policy for regular authenticated
-- users — confirmed via a real request-scoped client returning 0 rows
-- against a table with 124 real rows (service-role client sees them fine).
-- Mirrors the existing public_announcements_select pattern: any
-- authenticated user can read active rows.
drop policy if exists "authenticated_select_active_mess_menus" on public.mess_menus;
create policy "authenticated_select_active_mess_menus"
  on public.mess_menus for select
  to authenticated
  using (status = 'active');
