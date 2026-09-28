-- Exams from uploads, one-off class changes, admin publishing, role
-- management, registration fields, and section-locked CR notices.
-- (2026-09-28; docs/cr-workflow.md "Round 2")
--
--  1. exams: rows carry the printed course code/name (many exam codes —
--     other departments' electives — aren't in the timetable-derived course
--     catalogue) and the department the exam is for. A CR proposes an exam
--     schedule for their own semester + department; an admin approves it
--     (review_exam_schedule), which supersedes that scope's previous rows.
--  2. class_changes: one-off cancellations / reschedules / extra classes a
--     CR announces for their own class. Live immediately (like other
--     academic notices), audited, and applied to every schedule answer.
--     Permanent changes stay timetable proposals that need an admin.
--  3. Admins can publish to any class (target given explicitly), and grant
--     or revoke CR / ADMIN — also to an email that hasn't signed in yet.
--     oduri.johnson@gmail.com stays ADMIN; the last admin can't be removed.
--  4. Registration: roll number + admission year stored; year can't be in
--     the future; batch = section.
--  5. Every CR notice (pending or live) is locked to the CR's own class.
--
-- Additive where possible; function signatures that gain a parameter are
-- dropped and recreated (grants re-applied).

-- ============================================================ registration

alter table public.student_profiles
  add column if not exists roll_number text,
  add column if not exists admission_year smallint;

create unique index if not exists student_profiles_roll_number_uidx
  on public.student_profiles (upper(roll_number)) where roll_number is not null;

drop function if exists public.complete_registration(text, smallint, text, text, text, integer, text);
create or replace function public.complete_registration(
  p_full_name      text,
  p_semester       smallint,
  p_department     text,
  p_batch          text,
  p_section        text,
  p_admission_year integer,
  p_programme      text default 'B.Tech',
  p_roll_number    text default null
)
returns jsonb
language plpgsql
security invoker
set search_path to 'public'
as $$
declare
  v_uid    uuid := auth.uid();
  v_cohort text;
  v_roll   text := upper(nullif(trim(coalesce(p_roll_number, '')), ''));
  v_year   integer := extract(year from (now() at time zone 'Asia/Kolkata'))::integer;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;
  if trim(coalesce(p_full_name, '')) = '' then
    raise exception 'full_name is required';
  end if;
  if p_semester not between 1 and 8 then
    raise exception 'semester must be 1-8, got %', p_semester;
  end if;
  if p_admission_year is null or p_admission_year < 2015 or p_admission_year > v_year then
    raise exception 'Admission year must be between 2015 and %.', v_year;
  end if;
  if v_roll is not null and v_roll !~ '^[A-Z0-9]{6,15}$' then
    raise exception 'Roll number should be 6-15 letters and digits (e.g. 2024BCS0066).';
  end if;
  if v_roll is not null and exists (
      select 1 from public.student_profiles where upper(roll_number) = v_roll and user_id <> v_uid) then
    raise exception 'That roll number is already registered to another account.';
  end if;

  v_cohort := case when p_admission_year >= 2026 then '2026_onwards' else '2021_2025' end;

  update public.profiles set full_name = trim(p_full_name), updated_at = now() where id = v_uid;
  if not found then
    raise exception 'Profile not found for %. Signup trigger may have failed.', v_uid;
  end if;

  insert into public.student_profiles (
    user_id, display_name, semester, programme, department, batch, section, cohort, roll_number, admission_year
  ) values (
    v_uid, trim(p_full_name), p_semester, coalesce(p_programme, 'B.Tech'), p_department,
    coalesce(nullif(p_batch, ''), p_section), p_section, v_cohort, v_roll, p_admission_year
  )
  on conflict (user_id) do update set
    display_name   = excluded.display_name,
    semester       = excluded.semester,
    programme      = excluded.programme,
    department     = excluded.department,
    batch          = excluded.batch,
    section        = excluded.section,
    cohort         = excluded.cohort,
    roll_number    = excluded.roll_number,
    admission_year = excluded.admission_year,
    updated_at     = now();

  return jsonb_build_object('success', true, 'cohort', v_cohort);
end;
$$;
revoke execute on function public.complete_registration(text, smallint, text, text, text, integer, text, text) from public, anon;
grant execute on function public.complete_registration(text, smallint, text, text, text, integer, text, text) to authenticated;

create or replace function public.get_my_profile()
returns jsonb
language plpgsql
stable
security invoker
set search_path to 'public'
as $$
declare
  v_uid     uuid := auth.uid();
  v_profile record;
  v_student record;
  v_onboarded boolean;
  v_pending boolean;
begin
  if v_uid is null then
    return jsonb_build_object('error', 'not_authenticated');
  end if;
  select id, full_name, email, role, created_at into v_profile from public.profiles where id = v_uid;
  if not found then
    return jsonb_build_object('error', 'profile_not_found');
  end if;
  select display_name, programme, cohort, department, semester, batch, section, roll_number, admission_year
    into v_student from public.student_profiles where user_id = v_uid;
  v_onboarded := found;
  select exists (
    select 1 from public.approval_requests
    where submitted_by = v_uid and submission_type = 'cr_access_request' and approval_status = 'pending'
  ) into v_pending;
  return jsonb_build_object(
    'id', v_profile.id, 'full_name', v_profile.full_name, 'email', v_profile.email, 'role', v_profile.role,
    'onboarded', v_onboarded, 'pending_cr_request', v_pending,
    'department', v_student.department, 'semester', v_student.semester, 'batch', v_student.batch,
    'section', v_student.section, 'display_name', v_student.display_name, 'programme', v_student.programme,
    'cohort', v_student.cohort, 'roll_number', v_student.roll_number, 'admission_year', v_student.admission_year
  );
end;
$$;

-- Registration dropdowns: the classes that actually have a timetable.
create or replace function public.orion_class_options()
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select coalesce(jsonb_agg(jsonb_build_object('programme', programme, 'semester', semester,
                                               'department', department, 'section', section)
                            order by semester, department, section), '[]'::jsonb)
  from (
    select distinct coalesce(programme, 'B.Tech') as programme, semester, department, section
      from public.timetable_entries
     where status = 'active' and semester is not null and department is not null and section is not null
  ) c;
$$;
revoke execute on function public.orion_class_options() from public, anon;
grant execute on function public.orion_class_options() to authenticated;

-- ======================================================= role management

create table if not exists public.role_grants (
  email text primary key check (email = lower(email)),
  role text not null check (role in ('CR', 'ADMIN', 'FACULTY')),
  granted_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);
alter table public.role_grants enable row level security;
drop policy if exists role_grants_admin_select on public.role_grants;
create policy role_grants_admin_select on public.role_grants for select to authenticated using (public.is_admin());
revoke all on public.role_grants from anon;
grant select on public.role_grants to authenticated;

-- A pre-authorised email gets its role on first sign-in.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
declare
  v_grant text;
begin
  select role into v_grant from public.role_grants where email = lower(new.email);
  insert into public.profiles (id, full_name, email, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'),
    new.email,
    case when lower(new.email) = 'oduri.johnson@gmail.com' then 'ADMIN' else coalesce(v_grant, 'STUDENT') end
  )
  on conflict (id) do nothing;
  if v_grant is not null then
    delete from public.role_grants where email = lower(new.email);
  end if;
  return new;
end;
$$;

create or replace function public.admin_set_role(p_email text, p_role text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(coalesce(p_email, '')));
  v_role  text := upper(trim(coalesce(p_role, '')));
  v_prof  public.profiles;
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can change roles.';
  end if;
  if v_role not in ('STUDENT', 'CR', 'ADMIN', 'FACULTY') then
    raise exception 'Unknown role %', p_role;
  end if;
  if v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception 'Enter a valid email address.';
  end if;
  if v_email = 'oduri.johnson@gmail.com' and v_role <> 'ADMIN' then
    raise exception 'The default administrator can''t be changed.';
  end if;

  select * into v_prof from public.profiles where lower(email) = v_email;
  if not found then
    -- Not signed in yet: remember the grant for their first sign-in.
    if v_role = 'STUDENT' then
      delete from public.role_grants where email = v_email;
    else
      insert into public.role_grants (email, role, granted_by) values (v_email, v_role, auth.uid())
      on conflict (email) do update set role = excluded.role, granted_by = excluded.granted_by, created_at = now();
    end if;
    insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
    values (auth.uid(), 'role_pre_authorised', 'role_grants', v_email, jsonb_build_object('role', v_role));
    return jsonb_build_object('success', true, 'email', v_email, 'role', v_role, 'pending_sign_in', true);
  end if;

  if v_prof.role = 'ADMIN' and v_role <> 'ADMIN'
     and (select count(*) from public.profiles where role = 'ADMIN') <= 1 then
    raise exception 'That would leave ORION without an administrator.';
  end if;
  update public.profiles set role = v_role, updated_at = now() where id = v_prof.id;
  -- An open CR request is settled by the grant.
  update public.approval_requests
     set approval_status = case when v_role in ('CR', 'ADMIN') then 'approved' else 'rejected' end,
         reviewed_by = auth.uid(), reviewed_at = now(),
         rejection_reason = case when v_role in ('CR', 'ADMIN') then null else 'Role set by an administrator' end
   where submitted_by = v_prof.id and submission_type = 'cr_access_request' and approval_status = 'pending';
  insert into public.audit_logs (actor_id, action, entity_type, entity_id, old_data, new_data)
  values (auth.uid(), 'role_changed', 'profiles', v_prof.id::text,
          jsonb_build_object('role', v_prof.role, 'email', v_prof.email), jsonb_build_object('role', v_role));
  return jsonb_build_object('success', true, 'email', v_email, 'role', v_role, 'previous_role', v_prof.role);
end;
$$;
revoke execute on function public.admin_set_role(text, text) from public, anon;
grant execute on function public.admin_set_role(text, text) to authenticated;

-- ============================================ admin publishes to any class

-- The class a submission is for: a CR's own (from student_profiles), or —
-- only for an admin — the target given.
create or replace function public.orion_submission_class(p_target jsonb)
returns jsonb
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
  v_uid  uuid := auth.uid();
  v_role text;
  v_sp   public.student_profiles;
begin
  select role into v_role from public.profiles where id = v_uid;
  if v_role = 'ADMIN' and p_target is not null and p_target ? 'semester' then
    return jsonb_build_object('semester', (p_target->>'semester')::int, 'programme', coalesce(p_target->>'programme', 'B.Tech'),
                              'department', p_target->>'department', 'batch', coalesce(p_target->>'batch', p_target->>'section'),
                              'section', p_target->>'section');
  end if;
  if v_role not in ('CR', 'ADMIN') then
    raise exception 'Only a Class Representative or administrator can submit this.';
  end if;
  select * into v_sp from public.student_profiles where user_id = v_uid;
  if not found then
    raise exception 'Choose the class this is for (admins) or complete your academic profile (CRs).';
  end if;
  return jsonb_build_object('semester', v_sp.semester, 'programme', v_sp.programme, 'department', v_sp.department,
                            'batch', v_sp.batch, 'section', v_sp.section);
end;
$$;
revoke execute on function public.orion_submission_class(jsonb) from public, anon;
grant execute on function public.orion_submission_class(jsonb) to authenticated;

drop function if exists public.submit_cr_timetable(jsonb, date, date, text, text);
create or replace function public.submit_cr_timetable(
  p_entries jsonb,
  p_valid_from date default null,
  p_valid_until date default null,
  p_note text default null,
  p_source_path text default null,
  p_target jsonb default null
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_uid  uuid := auth.uid();
  v_cls  jsonb;
  v_n    integer;
  v_e    jsonb;
  v_id   bigint;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;
  v_cls := public.orion_submission_class(p_target);
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
  values ('timetable_update', v_uid, 'pending', nullif(trim(coalesce(p_note, '')), ''),
          jsonb_build_object('class', v_cls, 'valid_from', coalesce(p_valid_from, current_date),
                             'valid_until', p_valid_until, 'entries', p_entries),
          p_source_path)
  returning id into v_id;
  return jsonb_build_object('success', true, 'id', v_id, 'status', 'pending');
end;
$$;
revoke execute on function public.submit_cr_timetable(jsonb, date, date, text, text, jsonb) from public, anon;
grant execute on function public.submit_cr_timetable(jsonb, date, date, text, text, jsonb) to authenticated;

-- ===================================================================== exams

alter table public.exams
  add column if not exists programme text,
  add column if not exists department text,
  add column if not exists course_code text,
  add column if not exists course_name text,
  add column if not exists alt_group text,
  add column if not exists notes text;

create index if not exists exams_scope_idx on public.exams (semester, exam_type, status);

-- A CR (own semester + department) or admin (any semester; departments per
-- row) proposes an exam schedule. Nothing in `exams` changes here.
create or replace function public.submit_exam_schedule(
  p_entries jsonb,
  p_exam_type text,
  p_note text default null,
  p_source_path text default null,
  p_target jsonb default null
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_uid  uuid := auth.uid();
  v_role text;
  v_cls  jsonb;
  v_n    integer;
  v_e    jsonb;
  v_id   bigint;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;
  select role into v_role from public.profiles where id = v_uid;
  if p_exam_type not in ('end_sem', 'mid_sem', 'repeat', 'quiz', 'other') then
    raise exception 'Unknown exam type %', p_exam_type;
  end if;
  v_cls := public.orion_submission_class(p_target);
  if jsonb_typeof(p_entries) is distinct from 'array' then
    raise exception 'entries must be a JSON array';
  end if;
  v_n := jsonb_array_length(p_entries);
  if v_n < 1 or v_n > 300 then
    raise exception 'An exam schedule needs between 1 and 300 exams (got %).', v_n;
  end if;
  for v_e in select * from jsonb_array_elements(p_entries) loop
    perform (v_e->>'exam_date')::date;
    if (v_e->>'start_time')::time >= (v_e->>'end_time')::time then
      raise exception 'An exam must end after it starts (% - %)', v_e->>'start_time', v_e->>'end_time';
    end if;
    if coalesce(v_e->>'course_code', '') = '' then
      raise exception 'Every exam needs a course code.';
    end if;
    -- A CR's schedule is only ever for their own department.
    if v_role = 'CR' and coalesce(v_e->>'department', v_cls->>'department') <> v_cls->>'department' then
      raise exception 'A CR can only submit exams for their own department.';
    end if;
  end loop;
  if p_source_path is not null and p_source_path not like v_uid::text || '/%' then
    raise exception 'source file must be one you uploaded';
  end if;
  insert into public.approval_requests (submission_type, submitted_by, approval_status, submitter_note, payload, source_file_path)
  values ('exam_schedule', v_uid, 'pending', nullif(trim(coalesce(p_note, '')), ''),
          jsonb_build_object('class', v_cls, 'exam_type', p_exam_type, 'entries', p_entries,
                             'all_departments', v_role = 'ADMIN' and p_target is not null and not (p_target ? 'department')),
          p_source_path)
  returning id into v_id;
  return jsonb_build_object('success', true, 'id', v_id, 'status', 'pending');
end;
$$;
revoke execute on function public.submit_exam_schedule(jsonb, text, text, text, jsonb) from public, anon;
grant execute on function public.submit_exam_schedule(jsonb, text, text, text, jsonb) to authenticated;

-- Admin decision: the scope's (semester, exam type, department) previous
-- exams are superseded and the proposed ones inserted. Course ids are
-- linked when the code is in the catalogue; the printed code/name is kept
-- either way.
create or replace function public.review_exam_schedule(
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
  v_req   public.approval_requests;
  v_cls   jsonb;
  v_type  text;
  v_sem   integer;
  v_e     jsonb;
  v_n     integer := 0;
  v_old   integer := 0;
  v_depts text[];
begin
  if not public.is_admin() then
    raise exception 'Only an administrator can review exam schedules.';
  end if;
  select * into v_req from public.approval_requests where id = p_request_id for update;
  if not found or v_req.submission_type <> 'exam_schedule' then
    raise exception 'Exam schedule submission % not found', p_request_id;
  end if;
  if v_req.approval_status <> 'pending' then
    raise exception 'Exam schedule submission % is not pending (status=%)', p_request_id, v_req.approval_status;
  end if;
  if not p_approve then
    update public.approval_requests set approval_status = 'rejected', rejection_reason = p_rejection_reason,
           reviewed_by = auth.uid(), reviewed_at = now() where id = p_request_id;
    insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
    values (auth.uid(), 'exam_schedule_rejected', 'approval_requests', p_request_id::text,
            jsonb_build_object('submitted_by', v_req.submitted_by, 'rejection_reason', p_rejection_reason));
    return jsonb_build_object('success', true, 'id', p_request_id, 'status', 'rejected');
  end if;

  v_cls  := v_req.payload->'class';
  v_type := v_req.payload->>'exam_type';
  v_sem  := (v_cls->>'semester')::integer;
  select array_agg(distinct coalesce(e->>'department', v_cls->>'department'))
    into v_depts from jsonb_array_elements(v_req.payload->'entries') e;

  update public.exams set status = 'superseded'
   where status = 'active' and semester = v_sem and exam_type = v_type and department = any (v_depts);
  get diagnostics v_old = row_count;

  for v_e in select * from jsonb_array_elements(v_req.payload->'entries') loop
    v_n := v_n + 1;
    insert into public.exams (course_id, exam_type, exam_date, start_time, end_time, semester, batch, programme,
                              department, course_code, course_name, alt_group, notes, valid_from, valid_until,
                              status, source_id, approved_at, approved_by)
    values (
      (select id from public.courses where upper(replace(course_code, ' ', '')) = upper(replace(v_e->>'course_code', ' ', '')) limit 1),
      v_type, (v_e->>'exam_date')::date, (v_e->>'start_time')::time, (v_e->>'end_time')::time, v_sem, null,
      coalesce(v_cls->>'programme', 'B.Tech'), coalesce(v_e->>'department', v_cls->>'department'),
      upper(v_e->>'course_code'), v_e->>'course_name', nullif(v_e->>'alt_group', ''), left(v_e->>'notes', 300),
      current_date, (v_e->>'exam_date')::date, 'active', 'exam_submission:' || p_request_id, now(), auth.uid()
    );
  end loop;

  update public.approval_requests set approval_status = 'approved', rejection_reason = null,
         reviewed_by = auth.uid(), reviewed_at = now(), published_at = now() where id = p_request_id;
  insert into public.audit_logs (actor_id, action, entity_type, entity_id, old_data, new_data, metadata)
  values (auth.uid(), 'exam_schedule_approved', 'approval_requests', p_request_id::text,
          jsonb_build_object('superseded', v_old),
          jsonb_build_object('inserted', v_n, 'semester', v_sem, 'exam_type', v_type, 'departments', v_depts,
                             'submitted_by', v_req.submitted_by),
          jsonb_build_object('source_file_path', v_req.source_file_path));
  return jsonb_build_object('success', true, 'id', p_request_id, 'status', 'approved', 'inserted', v_n, 'superseded', v_old);
end;
$$;
revoke execute on function public.review_exam_schedule(bigint, boolean, text) from public, anon;
grant execute on function public.review_exam_schedule(bigint, boolean, text) to authenticated;

-- ============================================================ class changes

create table if not exists public.class_changes (
  id bigint generated always as identity primary key,
  semester smallint not null,
  programme text not null default 'B.Tech',
  department text not null,
  batch text,
  section text,
  change_type text not null check (change_type in ('cancel', 'reschedule', 'extra')),
  change_date date not null,
  course_code text,
  course_name text,
  original_start time,
  original_end time,
  new_date date,
  new_start time,
  new_end time,
  note text,
  announcement_id bigint references public.announcements(id) on delete set null,
  status text not null default 'active' check (status in ('active', 'archived')),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  check (change_type <> 'reschedule' or (new_date is not null and new_start is not null and new_end is not null)),
  check (change_type <> 'extra' or (new_start is not null and new_end is not null)),
  check (new_start is null or new_end is null or new_end > new_start)
);
create index if not exists class_changes_scope_idx on public.class_changes (semester, department, change_date);

alter table public.class_changes enable row level security;
drop policy if exists class_changes_select on public.class_changes;
create policy class_changes_select on public.class_changes for select to authenticated
  using (status = 'active' or public.is_admin() or created_by = (select auth.uid()));
drop policy if exists class_changes_insert on public.class_changes;
create policy class_changes_insert on public.class_changes for insert to authenticated
  with check (
    created_by = (select auth.uid())
    and status = 'active'
    and change_date between current_date - 1 and current_date + 90
    and (
      public.is_admin()
      or (
        (select p.role from public.profiles p where p.id = (select auth.uid())) = 'CR'
        and exists (select 1 from public.student_profiles sp
                     where sp.user_id = (select auth.uid()) and sp.semester = class_changes.semester
                       and sp.department = class_changes.department
                       and sp.section is not distinct from class_changes.section)
      )
    )
  );
drop policy if exists class_changes_update on public.class_changes;
create policy class_changes_update on public.class_changes for update to authenticated
  using (public.is_admin()) with check (public.is_admin());
revoke all on public.class_changes from anon;
grant select, insert, update on public.class_changes to authenticated;

-- A class-update notice and the changes it announces, in one transaction.
-- SECURITY INVOKER: the announcements and class_changes insert policies
-- decide what is allowed, exactly as for a direct insert.
create or replace function public.post_class_update(p_announcement jsonb, p_changes jsonb)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_uid uuid := auth.uid();
  v_id  bigint;
  v_c   jsonb;
  v_n   integer := 0;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;
  if jsonb_typeof(p_changes) is distinct from 'array' or jsonb_array_length(p_changes) = 0 then
    raise exception 'A class update needs at least one change.';
  end if;
  insert into public.announcements (title, content, category, semester, programme, department, batch, section,
                                    event_date, event_time, status, auto_published, submitted_by, published_at,
                                    valid_until, source_kind, source_file_path, approved_by, approved_at)
  values (p_announcement->>'title', p_announcement->>'content', 'CLASS_UPDATE',
          (p_announcement->>'semester')::smallint, p_announcement->>'programme', p_announcement->>'department',
          p_announcement->>'batch', p_announcement->>'section', (p_announcement->>'event_date')::date,
          (p_announcement->>'event_time')::time, 'active', (p_announcement->>'auto_published')::boolean, v_uid, now(),
          (p_announcement->>'valid_until')::timestamptz, p_announcement->>'source_kind', p_announcement->>'source_file_path',
          case when public.is_admin() then v_uid end, case when public.is_admin() then now() end)
  returning id into v_id;
  for v_c in select * from jsonb_array_elements(p_changes) loop
    insert into public.class_changes (semester, programme, department, batch, section, change_type, change_date,
                                      course_code, course_name, original_start, original_end, new_date, new_start,
                                      new_end, note, announcement_id, created_by)
    values ((p_announcement->>'semester')::smallint, coalesce(p_announcement->>'programme', 'B.Tech'),
            p_announcement->>'department', p_announcement->>'batch', p_announcement->>'section',
            v_c->>'change_type', (v_c->>'change_date')::date, nullif(v_c->>'course_code', ''), v_c->>'course_name',
            nullif(v_c->>'original_start', '')::time, nullif(v_c->>'original_end', '')::time,
            nullif(v_c->>'new_date', '')::date, nullif(v_c->>'new_start', '')::time, nullif(v_c->>'new_end', '')::time,
            left(v_c->>'note', 300), v_id, v_uid);
    v_n := v_n + 1;
  end loop;
  return jsonb_build_object('success', true, 'id', v_id, 'changes', v_n);
end;
$$;
revoke execute on function public.post_class_update(jsonb, jsonb) from public, anon;
grant execute on function public.post_class_update(jsonb, jsonb) to authenticated;

create or replace function public.audit_class_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.audit_logs (actor_id, action, entity_type, entity_id, new_data)
  values (new.created_by, 'class_change_' || case when tg_op = 'INSERT' then 'posted' else 'updated' end,
          'class_changes', new.id::text,
          jsonb_build_object('change_type', new.change_type, 'change_date', new.change_date, 'course_code', new.course_code,
                             'semester', new.semester, 'department', new.department, 'section', new.section,
                             'new_date', new.new_date, 'new_start', new.new_start, 'status', new.status));
  return new;
end;
$$;
revoke execute on function public.audit_class_change() from public, anon, authenticated;
drop trigger if exists class_changes_audit on public.class_changes;
create trigger class_changes_audit after insert or update on public.class_changes
  for each row execute function public.audit_class_change();

-- Taking a notice down also withdraws the class changes it announced.
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
  update public.announcements set status = 'archived', rejection_reason = p_reason, updated_at = now() where id = p_id;
  update public.class_changes set status = 'archived' where announcement_id = p_id and status = 'active';
  insert into public.audit_logs (actor_id, action, entity_type, entity_id, old_data, new_data)
  values (auth.uid(), 'announcement_taken_down', 'announcements', p_id::text,
          jsonb_build_object('status', v_row.status, 'title', v_row.title, 'submitted_by', v_row.submitted_by,
                             'auto_published', v_row.auto_published),
          jsonb_build_object('status', 'archived', 'reason', p_reason));
  return jsonb_build_object('success', true, 'id', p_id, 'status', 'archived');
end;
$$;

-- ============================================= CR notices: own class only

drop policy if exists cr_admin_insert_announcements on public.announcements;
create policy cr_admin_insert_announcements on public.announcements
  for insert
  with check (
    submitted_by = (select auth.uid())
    and (
      public.is_admin()
      or (
        (select p.role from public.profiles p where p.id = (select auth.uid())) = 'CR'
        -- every CR notice, pending or live, is for exactly the CR's own class
        and exists (
          select 1 from public.student_profiles sp
          where sp.user_id = (select auth.uid())
            and sp.semester = announcements.semester
            and sp.department = announcements.department
            and sp.batch is not distinct from announcements.batch
            and sp.section is not distinct from announcements.section
        )
        and (
          (status = 'pending' and not auto_published)
          or (
            status = 'active'
            and auto_published
            and public.orion_is_academic_category(category)
            and valid_until is not null
            and valid_until <= now() + interval '62 days'
          )
        )
      )
    )
  );

-- ======================================================= approval requests

drop policy if exists cr_submit_approvals on public.approval_requests;
create policy cr_submit_approvals on public.approval_requests
  for insert to authenticated
  with check (
    (select auth.uid()) = submitted_by
    and approval_status = 'pending'
    and (
      submission_type = 'cr_access_request'
      or (
        submission_type in ('timetable_update', 'exam_schedule')
        and (select p.role from public.profiles p where p.id = (select auth.uid())) in ('CR', 'ADMIN')
      )
    )
  );
