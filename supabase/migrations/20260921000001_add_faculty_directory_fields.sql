-- Add phone/designation/profile_url to faculty, sourced from the official
-- institute directory CSV (Data/iiit_kottayam_faculty.csv). Additive only;
-- existing columns/data untouched.
alter table public.faculty
  add column if not exists phone text,
  add column if not exists designation text,
  add column if not exists profile_url text;
