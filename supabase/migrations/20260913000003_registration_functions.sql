-- ORION — registration completion + single-round-trip profile fetch
--
-- Correction from the plan draft: `batch` in this schema is a Roman-numeral
-- section identifier ("I"/"II"/"III", verified against live
-- student_profiles rows), not an admission-year range — cohort cannot be
-- derived from it. complete_registration() takes an explicit
-- p_admission_year instead of guessing one out of p_batch.

create or replace function public.complete_registration(
  p_full_name      text,
  p_semester       smallint,
  p_department     text,
  p_batch          text,
  p_section        text,
  p_admission_year integer,
  p_programme      text default 'B.Tech'
)
returns jsonb
language plpgsql
security invoker
set search_path to 'public'
as $$
declare
  v_uid    uuid := auth.uid();
  v_cohort text;
begin
  if v_uid is null then
    raise exception 'Not authenticated';
  end if;

  if trim(p_full_name) = '' then
    raise exception 'full_name is required';
  end if;

  if p_semester not between 1 and 8 then
    raise exception 'semester must be 1-8, got %', p_semester;
  end if;

  v_cohort := case
    when p_admission_year >= 2026 then '2026_onwards'
    else '2021_2025'
  end;

  -- profiles keeps only full_name (identity); academic context lives
  -- solely in student_profiles (see migration 20260913000001's column drop).
  update public.profiles set
    full_name  = trim(p_full_name),
    updated_at = now()
  where id = v_uid;

  if not found then
    raise exception 'Profile not found for %. Signup trigger may have failed.', v_uid;
  end if;

  insert into public.student_profiles (
    user_id, display_name, semester, programme,
    department, batch, section, cohort
  )
  values (
    v_uid, trim(p_full_name), p_semester, p_programme,
    p_department, p_batch, p_section, v_cohort
  )
  on conflict (user_id) do update set
    display_name = excluded.display_name,
    semester     = excluded.semester,
    programme    = excluded.programme,
    department   = excluded.department,
    batch        = excluded.batch,
    section      = excluded.section,
    cohort       = excluded.cohort,
    updated_at   = now();

  return jsonb_build_object('success', true, 'cohort', v_cohort);
end;
$$;

-- get_my_profile(): single round-trip on app load. onboarded/pending_cr_request
-- are computed, not stored (design decision D1) — no student_profiles row
-- means not onboarded yet; a pending approval_requests row of type
-- cr_access_request means a request is in flight.
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

  select id, full_name, email, role, created_at
  into v_profile
  from public.profiles
  where id = v_uid;

  if not found then
    return jsonb_build_object('error', 'profile_not_found');
  end if;

  select display_name, programme, cohort, department, semester, batch, section
  into v_student
  from public.student_profiles
  where user_id = v_uid;

  v_onboarded := found;

  select exists (
    select 1 from public.approval_requests
    where submitted_by = v_uid
      and submission_type = 'cr_access_request'
      and approval_status = 'pending'
  ) into v_pending;

  return jsonb_build_object(
    'id',                 v_profile.id,
    'full_name',          v_profile.full_name,
    'email',               v_profile.email,
    'role',                v_profile.role,
    'onboarded',           v_onboarded,
    'pending_cr_request',  v_pending,
    'department',          v_student.department,
    'semester',            v_student.semester,
    'batch',               v_student.batch,
    'section',             v_student.section,
    'display_name',        v_student.display_name,
    'programme',           v_student.programme,
    'cohort',              v_student.cohort
  );
end;
$$;
