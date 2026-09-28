-- CR upload workflow: timetable changes (admin approval) and class
-- announcements (published straight away when academic).
--
-- What a CR can do after this migration:
--   1. Upload a timetable (PDF/image) → backend extracts it → CR corrects
--      it in an editable grid → submit_cr_timetable() stores the proposal
--      in approval_requests (never touches timetable_entries).
--      An admin reviews it; review_cr_timetable() is the ONLY thing that
--      writes the new periods, superseding the class's old ones.
--   2. Upload or type an announcement. An ACADEMIC one (quiz, exam,
--      assignment, class update, deadline) aimed at the CR's OWN class is
--      published immediately; anything else is 'pending' for an admin as
--      before. That rule is enforced here, in RLS, not only in the API.
--      Every auto-published announcement is audit-logged and an admin can
--      take it down (archive_announcement).
--
-- Additive: new columns are nullable/defaulted, existing rows unchanged.

-- ------------------------------------------------------------- columns

alter table public.approval_requests
  add column if not exists payload jsonb,
  add column if not exists source_file_path text;

alter table public.announcements
  add column if not exists semester smallint,
  add column if not exists programme text,
  add column if not exists section text,
  add column if not exists event_date date,
  add column if not exists event_time time,
  add column if not exists auto_published boolean not null default false,
  add column if not exists source_kind text,
  add column if not exists source_file_path text;

do $$ begin
  alter table public.announcements
    add constraint announcements_source_kind_check check (source_kind is null or source_kind in ('typed', 'upload'));
exception when duplicate_object then null; end $$;

-- Categories a CR may publish to their own class without admin review.
create or replace function public.orion_is_academic_category(p_category text)
returns boolean
language sql
immutable
set search_path = public
as $$
  select upper(coalesce(p_category, '')) in ('ACADEMIC', 'QUIZ', 'EXAM', 'ASSIGNMENT', 'CLASS_UPDATE', 'DEADLINE');
$$;

-- --------------------------------------------------- announcements RLS

-- Replaces the old "CR/admin may insert anything" policy: a CR's row is
-- either pending review, or an auto-published academic notice scoped to
-- exactly the CR's own class with an expiry at most ~2 months out.
drop policy if exists cr_admin_insert_announcements on public.announcements;
create policy cr_admin_insert_announcements on public.announcements
  for insert
  with check (
    submitted_by = (select auth.uid())
    and (
      public.is_admin()
      or (
        (select p.role from public.profiles p where p.id = (select auth.uid())) = 'CR'
        and (
          (status = 'pending' and not auto_published)
          or (
            status = 'active'
            and auto_published
            and public.orion_is_academic_category(category)
            and valid_until is not null
            and valid_until <= now() + interval '62 days'
            and exists (
              select 1 from public.student_profiles sp
              where sp.user_id = (select auth.uid())
                and sp.semester = announcements.semester
                and sp.department = announcements.department
                and sp.batch is not distinct from announcements.batch
                and sp.section is not distinct from announcements.section
            )
          )
        )
      )
    )
  );

-- Audit trail for auto-published announcements (no admin action exists to
-- log them otherwise). Append-only: the function can do nothing but add
-- one audit row describing the row that was just inserted.
create or replace function public.audit_announcement_auto_publish()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.auto_published and new.status = 'active' then
    insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data, metadata)
    values (
      new.submitted_by,
      'announcement_auto_published',
      'announcements',
      new.id::text,
      jsonb_build_object('title', new.title, 'category', new.category, 'semester', new.semester,
                         'department', new.department, 'section', new.section,
                         'event_date', new.event_date, 'valid_until', new.valid_until),
      jsonb_build_object('source_kind', new.source_kind, 'source_file_path', new.source_file_path)
    );
  end if;
  return new;
end;
$$;
revoke execute on function public.audit_announcement_auto_publish() from public, anon, authenticated;

drop trigger if exists announcements_auto_publish_audit on public.announcements;
create trigger announcements_auto_publish_audit
  after insert on public.announcements
  for each row execute function public.audit_announcement_auto_publish();

-- Admin take-down of a live announcement (auto-published or approved).
create or replace function public.archive_announcement(p_id bigint, p_reason text default null)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_row public.announcements;
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can take down announcements.';
  end if;
  select * into v_row from public.announcements where id = p_id for update;
  if not found then
    raise exception 'Announcement % not found', p_id;
  end if;
  if v_row.status <> 'active' then
    raise exception 'Announcement % is not live (status=%)', p_id, v_row.status;
  end if;
  update public.announcements
     set status = 'archived', rejection_reason = p_reason, updated_at = now()
   where id = p_id;
  insert into public.audit_logs (actor_id, action, entity_type, entity_id, old_data, new_data)
  values (auth.uid(), 'announcement_taken_down', 'announcements', p_id::text,
          jsonb_build_object('status', v_row.status, 'title', v_row.title, 'submitted_by', v_row.submitted_by,
                             'auto_published', v_row.auto_published),
          jsonb_build_object('status', 'archived', 'reason', p_reason));
  return jsonb_build_object('success', true, 'id', p_id, 'status', 'archived');
end;
$$;
revoke execute on function public.archive_announcement(bigint, text) from public, anon;
grant execute on function public.archive_announcement(bigint, text) to authenticated;

-- ----------------------------------------------- approval_requests RLS

-- Only a CR/admin may file a timetable proposal (the old policy let any
-- signed-in user insert any submission_type for themselves).
drop policy if exists cr_submit_approvals on public.approval_requests;
create policy cr_submit_approvals on public.approval_requests
  for insert to authenticated
  with check (
    (select auth.uid()) = submitted_by
    and approval_status = 'pending'
    and (
      submission_type = 'cr_access_request'
      or (
        submission_type = 'timetable_update'
        and (select p.role from public.profiles p where p.id = (select auth.uid())) in ('CR', 'ADMIN')
      )
    )
  );

-- ------------------------------------------------ timetable proposals

-- A CR proposes a new timetable for THEIR OWN class (from student_profiles,
-- never from the request). Nothing authoritative changes here.
create or replace function public.submit_cr_timetable(
  p_entries jsonb,
  p_valid_from date default null,
  p_valid_until date default null,
  p_note text default null,
  p_source_path text default null
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_uid  uuid := auth.uid();
  v_role text;
  v_sp   public.student_profiles;
  v_n    integer;
  v_e    jsonb;
  v_id   bigint;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;
  select role into v_role from public.profiles where id = v_uid;
  if v_role not in ('CR', 'ADMIN') then
    raise exception 'Only a Class Representative can submit a timetable.';
  end if;
  select * into v_sp from public.student_profiles where user_id = v_uid;
  if not found then
    raise exception 'Complete your academic profile before submitting a timetable.';
  end if;
  if jsonb_typeof(p_entries) is distinct from 'array' then
    raise exception 'entries must be a JSON array';
  end if;
  v_n := jsonb_array_length(p_entries);
  if v_n < 1 or v_n > 200 then
    raise exception 'A timetable needs between 1 and 200 periods (got %).', v_n;
  end if;
  for v_e in select * from jsonb_array_elements(p_entries) loop
    if (v_e->>'day_of_week')::int not between 1 and 7 then
      raise exception 'Invalid day_of_week %', v_e->>'day_of_week';
    end if;
    if (v_e->>'start_time')::time >= (v_e->>'end_time')::time then
      raise exception 'A period must end after it starts (% - %)', v_e->>'start_time', v_e->>'end_time';
    end if;
  end loop;
  if p_valid_until is not null and p_valid_until < coalesce(p_valid_from, current_date) then
    raise exception 'valid_until must be on or after valid_from';
  end if;
  if p_source_path is not null and p_source_path not like v_uid::text || '/%' then
    raise exception 'source file must be one you uploaded';
  end if;

  insert into public.approval_requests (submission_type, submitted_by, approval_status, submitter_note, payload, source_file_path)
  values (
    'timetable_update', v_uid, 'pending', nullif(trim(coalesce(p_note, '')), ''),
    jsonb_build_object(
      'class', jsonb_build_object('semester', v_sp.semester, 'programme', v_sp.programme,
                                  'department', v_sp.department, 'batch', v_sp.batch, 'section', v_sp.section),
      'valid_from', coalesce(p_valid_from, current_date),
      'valid_until', p_valid_until,
      'entries', p_entries
    ),
    p_source_path
  )
  returning id into v_id;

  return jsonb_build_object('success', true, 'id', v_id, 'status', 'pending');
end;
$$;
revoke execute on function public.submit_cr_timetable(jsonb, date, date, text, text) from public, anon;
grant execute on function public.submit_cr_timetable(jsonb, date, date, text, text) to authenticated;

-- Admin decision. On approval this is the ONE place a CR's proposal
-- becomes authoritative: the class's current periods are closed off at
-- valid_from - 1 (superseded if that is already past) and the proposed
-- periods are inserted, each course/faculty resolved against the live
-- directory — an unknown code/initials aborts the whole approval rather
-- than being guessed. Same SECURITY DEFINER + is_admin() pattern as
-- review_announcement: the write spans timetable_entries,
-- timetable_entry_faculty, approval_requests and audit_logs atomically,
-- and clients have no direct write access to any of them.
create or replace function public.review_cr_timetable(
  p_request_id bigint,
  p_approve boolean,
  p_rejection_reason text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_req    public.approval_requests;
  v_cls    jsonb;
  v_sem    integer;
  v_dept   text;
  v_batch  text;
  v_sect   text;
  v_prog   text;
  v_from   date;
  v_until  date;
  v_e      jsonb;
  v_i      integer := 0;
  v_course bigint;
  v_entry  bigint;
  v_type   text;
  v_ini    text;
  v_fid    bigint;
  v_ord    integer;
  v_old    integer := 0;
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can review timetable submissions.';
  end if;

  select * into v_req from public.approval_requests where id = p_request_id for update;
  if not found or v_req.submission_type <> 'timetable_update' then
    raise exception 'Timetable submission % not found', p_request_id;
  end if;
  if v_req.approval_status <> 'pending' then
    raise exception 'Timetable submission % is not pending (status=%)', p_request_id, v_req.approval_status;
  end if;

  if not p_approve then
    update public.approval_requests
       set approval_status = 'rejected', rejection_reason = p_rejection_reason,
           reviewed_by = auth.uid(), reviewed_at = now()
     where id = p_request_id;
    insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
    values (auth.uid(), 'timetable_submission_rejected', 'approval_requests', p_request_id::text,
            jsonb_build_object('submitted_by', v_req.submitted_by, 'rejection_reason', p_rejection_reason));
    return jsonb_build_object('success', true, 'id', p_request_id, 'status', 'rejected');
  end if;

  v_cls   := v_req.payload->'class';
  v_sem   := (v_cls->>'semester')::integer;
  v_dept  := v_cls->>'department';
  v_batch := v_cls->>'batch';
  v_sect  := v_cls->>'section';
  v_prog  := coalesce(v_cls->>'programme', 'B.Tech');
  v_from  := greatest(coalesce((v_req.payload->>'valid_from')::date, current_date), current_date);

  -- Runs to the end of the term the current timetable covers unless the
  -- CR gave an end date.
  select max(valid_until) into v_until
    from public.timetable_entries
   where semester = v_sem and department = v_dept and batch is not distinct from v_batch
     and section is not distinct from v_sect and status = 'active';
  v_until := coalesce((v_req.payload->>'valid_until')::date, v_until);
  if v_until is null then
    raise exception 'This class has no current timetable to take an end date from; ask the CR to set one.';
  end if;
  if v_until < v_from then
    raise exception 'The new timetable would end (%) before it starts (%).', v_until, v_from;
  end if;

  update public.timetable_entries
     set valid_until = least(coalesce(valid_until, v_from - 1), v_from - 1),
         status = case when v_from <= current_date or (valid_from is not null and valid_from >= v_from)
                       then 'superseded' else status end,
         updated_at = now()
   where semester = v_sem and department = v_dept and batch is not distinct from v_batch
     and section is not distinct from v_sect and status = 'active';
  get diagnostics v_old = row_count;

  for v_e in select * from jsonb_array_elements(v_req.payload->'entries') loop
    v_i := v_i + 1;
    v_type := coalesce(nullif(v_e->>'entry_type', ''), 'class');
    v_course := null;
    if coalesce(v_e->>'course_code', '') <> '' then
      select id into v_course from public.courses
       where upper(replace(course_code, ' ', '')) = upper(replace(v_e->>'course_code', ' ', ''));
      if v_course is null then
        raise exception 'Period %: unknown course code "%". Nothing was changed.', v_i, v_e->>'course_code';
      end if;
    elsif v_type in ('class', 'lab', 'tutorial') then
      raise exception 'Period %: a % needs a course code. Nothing was changed.', v_i, v_type;
    end if;

    insert into public.timetable_entries (
      course_id, day_of_week, slot_index, start_time, end_time, semester, programme, department,
      batch, section, entry_type, valid_from, valid_until, status, source_id, approved_at, approved_by,
      source_uid, source_text, lab_batch
    ) values (
      v_course, (v_e->>'day_of_week')::smallint, nullif(v_e->>'slot_index', '')::integer,
      (v_e->>'start_time')::time, (v_e->>'end_time')::time, v_sem, v_prog, v_dept,
      v_batch, v_sect, v_type, v_from, v_until, 'active', 'cr_submission:' || p_request_id, now(), auth.uid(),
      'cr:' || p_request_id || ':' || v_i, left(v_e->>'source_text', 500), nullif(v_e->>'lab_batch', '')::smallint
    )
    returning id into v_entry;

    v_ord := 0;
    for v_ini in select jsonb_array_elements_text(coalesce(v_e->'faculty_initials', '[]'::jsonb)) loop
      select id into v_fid from public.faculty where upper(initials) = upper(trim(v_ini));
      if v_fid is null then
        raise exception 'Period %: unknown faculty initials "%". Nothing was changed.', v_i, v_ini;
      end if;
      insert into public.timetable_entry_faculty (entry_id, faculty_id, ord) values (v_entry, v_fid, v_ord)
      on conflict do nothing;
      if v_ord = 0 then
        update public.timetable_entries set faculty_id = v_fid where id = v_entry;
      end if;
      v_ord := v_ord + 1;
    end loop;
  end loop;

  update public.approval_requests
     set approval_status = 'approved', rejection_reason = null,
         reviewed_by = auth.uid(), reviewed_at = now(), published_at = now()
   where id = p_request_id;

  insert into public.audit_logs (actor_id, action, entity_type, entity_id, old_data, new_data, metadata)
  values (auth.uid(), 'timetable_submission_approved', 'approval_requests', p_request_id::text,
          jsonb_build_object('closed_entries', v_old),
          jsonb_build_object('inserted_entries', v_i, 'class', v_cls, 'valid_from', v_from, 'valid_until', v_until,
                             'submitted_by', v_req.submitted_by),
          jsonb_build_object('source_id', 'cr_submission:' || p_request_id, 'source_file_path', v_req.source_file_path));

  return jsonb_build_object('success', true, 'id', p_request_id, 'status', 'approved',
                            'inserted', v_i, 'closed', v_old, 'valid_from', v_from, 'valid_until', v_until);
end;
$$;
revoke execute on function public.review_cr_timetable(bigint, boolean, text) from public, anon;
grant execute on function public.review_cr_timetable(bigint, boolean, text) to authenticated;

-- ------------------------------------------------------------- storage

-- Private bucket for the original files (audit: "what source caused it?").
-- 4 MB matches what the frontend proxy can carry.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('cr-uploads', 'cr-uploads', false, 4194304,
        array['application/pdf', 'image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
  set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists cr_uploads_insert_own on storage.objects;
create policy cr_uploads_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'cr-uploads'
    and (storage.foldername(name))[1] = (select auth.uid())::text
    and (select p.role from public.profiles p where p.id = (select auth.uid())) in ('CR', 'ADMIN')
  );

drop policy if exists cr_uploads_select_own_or_admin on storage.objects;
create policy cr_uploads_select_own_or_admin on storage.objects
  for select to authenticated
  using (
    bucket_id = 'cr-uploads'
    and ((storage.foldername(name))[1] = (select auth.uid())::text or public.is_admin())
  );
