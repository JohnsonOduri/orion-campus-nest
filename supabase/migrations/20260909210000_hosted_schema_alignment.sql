-- ORION — Hosted schema alignment for the timetable vertical slice.
--
-- The hosted project already contains faculty / courses / rooms /
-- timetable_entries (all empty at migration time). This script ADDS only what
-- the documented timetable pipeline genuinely requires (AGENTS.md §14:
-- version-controlled migration, never manual schema edits).
--
-- IDEMPOTENT: safe to run multiple times (SQL Editor → paste → run).
-- ADDITIVE: no existing column is dropped, renamed, or retyped.
--
-- Summary of changes:
--   1. timetable_entries: + source_uid (idempotency natural key),
--      + source_page / source_text / lab_batch (audit + authoritative data),
--      start_time/end_time made nullable (Saturday full-grid activities print
--      no period times; we refuse to fabricate them — AGENTS.md §6).
--   2. faculty: unique index on initials (upsert arbiter for ingestion).
--   3. courses: unique index on course_code (upsert arbiter).
--   4. timetable_entry_faculty: co-faculty join (cells like "DSL/ SSJ").
--   5. timetable_periods: period definitions per source (never hard-coded).
--   6. student_profiles: academic context (hosted naming: department).
--   7. ingestion_runs: audit trail (AGENTS.md §28).
--   8. orion_* RPC functions: identity rule preserved (auth.uid() wins;
--      p_user_id only for service_role/orion_admin), security invoker.

-- ---------------------------------------------------------------------------
-- 1. timetable_entries: idempotency key + audit columns
-- ---------------------------------------------------------------------------
alter table public.timetable_entries add column if not exists source_uid  text;
alter table public.timetable_entries add column if not exists source_page smallint;
alter table public.timetable_entries add column if not exists source_text text;
alter table public.timetable_entries add column if not exists lab_batch   smallint;

-- Saturday merged "Sports/Yoga/Cultural Activities" rows are full-day grid
-- cells with NO printed start/end time. Keeping these NOT NULL would force
-- fabricated times; the authoritative source has none.
alter table public.timetable_entries alter column start_time drop not null;
alter table public.timetable_entries alter column end_time   drop not null;

do $$ begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'timetable_entries_source_uid_key'
      and conrelid = 'public.timetable_entries'::regclass
  ) then
    alter table public.timetable_entries
      add constraint timetable_entries_source_uid_key unique (source_uid);
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- 2/3. Natural-key unique indexes (PostgREST upsert arbiters)
-- ---------------------------------------------------------------------------
create unique index if not exists faculty_initials_key
  on public.faculty (initials);
create unique index if not exists courses_course_code_key
  on public.courses (course_code);

-- ---------------------------------------------------------------------------
-- 4. Co-faculty join (28 co-taught cells in the S3 source, e.g. DSL/ SSJ)
-- ---------------------------------------------------------------------------
create table if not exists public.timetable_entry_faculty (
  entry_id   bigint not null references public.timetable_entries(id) on delete cascade,
  faculty_id bigint not null references public.faculty(id)        on delete cascade,
  ord        smallint not null default 0,
  primary key (entry_id, faculty_id)
);

-- ---------------------------------------------------------------------------
-- 5. timetable_periods: printed period definitions per source document
-- ---------------------------------------------------------------------------
create table if not exists public.timetable_periods (
  id              bigint generated always as identity primary key,
  source_id       text not null,
  slot_index      smallint not null,
  start_time      time,
  end_time        time,
  kind            text not null default 'teaching'
                  check (kind in ('teaching', 'break')),
  is_time_derived boolean not null default false,
  source_page     smallint,
  created_at      timestamptz not null default now()
);

comment on table public.timetable_periods is
  'Period definitions extracted from each timetable source. Slots 8/9 of the S3 source share the printed 5.00-7.00 PM range (is_time_derived = true). Reconciled in application code (fetch -> diff), not expression indexes.';

create index if not exists timetable_periods_source_idx
  on public.timetable_periods (source_id);

-- ---------------------------------------------------------------------------
-- 6. student_profiles: academic context (hosted naming: department)
-- ---------------------------------------------------------------------------
create table if not exists public.student_profiles (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  semester     smallint not null,
  programme    text not null default 'B.Tech',
  department   text not null,
  batch        text,
  section      text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

comment on table public.student_profiles is
  'Academic context per student. Never accepted from client input (AGENTS.md §7); queries resolve the authenticated user via orion_resolve_user.';

-- ---------------------------------------------------------------------------
-- 7. ingestion_runs: audit trail
-- ---------------------------------------------------------------------------
create table if not exists public.ingestion_runs (
  id                  uuid primary key default gen_random_uuid(),
  source_id           text not null,
  started_at          timestamptz not null default now(),
  finished_at         timestamptz,
  status              text not null check (status in ('dry_run','validated','imported','failed')),
  stats               jsonb not null default '{}',
  validation_errors   integer not null default 0,
  validation_warnings integer not null default 0,
  imported_by         text,
  approved_by         text
);

comment on table public.ingestion_runs is
  'Audit log of timetable ingestion runs: who approved, what was imported, when.';

create index if not exists ingestion_runs_source_idx
  on public.ingestion_runs (source_id, started_at desc);

-- ---------------------------------------------------------------------------
-- 8. Query-pattern indexes
-- ---------------------------------------------------------------------------
create index if not exists timetable_entries_import_ctx_idx
  on public.timetable_entries (semester, department, batch, section, day_of_week, start_time);
create index if not exists timetable_entries_validity_idx
  on public.timetable_entries (status, valid_from, valid_until);
create index if not exists timetable_entries_source_idx
  on public.timetable_entries (source_id);
create index if not exists timetable_entry_faculty_faculty_idx
  on public.timetable_entry_faculty (faculty_id);

-- ---------------------------------------------------------------------------
-- 9. Row Level Security (never weakened)
-- ---------------------------------------------------------------------------
alter table public.timetable_periods      enable row level security;
alter table public.timetable_entry_faculty enable row level security;
alter table public.student_profiles       enable row level security;
alter table public.ingestion_runs         enable row level security;

drop policy if exists "authenticated read timetable_periods" on public.timetable_periods;
create policy "authenticated read timetable_periods" on public.timetable_periods
  for select to authenticated using (true);

drop policy if exists "authenticated read timetable_entry_faculty" on public.timetable_entry_faculty;
create policy "authenticated read timetable_entry_faculty" on public.timetable_entry_faculty
  for select to authenticated using (true);

drop policy if exists "students read own profile" on public.student_profiles;
create policy "students read own profile" on public.student_profiles
  for select to authenticated using (auth.uid() = user_id);

-- ingestion_runs: intentionally NO policies (service-role/audit only).

-- ---------------------------------------------------------------------------
-- 10. Timetable query functions — hosted naming + FK composition.
--
-- IDENTITY RULE (AGENTS.md §7) — non-negotiable:
--   * anon/authenticated callers are ALWAYS auth.uid(); a client-supplied
--     p_user_id is IGNORED (no cross-student impersonation);
--   * explicit p_user_id honored only for service_role / orion_admin;
--   * security invoker: RLS still applies to the calling role.
-- ---------------------------------------------------------------------------

create or replace function public.orion_resolve_user(
  p_user_id uuid default null
)
returns uuid
language plpgsql stable
security invoker
set search_path = public
as $$
begin
  if p_user_id is not null
     and (
       current_setting('request.jwt.claims', true)::jsonb->>'role' in ('service_role', 'orion_admin')
     ) then
    return p_user_id;
  end if;
  return auth.uid();
end;
$$;

-- Compose the API-facing JSON for one entry row (course/faculty/room via FKs).
create or replace function public.orion_entry_json(v_entry public.timetable_entries)
returns jsonb
language sql stable
security invoker
set search_path = public
as $$
  select to_jsonb(v_entry) - 'course_id' - 'faculty_id' - 'room_id'
    || jsonb_build_object(
         'course_code',   c.course_code,
         'course_name',   c.course_name,
         'faculty_names', coalesce(f.names, '{}'::text[]),
         'room',          r.room_no
       )
  from public.timetable_entries e_ref
  left join public.courses c on c.id = v_entry.course_id
  left join public.rooms   r on r.id = v_entry.room_id
  left join lateral (
    select array_agg(fj.full_name order by tef.ord) as names
    from public.timetable_entry_faculty tef
    join public.faculty fj on fj.id = tef.faculty_id
    where tef.entry_id = v_entry.id
  ) f on true
  where e_ref.id = v_entry.id
$$;

create or replace function public.orion_student_context(
  p_user_id uuid default null
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
    return null;
  end if;
  select * into v_profile from public.student_profiles where user_id = v_user;
  if not found then
    return null;
  end if;
  return to_jsonb(v_profile);
end;
$$;

create or replace function public.orion_active_entries(
  p_semester  smallint,
  p_department text,
  p_batch     text,
  p_section   text,
  p_on_date   date default current_date
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

  -- Wall-clock schedule comparisons pinned to UTC (timezone-deterministic).
  v_day := extract(isodow from (p_at at time zone 'utc'))::smallint;
  v_time := (p_at at time zone 'utc')::time;

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
      (p_at at time zone 'utc')::date
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
  p_on_date date default current_date
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
  p_on_date date default current_date
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

comment on function public.orion_resolve_user(uuid) is
  'Identity resolution: anon/authenticated callers are always auth.uid(); client-supplied p_user_id is ignored. Explicit p_user_id only for service_role/orion_admin.';

comment on function public.orion_next_class(uuid, timestamptz, boolean) is
  'Next valid class for the resolved user: ongoing counts, rolls to later days, wraps to next week; validity per occurrence date; breaks always excluded; activities opt-in.';
