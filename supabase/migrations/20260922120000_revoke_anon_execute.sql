-- Least privilege for RPCs no anonymous caller should reach (Supabase
-- security advisor 0028, 2026-09-22).
--
-- review_announcement / review_cr_access_request are admin actions
-- (SECURITY DEFINER, gated internally by is_admin()); search_document_chunks
-- serves signed-in users only (RLS already hides documents from anon). Every
-- ORION caller uses an authenticated JWT, and `authenticated` keeps its own
-- explicit grant — verified before revoking — so nothing that works today
-- stops working. is_admin() is left alone: RLS policies evaluate it.

revoke execute on function public.review_announcement(bigint, boolean, text) from anon, public;
revoke execute on function public.review_cr_access_request(bigint, boolean, text) from anon, public;
revoke execute on function public.search_document_chunks(text, integer, text, text, text, date) from anon, public;

grant execute on function public.review_announcement(bigint, boolean, text) to authenticated;
grant execute on function public.review_cr_access_request(bigint, boolean, text) to authenticated;
grant execute on function public.search_document_chunks(text, integer, text, text, text, date) to authenticated;
