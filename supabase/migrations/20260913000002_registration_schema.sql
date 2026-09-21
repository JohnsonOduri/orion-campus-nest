-- ORION — registration schema additions
--
-- cohort on student_profiles, for RAG cohort-isolation (CLAUDE.md §20) once
-- a student completes registration. profiles.email uniqueness — pre-checked
-- for duplicates (0 found across 5 live rows) before adding.

alter table public.student_profiles
  add column if not exists cohort text;

alter table public.profiles
  add constraint profiles_email_unique unique (email);
