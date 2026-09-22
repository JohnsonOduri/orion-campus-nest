-- The admin Logs page (src/routes/logs.tsx -> GET /admin/logs) needs to read
-- audit_logs, but the table had RLS enabled with no SELECT policy at all —
-- verified live: with 3 rows present, an anon client saw 0, and so would an
-- admin, since "RLS on + no policy" denies everyone equally. The rows were
-- only ever reachable by service-role (which bypasses RLS), and no router
-- may use service-role to serve a user request (CLAUDE.md §13).
--
-- Admins only: audit_logs records who approved/rejected what, which is not
-- something a student or CR should be able to enumerate. is_admin() is the
-- same helper every other admin-gated policy in this schema uses.

alter table public.audit_logs enable row level security;

drop policy if exists "audit_logs_select_admin" on public.audit_logs;
create policy "audit_logs_select_admin"
  on public.audit_logs for select
  using (public.is_admin());
