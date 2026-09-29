-- Two linked bugs, both of which silently give a student an EMPTY timetable.
--
-- 1. The same department is spelled differently in every semester's PDF, and
--    the timetable RPCs compare `student_profiles.department` to
--    `timetable_entries.department` with exact `=`. Measured live 2026-09-29:
--      sem 3  CSE WITH SPECIALISATION IN AI AND DATA SCIENCE
--      sem 5  AI AND DATA SCIENCE
--      sem 7  CSE WITH SPECIALIZATION IN AI & DATA SCIENCE
--    so an AI&DS student matches their own semester and then gets nothing at
--    all the moment they roll over to the next one. Same for Cyber Security
--    (sem 3 "CSE WITH SPECIALISATION IN CYBER SECURITY" vs sem 5 "CYBER
--    SECURITY"), and sem-5 Cyber prints its section as arabic '1' while every
--    other row uses roman 'I'.
--
--    We do NOT rewrite timetable_entries.department to fix this: `source_uid`
--    (backend/timetable/model.py) embeds the branch string, so rewriting the
--    column would change every natural key and a re-import of the same PDF
--    would insert 1,263 duplicates instead of upserting. Match on a canonical
--    key instead — same idea as dept_key() in backend/cr_ingest/exam_draft.py,
--    which this mirrors deliberately so Python and SQL agree.
--
-- 2. Department and batch were whatever the student picked in a dropdown.
--    The institute already encodes both in the roll number (2024BCS0086 =
--    2024 intake, BCS = CSE, serial 86), and batch is serial % 4 + 1, so
--    complete_registration now derives them server-side instead of trusting
--    the form. Verified against the real rows: ...bcs86 -> 86%4=2 -> batch 3
--    -> section III, which is exactly what that student already has.

-- ---------------------------------------------------------------- keys

create or replace function public.orion_dept_key(p_name text)
returns text
language sql
immutable
parallel safe
set search_path = public
as $$
  -- Mirrors backend/cr_ingest/exam_draft.py::dept_key. Order matters: the
  -- specialisation names contain "CSE" too, so CYBER/AI&DS must win first.
  select case
    when n like '%CYBER%' or n ~ '\mCSY\M'                                   then 'cyber'
    when (n like '%DATA%' and n ~ '\mAI\M|ARTIFICIAL')
         or n like '%AIDS%' or replace(n, ' ', '') like '%AI&DS%'            then 'aids'
    when n like '%ELECTRONICS%' or n ~ '\mECE\M'                             then 'ece'
    when n like '%COMPUTER SCIENCE%' or btrim(n) = 'CSE'                     then 'cse'
    when n like '%MATHEMATIC%'                                               then 'maths'
    else btrim(regexp_replace(lower(n), '[^a-z]+', ' ', 'g'))
  end
  from (select upper(coalesce(p_name, '')) as n) s;
$$;

comment on function public.orion_dept_key(text) is
  'One key per department however it is spelled, so timetable rows written by different semesters'' PDFs still match one student.';

create or replace function public.orion_section_key(p_section text)
returns text
language sql
immutable
parallel safe
set search_path = public
as $$
  -- Sections are the same thing written two ways ('III' vs '3').
  select case upper(btrim(coalesce(p_section, '')))
    when 'I'   then '1' when 'II'  then '2' when 'III' then '3'
    when 'IV'  then '4' when 'V'   then '5'
    else upper(btrim(coalesce(p_section, '')))
  end;
$$;

create or replace function public.orion_dept_label(p_key text)
returns text
language sql
immutable
parallel safe
set search_path = public
as $$
  -- The one spelling we show and store going forward.
  select case p_key
    when 'cse'   then 'COMPUTER SCIENCE AND ENGINEERING'
    when 'aids'  then 'CSE WITH SPECIALISATION IN AI AND DATA SCIENCE'
    when 'cyber' then 'CSE WITH SPECIALISATION IN CYBER SECURITY'
    when 'ece'   then 'ELECTRONICS AND COMMUNICATION ENGINEERING'
    when 'maths' then 'MATHEMATICS'
    else upper(coalesce(p_key, ''))
  end;
$$;

create or replace function public.orion_section_label(p_key text)
returns text
language sql
immutable
parallel safe
set search_path = public
as $$
  select case public.orion_section_key(p_key)
    when '1' then 'I' when '2' then 'II' when '3' then 'III'
    when '4' then 'IV' when '5' then 'V'
    else upper(btrim(coalesce(p_key, '')))
  end;
$$;

-- Roll number -> the class it encodes. Null when it isn't a roll number we
-- understand, so callers can fall back instead of guessing.
create or replace function public.orion_parse_roll(p_roll text)
returns jsonb
language sql
immutable
parallel safe
set search_path = public
as $$
  select case
    when m is null then null
    when branch_key is null then null
    else jsonb_build_object(
      'admission_year', (m[1])::int,
      'branch_code',    m[2],
      'serial',         (m[3])::int,
      'dept_key',       branch_key,
      'department',     public.orion_dept_label(branch_key),
      -- serial 86 -> 86 % 4 = 2 -> batch 3. Batches are 1-4.
      'batch_no',       ((m[3])::int % 4) + 1,
      'section',        public.orion_section_label((((m[3])::int % 4) + 1)::text)
    )
  end
  from (
    select m, case m[2]
      when 'BCS' then 'cse'
      when 'BCD' then 'aids'
      when 'BCY' then 'cyber'
      when 'BEC' then 'ece'
      else null
    end as branch_key
    from (
      select regexp_match(upper(btrim(coalesce(p_roll, ''))), '^(20[0-9]{2})(B[A-Z]{2})([0-9]{1,4})$') as m
    ) r
  ) b;
$$;

comment on function public.orion_parse_roll(text) is
  'e.g. 2024BCS0086 -> {admission_year 2024, dept CSE, batch_no 3, section III}. Null if the format or branch code is unknown.';

-- ------------------------------------------------- timetable matching

-- Same bodies as 20260921000004_timetable_ist_timezone_fix.sql (IST pinning
-- preserved verbatim) with the department/section comparisons swapped for
-- key comparisons. `batch` is no longer compared at all: on this campus it
-- holds the same roman label as `section` (normalizer.py sets section=batch),
-- and it is the column most likely to carry a stale spelling, so comparing it
-- a second time only adds ways to match nothing.

create or replace function public.orion_active_entries(
  p_semester  smallint,
  p_department text,
  p_batch     text,
  p_section   text,
  p_on_date   date default ((now() at time zone 'Asia/Kolkata')::date)
)
returns jsonb
language sql stable
security invoker
set search_path = public
as $$
  select coalesce(
    jsonb_agg(public.orion_entry_json(e) order by e.day_of_week, e.start_time nulls last),
    '[]'::jsonb)
  from public.timetable_entries e
  where e.semester = p_semester
    and public.orion_dept_key(e.department) = public.orion_dept_key(p_department)
    and public.orion_section_key(e.section) = public.orion_section_key(coalesce(p_section, p_batch))
    and e.status = 'active'
    and e.valid_from <= p_on_date
    and e.valid_until >= p_on_date
    and e.day_of_week = extract(isodow from p_on_date)::smallint
    and e.entry_type <> 'break'
$$;

create or replace function public.orion_next_class(
  p_user_id uuid default null,
  p_at timestamptz default now(),
  p_include_activities boolean default false
)
returns jsonb
language plpgsql stable
security invoker
set search_path = public
as $$
declare
  v_user uuid := public.orion_resolve_user(p_user_id);
  v_profile public.student_profiles%rowtype;
  v_day smallint;
  v_time time;
  v_entry public.timetable_entries%rowtype;
begin
  if v_user is null then
    return null;
  end if;
  select * into v_profile from public.student_profiles where user_id = v_user;
  if not found then
    return null;
  end if;

  -- Wall-clock schedule comparisons pinned to Asia/Kolkata (IST).
  v_day := extract(isodow from (p_at at time zone 'Asia/Kolkata'))::smallint;
  v_time := (p_at at time zone 'Asia/Kolkata')::time;

  -- Day-offset occurrence model:
  --   0     today, still ongoing (end_time > now — ongoing classes count)
  --   1..6  later this week
  --   7     same weekday already ended -> next week (wrap)
  -- Validity is checked against the OCCURRENCE date, not p_at::date.
  select e.* into v_entry
  from public.timetable_entries e
  where e.semester = v_profile.semester
    and public.orion_dept_key(e.department) = public.orion_dept_key(v_profile.department)
    and public.orion_section_key(e.section)
        = public.orion_section_key(coalesce(v_profile.section, v_profile.batch))
    and e.status = 'active'
    and e.entry_type <> 'break'
    and (p_include_activities or e.entry_type not in ('sports', 'club_activity'))
    and (
      (p_at at time zone 'Asia/Kolkata')::date
      + case
          when e.day_of_week = v_day and e.end_time > v_time then 0
          else ((e.day_of_week - v_day + 6)::int % 7) + 1
        end
    ) between e.valid_from and e.valid_until
  order by
    case
      when e.day_of_week = v_day and e.end_time > v_time then 0
      else ((e.day_of_week - v_day + 6)::int % 7) + 1
    end,
    e.start_time
  limit 1;

  if not found then
    return null;
  end if;
  return public.orion_entry_json(v_entry);
end;
$$;

create or replace function public.orion_day_timetable(
  p_user_id uuid default null,
  p_on_date date default ((now() at time zone 'Asia/Kolkata')::date)
)
returns jsonb
language plpgsql stable
security invoker
set search_path = public
as $$
declare
  v_user uuid := public.orion_resolve_user(p_user_id);
  v_profile public.student_profiles%rowtype;
begin
  if v_user is null then
    return '[]'::jsonb;
  end if;
  select * into v_profile from public.student_profiles where user_id = v_user;
  if not found then
    return '[]'::jsonb;
  end if;
  return public.orion_active_entries(
    v_profile.semester, v_profile.department, v_profile.batch, v_profile.section, p_on_date
  );
end;
$$;

create or replace function public.orion_week_timetable(
  p_user_id uuid default null,
  p_on_date date default ((now() at time zone 'Asia/Kolkata')::date)
)
returns jsonb
language plpgsql stable
security invoker
set search_path = public
as $$
declare
  v_user uuid := public.orion_resolve_user(p_user_id);
  v_profile public.student_profiles%rowtype;
  v_monday date;
begin
  if v_user is null then
    return '[]'::jsonb;
  end if;
  select * into v_profile from public.student_profiles where user_id = v_user;
  if not found then
    return '[]'::jsonb;
  end if;
  v_monday := p_on_date - (extract(isodow from p_on_date)::int - 1);

  return coalesce(
    jsonb_agg(public.orion_entry_json(e) order by e.day_of_week, e.start_time nulls last),
    '[]'::jsonb)
  from public.timetable_entries e
  where e.semester = v_profile.semester
    and public.orion_dept_key(e.department) = public.orion_dept_key(v_profile.department)
    and public.orion_section_key(e.section)
        = public.orion_section_key(coalesce(v_profile.section, v_profile.batch))
    and e.status = 'active'
    and e.valid_from <= v_monday + 6
    and e.valid_until >= v_monday
    and e.entry_type <> 'break';
end;
$$;

-- ------------------------------------------------- registration

-- One row per real class, with the canonical spelling, so the dropdown stops
-- offering the same department three times under three names.
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
    select distinct
           coalesce(programme, 'B.Tech')                   as programme,
           semester,
           public.orion_dept_label(public.orion_dept_key(department)) as department,
           public.orion_section_label(section)             as section
      from public.timetable_entries
     where status = 'active' and semester is not null and department is not null and section is not null
  ) c;
$$;

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
  v_parsed jsonb;
  v_department text;
  v_section    text;
  v_admission  integer := p_admission_year;
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
  if v_roll is not null and v_roll !~ '^[A-Z0-9]{6,15}$' then
    raise exception 'Roll number should be 6-15 letters and digits (e.g. 2024BCS0066).';
  end if;
  if v_roll is not null and exists (
      select 1 from public.student_profiles where upper(roll_number) = v_roll and user_id <> v_uid) then
    raise exception 'That roll number is already registered to another account.';
  end if;

  -- The roll number is the institute's own record of which branch and batch a
  -- student is in, so when it parses it wins over anything the form sent.
  v_parsed := public.orion_parse_roll(v_roll);
  if v_parsed is not null then
    v_department := v_parsed ->> 'department';
    v_section    := v_parsed ->> 'section';
    v_admission  := (v_parsed ->> 'admission_year')::int;
  else
    v_department := public.orion_dept_label(public.orion_dept_key(p_department));
    v_section    := public.orion_section_label(coalesce(nullif(p_section, ''), p_batch));
  end if;

  if v_admission is null or v_admission < 2015 or v_admission > v_year then
    raise exception 'Admission year must be between 2015 and %.', v_year;
  end if;
  if coalesce(v_department, '') = '' then
    raise exception 'department is required';
  end if;
  if coalesce(v_section, '') = '' then
    raise exception 'section is required';
  end if;

  v_cohort := case when v_admission >= 2026 then '2026_onwards' else '2021_2025' end;

  update public.profiles set full_name = trim(p_full_name), updated_at = now() where id = v_uid;
  if not found then
    raise exception 'Profile not found for %. Signup trigger may have failed.', v_uid;
  end if;

  insert into public.student_profiles (
    user_id, display_name, semester, programme, department, batch, section, cohort, roll_number, admission_year
  ) values (
    v_uid, trim(p_full_name), p_semester, coalesce(p_programme, 'B.Tech'), v_department,
    v_section, v_section, v_cohort, v_roll, v_admission
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

  return jsonb_build_object(
    'success', true, 'cohort', v_cohort,
    'department', v_department, 'section', v_section, 'admission_year', v_admission,
    'derived_from_roll', v_parsed is not null
  );
end;
$$;

revoke execute on function public.complete_registration(text, smallint, text, text, text, integer, text, text) from public, anon;
grant execute on function public.complete_registration(text, smallint, text, text, text, integer, text, text) to authenticated;

-- --------------------------------------------------------- backfill

-- Canonicalise what is already stored. This only rewrites spelling: where a
-- roll number is present the class is re-derived from it, otherwise the
-- existing department/section are mapped onto the canonical vocabulary
-- ('CSE' -> COMPUTER SCIENCE AND ENGINEERING, 'AI & DATA SCIENCE' -> the
-- AI&DS label, section '3' -> 'III'). No class is invented.
update public.student_profiles sp
set department = coalesce(p.derived_department, p.canonical_department),
    section    = coalesce(p.derived_section, p.canonical_section),
    batch      = coalesce(p.derived_section, p.canonical_section),
    admission_year = coalesce(p.derived_year, sp.admission_year),
    updated_at = now()
from (
  select user_id,
         (public.orion_parse_roll(roll_number) ->> 'department')          as derived_department,
         (public.orion_parse_roll(roll_number) ->> 'section')             as derived_section,
         (public.orion_parse_roll(roll_number) ->> 'admission_year')::int as derived_year,
         public.orion_dept_label(public.orion_dept_key(department))       as canonical_department,
         public.orion_section_label(coalesce(nullif(section, ''), batch)) as canonical_section
  from public.student_profiles
) p
where sp.user_id = p.user_id
  and (sp.department is distinct from coalesce(p.derived_department, p.canonical_department)
       or sp.section is distinct from coalesce(p.derived_section, p.canonical_section)
       or sp.batch   is distinct from coalesce(p.derived_section, p.canonical_section));
