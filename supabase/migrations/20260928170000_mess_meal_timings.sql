-- Mess serving times, so "Is the mess open now?", "What time does the mess
-- close?" and "When is breakfast?" are answered from data instead of a
-- dump of the whole menu (AI-Tests/, 2026-09-28).
--
-- Source: the header row of the published menu, Data/Structured/
-- "august_menu .pdf": BREAKFAST (7:00 - 9:45 am), LUNCH (12:00-2:30pm),
-- SNACKS (4:00-6:00 pm), DINNER (7:00-8:30 pm). Valid until a later menu
-- supersedes it (valid_until stays NULL; a new menu closes these rows).
--
-- Additive. RLS: any signed-in user reads; no client writes (ingestion is
-- service-role, like mess_menus).

create table if not exists public.mess_meal_timings (
  id bigint generated always as identity primary key,
  meal text not null check (meal in ('breakfast', 'lunch', 'snacks', 'dinner')),
  start_time time not null,
  end_time time not null check (end_time > start_time),
  valid_from date not null,
  valid_until date,
  status text not null default 'active' check (status in ('active', 'superseded', 'archived')),
  source_id text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists mess_meal_timings_meal_source_uidx
  on public.mess_meal_timings (meal, source_id);

alter table public.mess_meal_timings enable row level security;

drop policy if exists mess_meal_timings_select on public.mess_meal_timings;
create policy mess_meal_timings_select on public.mess_meal_timings
  for select to authenticated
  using (status = 'active' and valid_from <= current_date and (valid_until is null or valid_until >= current_date));

revoke all on public.mess_meal_timings from anon;
grant select on public.mess_meal_timings to authenticated;

insert into public.mess_meal_timings (meal, start_time, end_time, valid_from, source_id) values
  ('breakfast', '07:00', '09:45', '2026-08-01', 'august_menu .pdf'),
  ('lunch',     '12:00', '14:30', '2026-08-01', 'august_menu .pdf'),
  ('snacks',    '16:00', '18:00', '2026-08-01', 'august_menu .pdf'),
  ('dinner',    '19:00', '20:30', '2026-08-01', 'august_menu .pdf')
on conflict (meal, source_id) do nothing;
