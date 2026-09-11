"""Verification queries against the LIVE hosted Supabase (read-only).

STEP 10/11 of the import task: before/after counts and explicit integrity
checks. Run via scripts/supabase_sql.py or import run_verification().
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.supabase_sql import load_env, run_sql  # noqa: E402

SOURCE_ID = "Semester 3_TimeTable_Odd_2026.pdf"

COUNT_SQL = """
select
  count(*)                                        as total_entries,
  count(*) filter (where status = 'active')       as active_entries,
  count(distinct course_id)                       as distinct_courses,
  count(distinct faculty_id)                      as distinct_faculty,
  count(distinct room_id)                         as distinct_rooms,
  count(distinct source_id)                       as sources
from public.timetable_entries
"""

GROUP_SQL = """
select
  source_id, semester, department as branch, batch, section,
  count(*) as entries
from public.timetable_entries
group by source_id, semester, department, batch, section
order by source_id, semester, department, batch, section
"""

INTEGRITY_SQL = """
select
  -- 2. duplicates on the natural key
  (select count(*) from (
     select source_uid, count(*) c from public.timetable_entries
     group by source_uid having count(*) > 1) d)            as duplicate_source_uids,
  -- 3. expired-but-active
  (select count(*) from public.timetable_entries
     where status='active' and valid_until < current_date)  as expired_active,
  -- 4. slots 8/9 must be 17:00-19:00
  (select count(*) from public.timetable_entries
     where slot_index in (8,9)
       and (start_time is distinct from '17:00' or end_time is distinct from '19:00')) as bad_slot_89,
  -- 5. Saturday sports duplicated per section
  (select count(*) from (
     select department, batch, section, count(*) c from public.timetable_entries
     where day_of_week = 6 and entry_type = 'sports'
     group by department, batch, section having count(*) > 1) s)  as saturday_sports_dups,
  -- 6/7. broken FK references
  (select count(*) from public.timetable_entries e
     where e.course_id is not null and not exists
       (select 1 from public.courses c where c.id = e.course_id))   as broken_course_fk,
  (select count(*) from public.timetable_entries e
     where e.faculty_id is not null and not exists
       (select 1 from public.faculty f where f.id = e.faculty_id))  as broken_faculty_fk,
  -- 8. rooms: processed data has none; any room_id would be fabricated
  (select count(*) from public.timetable_entries where room_id is not null) as fabricated_rooms,
  -- entries without times that are not Saturday full-grid activities
  (select count(*) from public.timetable_entries
     where start_time is null and (day_of_week <> 6 or entry_type <> 'sports')) as unexpected_null_times,
  -- faculty join coverage: every entry with initials must have >= 1 link
  (select count(*) from public.timetable_entries e
     where e.faculty_id is not null
       and not exists (select 1 from public.timetable_entry_faculty tef
                       where tef.entry_id = e.id))              as missing_faculty_links
"""

CHECKS_SQL = """
select
  (select count(*) from public.timetable_entries)                          as total,
  (select count(distinct source_id) from public.timetable_entries)         as sources,
  (select count(distinct initials) from public.faculty)                    as faculty_initials,
  (select count(*) from public.courses)                                    as courses,
  (select count(*) from public.timetable_periods
     where source_id = 'Semester 3_TimeTable_Odd_2026.pdf')                as periods_for_source,
  (select count(*) from public.timetable_periods
     where slot_index in (8,9) and start_time='17:00' and end_time='19:00'
       and is_time_derived)                                                as slot_89_derived_rows,
  (select count(*) from public.timetable_entry_faculty)                    as faculty_join_rows
"""


def verify() -> dict:
    load_env()
    out: dict = {}
    out["counts"] = run_sql(COUNT_SQL)
    out["groups"] = run_sql(GROUP_SQL)
    out["integrity"] = run_sql(INTEGRITY_SQL)
    out["checks"] = run_sql(CHECKS_SQL)
    return out


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2, default=str))
