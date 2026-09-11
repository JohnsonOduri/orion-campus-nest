# Timetable Vertical Slice

Semester 3 timetable PDF → layout-aware extraction → normalization →
validation → preview → idempotent Supabase persistence → authenticated
student timetable queries → **"What is my next class?"**

Source of truth: `Data/Structured/Semester 3_TimeTable_Odd_2026.pdf`
(17 pages, one timetable grid per branch/batch page).

---

## 1. Architecture

```
PDF (positional grid)
  │  scripts/ingest_timetable.py
  ▼
backend/timetable/
  extractor.py    pdfplumber, geometry-first: digit-anchored period columns,
                  break columns, day rows, per-page legend, section metadata
  normalizer.py   cells → canonical TimetableRecords (day/slot/time/course/
                  faculty/type), legend resolution, fragment merging, dedupe
  validator.py    strict pre-insert rules; None-vs-empty directory semantics
  repository.py   the ONLY component that talks to Supabase (service role)
  service.py      run_pipeline() + TimetableService (student queries)
  model.py        dataclasses + tolerant header/day/entry-type parsers
  ▼
Supabase PostgreSQL (courses, faculty, rooms, timetable_periods,
timetable_entries, ingestion_runs)
  ▼  RPC: orion_student_context / orion_active_entries / orion_next_class /
          orion_day_timetable / orion_week_timetable
API (TanStack Start server functions + REST route /api/timetable/*)
```

Timetable data is **authoritative structured data** (AGENTS.md §5): it lives in
PostgreSQL only. No OCR text is embedded into any vector store, and no LLM is
involved anywhere in this slice.

## 2. PDF extraction

- Uses `pdfplumber` (layout-aware, line-based table detection) — never a naive
  text dump. Each page's dominant grid is found by bbox area.
- Period columns are anchored on **header cells that begin with a digit 1–12**;
  times are collected from x-overlapping header fragments and tolerate Word
  artifacts: stacked rows (`"(9.00-9.55"` + `"AM)"`), merged headers
  (`"6 (3.00-3.55 PM)"`), cross-noon ranges (`"11.05-12.00 PM"` → 11:05, not
  23:05), and overlaid glyph runs (`"(5.0P0M-7). 00"` → 17:00–19:00).
- **No period time is hard-coded.** Slot 8/9 on this PDF share one printed
  5.00–7.00 PM range; the shared range is flagged `derived` (see §5).
- Break columns (`B r e a k`, doubled-letter artifacts included) are detected
  by letter-subset matching and recorded as `kind=break` columns, never as
  classes.
- Day rows come from the narrow left column; cells are attributed to days by
  y-overlap (continuation rows attach to the row above).
- The Saturday row is a single merged full-width cell → one whole-grid sports
  record per section, emitted once.
- Repeated headers and per-page legends (course code → name, credits, faculty
  initials) are handled per page.

Inspect without touching the DB:

```bash
.venv/bin/python scripts/inspect_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"
.venv/bin/python scripts/inspect_timetable.py --json "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"
```

## 3. Normalization

`normalize_section()` turns grid cells into canonical records:

- fragments stacked within a column are merged in y-order
  (`"ICS 212" + "(DSL/" + "SSJ)"` → `"ICS 212 (DSL/ SSJ)"`);
- cells are assigned to period columns by best x-overlap (bleeding edges
  tolerated); whole-grid activities (clubs/sports) span every column they cover;
- faculty initials resolve **only** via the page legend; `(T)` tutorial markers
  and `(EC LAB I)`-style lab labels are never treated as initials;
- entry types: `class | lab | tutorial | seminar | project | club_activity |
  sports | break | other` (breaks are structural, excluded from records);
- unknown values produce `unresolved_courses` / `unresolved_faculty` entries —
  **nothing is guessed** (AGENTS.md §6/§34);
- `dedupe()` removes exact duplicates by deterministic `source_uid`.

## 4. Validation

`validator.validate_records()` accepts or rejects; it never repairs.

Rules: valid weekday; `start_time < end_time`; valid entry type; teaching
entries must resolve course code + name and at least one faculty initial;
faculty names aligned; no impossible duplicates; no overlapping entries for the
same section/day (activities exempt); semester/batch/branch/section
consistency; source file exists; validity dates present and ordered.

**Directory cross-check semantics:**

- `known_courses=None` → no directory available, cross-check skipped;
- `known_courses={}` → directory explicitly empty → every teaching record
  **fails** `course_in_catalog` / `faculty_in_directory`.

Failures are collected per record with rule ids and rendered into the
validation report; failing records are never imported.

## 5. Preview JSON

```bash
.venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"
# → Data/processed/semester_3_timetable_odd_2026_preview.json
# → Data/processed/semester_3_timetable_odd_2026_validation.json
```

The preview contains per-section period tables (with `"derived": true` for
shared ranges like the 8/9 evening block) and stats: pages processed, records
extracted/valid/rejected, courses/faculty discovered, unresolved courses and
initials, duplicates, warnings. Current S3 run: **17 pages, 608 records,
608 valid, 0 rejected, 0 duplicates, 0 warnings, 15 courses, 37 faculty**.

## 6. Supabase persistence

Migration: `supabase/migrations/20260909000001_timetable_vertical_slice.sql`

Tables: `courses`, `faculty`, `rooms`, `timetable_periods`,
`timetable_entries` (unique `source_uid`, context/validity/source indexes),
`ingestion_runs` (audit). RLS enabled; read policies for authenticated users,
writes restricted to the service role.

Insert order: courses → faculty → rooms → periods → entries.
Import requires `--import --approved-by <admin>`; everything is recorded in
`ingestion_runs` (who/when/stats) per AGENTS.md §8/§28.

## 7. Idempotency

- `courses` upsert on `code`; `faculty` upsert on `initials`;
- `timetable_entries` upsert on deterministic `source_uid`
  (source_id + section + day + slot + times + course + type);
- `timetable_periods` reconciles fetch→diff on `(source_id, slot_index,
  start_time, kind)` — no expression index, so PostgREST can target the keys.

Running the ingestion twice changes nothing (covered by
`tests/test_repository_idempotency.py`).

## 8. Student context

`orion_student_context()` reads the student's `semester / programme / branch /
batch / section` from `student_profiles` for the **resolved user** — never from
request parameters. No profile → `null` (the API degrades to demo mode).

## 9. Timetable queries

| Function | Returns |
|---|---|
| `orion_active_entries(semester, branch, batch, section, on_date)` | valid active entries for one date, breaks excluded |
| `orion_day_timetable(user_id?, on_date)` | the resolved student's day |
| `orion_week_timetable(user_id?, on_date)` | entries overlapping the Monday–Sunday window |
| `orion_next_class(user_id?, at, include_activities)` | the next class (JSON) or `null` |

All are `security invoker`, so RLS still applies to the calling role.

## 10. Next-class behavior

`orion_next_class` uses a **day-offset occurrence model**:

- offset 0 — same day, still ongoing (`end_time > now`) → **ongoing classes
  count as next**;
- offsets 1–6 — the remaining days of this week (rolls to later days);
- offset 7 — same weekday already ended → **wraps to next week**;
- validity (`valid_from <= occurrence_date <= valid_until`) is evaluated
  against the **occurrence date**, so an entry that starts next Monday cannot
  surface on this Friday;
- `status='active'` only; `break` always excluded; `sports` and
  `club_activity` excluded unless `include_activities=true`;
- no weekday is hard-coded; ordering is by offset then start time;
- no valid candidate → `null`.

Day/time extraction is pinned to `p_at at time zone 'utc'` so behaviour is
identical regardless of the session timezone.

## 11. Authentication & security

Identity rule (`orion_resolve_user`, non-negotiable):

- **anon/authenticated callers are always `auth.uid()`** — a client-supplied
  `p_user_id` is **ignored**, so no one can read another student's timetable
  by passing a UUID;
- explicit `p_user_id` is honored **only** for `service_role` / `orion_admin`
  (trusted server-side tooling: ingestion, integration tests);
- functions are `security invoker`; RLS is never weakened.

API layer (`src/lib/supabase-server.ts`, `src/lib/timetable-api.ts`):

- user requests are served with a **request-scoped client** built from the
  caller's `Authorization: Bearer` header on the **anon** key — Supabase
  verifies the JWT and `auth.uid()` resolves inside the RPCs;
- the **service-role** admin client never serves user requests (it bypasses
  RLS); it is reserved for ingestion/admin tooling;
- no bearer token / no Supabase configured → clearly-flagged demo mode
  (`src/lib/timetable-demo.ts`), never real data.

## 12. Running the ingestion CLI

```bash
# one-time environment
python3 -m venv .venv
.venv/bin/pip install pdfplumber supabase pytest

# inspect (read-only)
.venv/bin/python scripts/inspect_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"

# dry run: extract → normalize → validate → preview + validation JSON
.venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf"

# audited import into Supabase (needs SUPABASE_URL + SUPABASE_SECRET_KEY)
.venv/bin/python scripts/ingest_timetable.py "Data/Structured/Semester 3_TimeTable_Odd_2026.pdf" \
  --import --approved-by admin@example.com
```

Exit code 1 on validation failure; nothing is imported unless every record
passes. Dry-run first — `--import` is the admin-approval step.

## 13. Importing into the LIVE hosted Supabase (actual procedure)

The hosted ORION project predates the local migration and uses a different
naming scheme (`courses.course_code/course_name`, `timetable_entries.department`,
single `faculty_id` FK, no denormalized course/faculty text columns). Import is
therefore handled by a thin hosted adapter, not `repository.py` directly:

```
Data/processed/semester_3_timetable_odd_2026_preview.json   (already validated)
  │  scripts/import_hosted.py
  │    └ backend/timetable/hosted_adapter.py   rename-only mapping + faculty
  │        resolution (PDF legend first, then exact unique initials match
  │        against Data/processed/people.json — never a guess)
  ▼
LIVE Supabase   faculty → courses → timetable_periods → timetable_entries
                (+ timetable_entry_faculty join: ALL teachers per entry,
                ord 0 = primary; 430 links for the S3 source)
```

Hosted-alignment migrations (additive, idempotent, applied 2026-09-09):

- `supabase/migrations/20260909210000_hosted_schema_alignment.sql` —
  `source_uid` natural key + audit columns on `timetable_entries`, nullable
  `start_time`/`end_time` (Saturday full-grid activities print no times),
  `timetable_periods`, `student_profiles` (hosted naming: `department`),
  `ingestion_runs`, `timetable_entry_faculty`, RLS, and the `orion_*` RPCs
  composing `course_code/course_name/faculty_names/room` via joins.
- `supabase/migrations/20260909220000_entry_type_tutorial.sql` — the hosted
  `entry_type` check omitted `tutorial` (66 validated S3 records use it).
- `supabase/migrations/20260909230000_fix_handle_new_user.sql` —
  `public.handle_new_user()` had lost `security definer`, breaking ALL signups
  project-wide (GoTrue 500); restored the canonical pattern.

Idempotency: hosted PostgREST cannot target expression indexes and the source
has no per-section uniqueness, so every entity is reconciled fetch → diff
(natural keys: `faculty.initials`, `courses.course_code`, periods on
`(source_id, slot_index, start_time)`, entries on `source_uid`). Times are
normalized (`"09:00:00"` ≡ `"09:00"`) before comparison. A verified rerun
reports `insert=0 update=0 unchanged=608`.

Admin SQL runs via the Management API with `SUPABASE_ACCESS_TOKEN`
(`scripts/supabase_sql.py`); service-role writes via
`scripts/import_hosted.py` (`.env` only, never browser code). Every import
appends an `ingestion_runs` row (AGENTS.md §28).

## 14. Adding Semester 5 / Semester 7 later

The pipeline is PDF-agnostic:

1. Drop the new PDF into `Data/Structured/` (same layout family: digit-anchored
   period headers, day rows, legend, merged Saturday row).
2. `scripts/inspect_timetable.py` — confirm columns/days/legend resolve; fix
   artifacts in `model.py`/`extractor.py` if a new Word quirk appears (add a
   regression test, as done for `breakk` and `(5.0P0M-7). 00`).
3. Dry-run `scripts/ingest_timetable.py` — review preview + validation JSON;
   every unresolved course/initial must be explained (legend or fix), never
   guessed.
4. Import with `--import --approved-by <admin>`; `source_id` (the file name)
   scopes periods/entries, so semesters never collide.
5. Extend `document_metadata()` if a new programme/branch naming appears.

Academic calendar, classroom details and mess menus follow the same
pattern: extract → normalize → validate → preview → approve → import.

## Testing

```bash
.venv/bin/python -m pytest tests/ -q        # 87 tests
npm run build && npx tsc --noEmit           # API + frontend
```

Test coverage: header parsing (artifacts, cross-noon, breaks), extraction on
the real PDF, normalization/faculty resolution, validation rules incl.
directory semantics, overlap/duplicate detection, repository idempotency,
expiry/status filtering, today/week timetables, next-class (ongoing, future,
next day, week wrap, expired, none), activity opt-in, identity handling.

Live-import tooling (server-side only): `scripts/import_hosted.py`,
`scripts/supabase_sql.py` (Management API SQL), `scripts/verify_import.py`
(counts + integrity), `scripts/create_test_students.py` (GoTrue admin test
users), `scripts/probe_supabase.py` / `scripts/probe_schema.py` (read-only
schema probes).
