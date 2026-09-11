-- ORION — Timetable vertical slice (Semester 3, Odd 2026)
-- Authoritative structured timetable data lives here. NEVER index these rows
-- into the vector store (AGENTS.md §5, §14).
--
-- Conventions:
--   * Natural keys + unique constraints make ingestion idempotent.
--   * Lifecycle metadata on every time-sensitive row (AGENTS.md §13):
--       valid_from, valid_until, status, source_id, approved_at, approved_by
--   * RLS: reads for authenticated users, writes via service role only.
--     Ingestion scripts use SUPABASE_SECRET_KEY (service role) server-side.

-- ---------------------------------------------------------------------------
-- faculty: resolution dictionary for timetable initials (from PDF legends)
-- ---------------------------------------------------------------------------
create table if not exists public.faculty (
  id          uuid primary key default gen_random_uuid(),
  initials    text not null unique,
  full_name   text not null,
  department  text,
  source_id   text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

comment on table public.faculty is
  'Faculty directory. `initials` are the short codes printed in timetable grid cells and legends. Populated from approved timetable PDF legends.';

-- ---------------------------------------------------------------------------
-- courses: authoritative course catalog entries discovered in approved sources
-- ---------------------------------------------------------------------------
create table if not exists public.courses (
  id             uuid primary key default gen_random_uuid(),
  code           text not null unique,
  title          text not null,
  credits_raw    text,
  credits_l      smallint,
  credits_t      smallint,
  credits_p      smallint,
  credits_total  smallint,
  semester       smallint,
  programme      text,
  source_id      text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

comment on table public.courses is
  'Course catalog. One row per course code. credits_raw preserves the source string, e.g. "[3-1-0] 4".';

-- ---------------------------------------------------------------------------
-- rooms: physical rooms/labs (populated by the classroom-details source later)
-- ---------------------------------------------------------------------------
create table if not exists public.rooms (
  id          uuid primary key default gen_random_uuid(),
  room_no     text not null unique,
  room_type   text,
  source_id   text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- timetable_periods: the period/slot definitions extracted from each source
-- PDF. Period times are NOT hard-coded anywhere in ORION; they come from here.
-- ---------------------------------------------------------------------------
create table if not exists public.timetable_periods (
  id              uuid primary key default gen_random_uuid(),
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
  'Period definitions per source document (e.g. slot 1 = 09:00-09:55). break rows are gaps between teaching slots; their times may be derived from neighbouring slots (is_time_derived).';

create index if not exists timetable_periods_source_idx
  on public.timetable_periods (source_id);
-- (Period rows are reconciled in application code: PostgREST upsert cannot
-- target expression indexes, so the repository fetch-then-diffs periods.)
-- The timetable_entries natural key is a plain unique column (source_uid),
-- which PostgREST upserts CAN target — ingestion is idempotent.

-- ---------------------------------------------------------------------------
-- timetable_entries: the authoritative weekly schedule
-- ---------------------------------------------------------------------------
create table if not exists public.timetable_entries (
  id                  uuid primary key default gen_random_uuid(),
  -- deterministic natural key => upsert-idempotent ingestion
  source_uid          text not null unique,
  source_id           text not null,
  source_page         smallint not null,
  day_of_week         smallint not null check (day_of_week between 1 and 7), -- 1=Mon..7=Sun
  slot_index          smallint not null,
  start_time          time not null,
  end_time            time not null,

  course_id           uuid references public.courses(id),
  course_code         text not null,
  course_name         text not null,

  -- first/primary faculty (cells may list co-teachers, e.g. "DSL/ SSJ")
  primary_faculty_id  uuid references public.faculty(id),
  faculty_initials    text[] not null default '{}',
  faculty_names       text[] not null default '{}',

  room_id             uuid references public.rooms(id),
  room                text,

  entry_type          text not null
                      check (entry_type in ('class','lab','tutorial','seminar','project',
                                            'club_activity','sports','break','other')),
  lab_batch           smallint,

  -- academic context (from the source page header, not user input)
  semester            smallint not null,
  programme           text not null,
  branch              text not null,
  batch               text not null,
  section             text not null,

  -- raw cell text for audit/human review
  source_text         text,

  -- lifecycle (AGENTS.md §13)
  valid_from          date not null,
  valid_until         date not null,
  status              text not null default 'active'
                      check (status in ('active','pending_review','archived','rejected')),
  approved_at         timestamptz,
  approved_by         text,

  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

comment on table public.timetable_entries is
  'Authoritative weekly timetable. Rows are only written by the ingestion pipeline after validation + approval. faculty_initials/faculty_names preserve multi-faculty cells; primary_faculty_id is the first listed teacher.';

-- A timetable grid may share one PDF across batches; these columns come from
-- the printed page header (authoritative), never from client input.
create index if not exists timetable_entries_context_idx
  on public.timetable_entries (semester, branch, batch, section, day_of_week, start_time);
create index if not exists timetable_entries_validity_idx
  on public.timetable_entries (status, valid_from, valid_until);
create index if not exists timetable_entries_source_idx
  on public.timetable_entries (source_id);
create index if not exists timetable_entries_course_idx
  on public.timetable_entries (course_id);
create index if not exists timetable_entries_faculty_idx
  on public.timetable_entries (primary_faculty_id);

-- ---------------------------------------------------------------------------
-- student_profiles: academic context used to personalize/authorize timetable
-- queries. user_id references Supabase auth users; never accept this context
-- from client input (AGENTS.md §7).
-- ---------------------------------------------------------------------------
create table if not exists public.student_profiles (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  semester     smallint not null,
  programme    text not null default 'B.Tech',
  branch       text not null,
  batch        text not null,
  section      text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

comment on table public.student_profiles is
  'Academic context per student. Seeded demo profile is for local development only; production rows are created by an onboarding/admin flow.';

-- ---------------------------------------------------------------------------
-- ingestion_runs: audit trail for every pipeline execution (AGENTS.md §28)
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
  'Audit log of timetable ingestion runs: what was extracted, validated, approved and imported, and when.';

create index if not exists ingestion_runs_source_idx
  on public.ingestion_runs (source_id, started_at desc);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.faculty            enable row level security;
alter table public.courses            enable row level security;
alter table public.rooms              enable row level security;
alter table public.timetable_periods  enable row level security;
alter table public.timetable_entries  enable row level security;
alter table public.ingestion_runs     enable row level security;
alter table public.student_profiles   enable row level security;

-- Institutional reference data: readable by any authenticated user.
-- (No INSERT/UPDATE/DELETE policies on purpose: writes go through the
-- service-role ingestion pipeline only.)
drop policy if exists "authenticated read faculty" on public.faculty;
create policy "authenticated read faculty" on public.faculty
  for select to authenticated using (true);

drop policy if exists "authenticated read courses" on public.courses;
create policy "authenticated read courses" on public.courses
  for select to authenticated using (true);

drop policy if exists "authenticated read rooms" on public.rooms;
create policy "authenticated read rooms" on public.rooms
  for select to authenticated using (true);

drop policy if exists "authenticated read timetable_periods" on public.timetable_periods;
create policy "authenticated read timetable_periods" on public.timetable_periods
  for select to authenticated using (true);

drop policy if exists "authenticated read timetable_entries" on public.timetable_entries;
create policy "authenticated read timetable_entries" on public.timetable_entries
  for select to authenticated using (true);

-- Audit log: service role only (no policies => no client access).
-- student_profiles: a student may read only their own profile.
drop policy if exists "students read own profile" on public.student_profiles;
create policy "students read own profile" on public.student_profiles
  for select to authenticated using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- Timetable query functions (single authoritative implementation).
--
-- IDENTITY RULE (AGENTS.md §7) — non-negotiable:
--   * For the anon/public role the caller is ALWAYS auth.uid(). The p_user_id
--     argument is IGNORED for anon/public so a client can never read another
--     student's timetable by passing a UUID.
--   * Explicit p_user_id is honored ONLY when the caller is the service role
--     or holds the app role 'orion_admin' (trusted server-side tooling: the
--     ingestion pipeline, integration tests, admin tooling).
--   * RLS is not weakened: functions are security invoker, so underlying
--     table policies still apply to the invoking role.
-- Validity + status filters implement AGENTS.md §13 (no expired data).
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
  -- Trusted callers (service role / orion_admin) may act on behalf of a user.
  if p_user_id is not null
     and (
       current_setting('request.jwt.claims', true)::jsonb->>'role' in ('service_role', 'orion_admin')
     ) then
    return p_user_id;
  end if;
  -- Everyone else: the JWT wins. Client-supplied ids are ignored.
  return auth.uid();
end;
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
  p_semester smallint,
  p_branch text,
  p_batch text,
  p_section text,
  p_on_date date default current_date
)
returns jsonb
language sql stable
security invoker
set search_path = public
as $$
  select coalesce(jsonb_agg(to_jsonb(e) order by e.day_of_week, e.start_time), '[]'::jsonb)
  from public.timetable_entries e
  where e.semester = p_semester
    and e.branch = p_branch
    and e.batch = p_batch
    and e.section = p_section
    and e.status = 'active'
    and e.valid_from <= p_on_date
    and e.valid_until >= p_on_date
    -- weekly recurring schedule: "on a date" = that date's weekday
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

  -- Timetables are wall-clock schedules pinned to campus time, so day/time
  -- extraction is pinned to UTC (p_at is stored/compared in UTC everywhere).
  v_day := extract(isodow from (p_at at time zone 'utc'))::smallint;
  v_time := (p_at at time zone 'utc')::time;

  -- Candidate next occurrences. day_offset is the number of days from
  -- p_at::date to the next occurrence of the entry's weekday:
  --   0        today, still ongoing (end_time > v_time — includes ongoing)
  --   1..6     later this week (naturally handles "rolls to next day")
  --   7        same weekday, already ended today -> next week
  -- Validity is evaluated against the OCCURRENCE date, not p_at::date, so an
  -- entry that only becomes valid next Monday cannot surface on this Friday.
  select e.* into v_entry
  from public.timetable_entries e
  where e.semester = v_profile.semester
    and e.branch = v_profile.branch
    and e.batch = v_profile.batch
    and e.section = v_profile.section
    and e.status = 'active'
    and e.entry_type <> 'break'
    and (
      p_include_activities
      or e.entry_type not in ('sports', 'club_activity')
    )
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
  return to_jsonb(v_entry);
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
    v_profile.semester, v_profile.branch, v_profile.batch, v_profile.section, p_on_date
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
    (
      select jsonb_agg(to_jsonb(e) order by e.day_of_week, e.start_time)
      from public.timetable_entries e
      where e.semester = v_profile.semester
        and e.branch = v_profile.branch
        and e.batch = v_profile.batch
        and e.section = v_profile.section
        and e.status = 'active'
        and e.valid_from <= v_monday + 6
        and e.valid_until >= v_monday
        and e.entry_type <> 'break'
    ),
    '[]'::jsonb
  );
end;
$$;

comment on function public.orion_resolve_user(uuid) is
  'Identity resolution: anon/authenticated callers are always auth.uid(); explicit p_user_id is honored only for service_role/orion_admin (trusted server-side tooling). Prevents client-supplied-UUID impersonation.';

comment on function public.orion_next_class(uuid, timestamptz, boolean) is
  'Next valid class/activity for the resolved user, honouring validity (per occurrence date), status, breaks and activity preferences. Ongoing classes count as next; rolls to later days and wraps to next week when nothing remains.';
