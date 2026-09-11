-- ORION — Extend timetable_entries.entry_type to include 'tutorial'.
--
-- Discovered during the first live import: the hosted check constraint
-- (timetable_entries_entry_type_check) omits 'tutorial', but the validated
-- Semester 3 source contains 66 tutorial records (marked "(T)" in the PDF).
-- The ORION entry-type vocabulary (AGENTS.md; docs/timetable.md §3) includes
-- tutorial, and the import must preserve validated entry_type values
-- unchanged (task STEP 7/11). This migration aligns the hosted constraint
-- with the documented vocabulary. Idempotent.
do $$ begin
  if exists (
    select 1 from pg_constraint
    where conname = 'timetable_entries_entry_type_check'
      and conrelid = 'public.timetable_entries'::regclass
      and pg_get_constraintdef(oid) not like '%tutorial%'
  ) then
    alter table public.timetable_entries
      drop constraint timetable_entries_entry_type_check;
    alter table public.timetable_entries
      add constraint timetable_entries_entry_type_check
      check (entry_type in ('class','lab','tutorial','seminar','project',
                            'club_activity','sports','break','other'));
  end if;
end $$;
