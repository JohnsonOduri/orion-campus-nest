-- Hostel warden directory (source: "Wardens Team July 2026 - Students Copy.pdf").
-- One row per (person, hall) pair -- a warden team commonly covers 2-4 halls, so
-- the same person appears once per hall they're responsible for; this keeps
-- "who is the warden for hall X" a plain equality lookup. Non-hall-specific
-- roles (Chief Warden, Associate Dean, Hostel Manager, Security Officer) have
-- hall_code/hall_name NULL.
create table if not exists public.hostel_wardens (
  id bigint generated always as identity primary key,
  hall_code text,
  hall_name text,
  role text not null,
  full_name text not null,
  phone text,
  email text,
  status text not null default 'active' check (status in ('active', 'inactive')),
  source_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists hostel_wardens_hall_code_idx on public.hostel_wardens (hall_code);
create index if not exists hostel_wardens_source_id_idx on public.hostel_wardens (source_id);

alter table public.hostel_wardens enable row level security;

create policy "hostel_wardens_select_authenticated"
  on public.hostel_wardens for select
  to authenticated
  using (true);

create trigger hostel_wardens_updated_at
  before update on public.hostel_wardens
  for each row execute function update_updated_at();
