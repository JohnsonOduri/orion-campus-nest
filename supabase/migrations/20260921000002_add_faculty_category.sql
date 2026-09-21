-- Categorizes each faculty row as one of: hod, administrative, faculty,
-- professional_support — derived from the institute directory CSV's
-- designation text (scripts/rebuild_faculty.py). Additive only.
alter table public.faculty
  add column if not exists category text;
