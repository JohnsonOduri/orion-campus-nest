-- A person can hold multiple roles (e.g. HOD + teaching faculty) — store
-- every category they hold, not just the most senior one. Existing single
-- values become one-element arrays.
alter table public.faculty
  alter column category type text[] using case when category is null then null else array[category] end;
