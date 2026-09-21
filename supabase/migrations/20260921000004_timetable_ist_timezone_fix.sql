-- The printed timetable's start_time/end_time/day are institute-local
-- (Asia/Kolkata, IST, UTC+5:30) wall-clock values, not UTC. The previous
-- definitions explicitly converted `now()`/`p_at` to UTC wall-clock before
-- comparing against those stored times — found live: at 07:04 UTC (which
-- is 12:34 PM IST), a 09:30-10:25 class that had already ended almost two
-- hours earlier was still being returned as the "next" class, because
-- 07:04 < 09:30 in raw UTC digits even though the real local time was
-- already well past 10:25. Same issue for `current_date` (session
-- timezone, not necessarily IST) as the default "today" for day/week
-- timetable lookups. Fix: convert to 'Asia/Kolkata' everywhere a wall-
-- clock comparison or a default "today" is computed.

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
    and e.department = p_department
    and e.batch = p_batch
    and e.section = p_section
    and e.status = 'active'
    and e.valid_from <= p_on_date
    and e.valid_until >= p_on_date
    -- the timetable is a weekly recurring schedule: "on a date" means that
    -- date's weekday, not every entry whose validity window covers the date
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

  -- Wall-clock schedule comparisons pinned to Asia/Kolkata (IST) — see
  -- migration header for why UTC was wrong here.
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
    and e.department = v_profile.department
    and e.batch = v_profile.batch
    and e.section = v_profile.section
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
    and e.department = v_profile.department
    and e.batch = v_profile.batch
    and e.section = v_profile.section
    and e.status = 'active'
    and e.valid_from <= v_monday + 6
    and e.valid_until >= v_monday
    and e.entry_type <> 'break';
end;
$$;

comment on function public.orion_next_class(uuid, timestamptz, boolean) is
  'Next valid class for the resolved user: ongoing counts, rolls to later days, wraps to next week; validity per occurrence date; breaks always excluded; activities opt-in. Wall-clock comparisons pinned to Asia/Kolkata (IST).';
