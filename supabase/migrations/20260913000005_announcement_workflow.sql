-- ORION — CR announcement authoring + admin approval.
--
-- announcements already has its own lifecycle columns (status/submitted_by/
-- approved_by/approved_at) but, before this migration, exactly one RLS
-- policy existed (public_announcements_select, active-only) — no INSERT
-- for CRs, no UPDATE/approval path, no functions at all. Mirrors the
-- already-proven submit_cr_access_request/review_cr_access_request shape.
--
-- rejection_reason: added so a CR can see WHY their own submission was
-- rejected via submitter_view_own_announcements (audit_logs, where the
-- reason is also recorded, is admin-only).

alter table public.announcements
  add column if not exists rejection_reason text;

create or replace function public.submit_announcement(
  p_title        text,
  p_content      text,
  p_category     text default null,
  p_department   text default null,
  p_batch        text default null,
  p_target_role  text default null,
  p_valid_from   timestamptz default null,
  p_valid_until  timestamptz default null
)
returns jsonb
language plpgsql
security invoker
set search_path to 'public'
as $$
declare
  v_uid  uuid := auth.uid();
  v_role text;
  v_id   bigint;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;

  select role into v_role from public.profiles where id = v_uid;
  if v_role not in ('CR', 'ADMIN') then
    raise exception 'Only a Class Representative or administrator can submit announcements.';
  end if;

  if trim(coalesce(p_title, '')) = '' then
    raise exception 'title is required';
  end if;
  if trim(coalesce(p_content, '')) = '' then
    raise exception 'content is required';
  end if;

  insert into public.announcements (
    title, content, category, department, batch, target_role,
    valid_from, valid_until, status, submitted_by
  )
  values (
    trim(p_title), p_content, p_category, p_department, p_batch, p_target_role,
    p_valid_from, p_valid_until, 'pending', v_uid
  )
  returning id into v_id;

  return jsonb_build_object('success', true, 'id', v_id);
end;
$$;

create or replace function public.review_announcement(
  p_id               bigint,
  p_approve          boolean,
  p_rejection_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path to 'public'
as $$
declare
  v_announcement public.announcements;
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can review announcements.';
  end if;

  select * into v_announcement from public.announcements where id = p_id;
  if not found then
    raise exception 'Announcement % not found', p_id;
  end if;
  if v_announcement.status <> 'pending' then
    raise exception 'Announcement % is not pending review (status=%)', p_id, v_announcement.status;
  end if;

  update public.announcements set
    status           = case when p_approve then 'active' else 'rejected' end,
    approved_by      = auth.uid(),
    approved_at      = case when p_approve then now() else null end,
    published_at     = case when p_approve then now() else null end,
    rejection_reason = case when p_approve then null else p_rejection_reason end,
    updated_at       = now()
  where id = p_id;

  insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
  values (
    auth.uid(),
    case when p_approve then 'announcement_approved' else 'announcement_rejected' end,
    'announcements',
    p_id::text,
    jsonb_build_object('submitted_by', v_announcement.submitted_by, 'rejection_reason', p_rejection_reason)
  );

  return jsonb_build_object('success', true, 'id', p_id,
    'status', case when p_approve then 'active' else 'rejected' end);
end;
$$;

drop policy if exists "submitter_view_own_announcements" on public.announcements;
create policy "submitter_view_own_announcements"
  on public.announcements for select
  using ((select auth.uid()) = submitted_by);

drop policy if exists "admin_select_all_announcements" on public.announcements;
create policy "admin_select_all_announcements"
  on public.announcements for select
  using (public.is_admin());

drop policy if exists "admin_update_all_announcements" on public.announcements;
create policy "admin_update_all_announcements"
  on public.announcements for update
  using (public.is_admin())
  with check (public.is_admin());
