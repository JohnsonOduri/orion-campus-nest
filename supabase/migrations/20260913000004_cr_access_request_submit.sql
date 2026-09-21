-- ORION — the missing "submit" counterpart to the already-live
-- review_cr_access_request(). Reuses approval_requests (submission_type
-- discriminator) — no new table.
--
-- submitter_note: approval_requests had no column for a submitter's own
-- note/reason (only rejection_reason, for the admin's side) — added here,
-- nullable, generically useful for any future submission_type too.

alter table public.approval_requests
  add column if not exists submitter_note text;

create or replace function public.submit_cr_access_request(
  p_reason text default null
)
returns jsonb
language plpgsql
security invoker
set search_path to 'public'
as $$
declare
  v_uid  uuid := auth.uid();
  v_role text;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;

  select role into v_role from public.profiles where id = v_uid;

  if v_role in ('CR', 'ADMIN') then
    return jsonb_build_object('error', 'already_elevated', 'message', 'You are already a ' || v_role);
  end if;

  if exists (
    select 1 from public.approval_requests
    where submitted_by = v_uid
      and submission_type = 'cr_access_request'
      and approval_status = 'pending'
  ) then
    return jsonb_build_object('error', 'already_pending',
      'message', 'You already have a pending CR request. Please wait for admin review.');
  end if;

  if not exists (select 1 from public.student_profiles where user_id = v_uid) then
    return jsonb_build_object('error', 'profile_incomplete',
      'message', 'Please complete your registration before applying for CR.');
  end if;

  insert into public.approval_requests (submission_type, submitted_by, approval_status, submitter_note)
  values ('cr_access_request', v_uid, 'pending', p_reason);

  return jsonb_build_object('success', true,
    'message', 'Your CR request has been submitted. The admin will review it shortly.');
end;
$$;
