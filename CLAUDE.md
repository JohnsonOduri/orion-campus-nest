# CLAUDE.md — ORION AI-Powered Campus Assistant

> Persistent engineering context for Claude Code / AI coding agents.
> Current project state: 2026-09-11.

## 1. Mission

ORION is an AI-powered campus assistant for students, faculty, Class Representatives (CRs), and administrators. It provides one conversational knowledge layer over institutional information including timetables, academic calendars, exams, courses, faculty, rooms, mess menus, announcements, clubs/events, regulations, policies, notices, PDFs, images, and OCR-derived content.

**Core rule:** PostgreSQL and the approved knowledge base are the source of truth. The LLM is a reasoning/interface layer, never the source of institutional facts.

For deterministic facts, use structured PostgreSQL. For semantic document questions, use retrieval. For questions requiring both, use hybrid retrieval. Never substitute model memory for institutional data.

---

## 2. Repository and infrastructure

- GitHub repository: `JohnsonOduri/orion-campus-nest`
- Default branch: `main`
- Repository visibility: private
- Supabase project: `ORION`
- Supabase project ref: `dgklugpgrnxhyjkvnacp`
- Supabase region: `ap-south-1`
- PostgreSQL: 17.x
- Current Supabase status: active/healthy

Before changing anything:

1. Read `README.md`.
2. Read `AGENTS.md`.
3. Read `docs/timetable.md`.
4. Inspect the repository tree and git status.
5. Inspect relevant `backend/`, `scripts/`, `src/`, tests, and migrations.
6. Inspect the **actual hosted Supabase schema** before writing SQL.
7. Reuse existing architecture; do not treat the repo as greenfield.

---

## 3. Product goals

ORION should:

1. Centralize campus information.
2. Make institutional information discoverable with natural language.
3. Provide grounded, accurate answers.
4. Personalize using authenticated academic context.
5. Support structured and unstructured information.
6. Convert PDFs/images/screenshots into usable data.
7. Let CRs contribute without bypassing administrator approval.
8. Handle validity and expiry.
9. Support timetable/course/faculty/room/exam/mess/document/announcement discovery.
10. Keep prototype infrastructure close to zero cost where practical.

ORION is **not** a college ERP. Do not add fees, payroll, medical records, grades, banking, or other out-of-scope systems unless explicitly requested.

---

## 4. Roles

### STUDENT
Consumers of campus information. Can ask questions, view own timetable/calendar/exams, browse courses/faculty/clubs/events/mess/documents, and receive recommendations. Cannot directly mutate authoritative institutional data.

### FACULTY
Can view relevant academic information and maintain permitted profile information. Approved/public data may include research interests, subjects, office, office hours, achievements, and schedules.

### CR
Controlled data contributor. Can submit timetable files, mess menus, announcements, notices, screenshots, and batch/class information. A CR submission is never authoritative until approved.

### ADMIN
Trusted data manager. Can approve/reject submissions, manage authoritative data, users/roles, faculty, announcements, documents, OCR verification, lifecycle, and audit logs.

---

## 5. Source-of-truth matrix

| Query/data | Primary source |
|---|---|
| Next class | PostgreSQL timetable |
| Today/week timetable | PostgreSQL timetable |
| Faculty teaching a course | PostgreSQL faculty + timetable |
| Class room | PostgreSQL timetable/rooms |
| Exam date/time | PostgreSQL exams |
| Academic deadline/event | PostgreSQL academic_calendar |
| Mess menu | PostgreSQL mess_menus |
| Current announcement | PostgreSQL announcements |
| Faculty research interests | Structured faculty + approved semantic content |
| Regulations/policies | RAG over approved documents |
| Long institutional documents | RAG |
| Faculty + availability | Hybrid faculty + timetable |
| Faculty recommendation | Faculty/research data + semantic retrieval + optional schedule context |

Never route every query to RAG or an LLM.

---

## 6. Target architecture

```text
USER
 |
 v
Authentication / Session
 |
 v
Authenticated Academic Context
 |
 v
QUERY ROUTER
 /          |           STRUCTURED SEMANTIC    HYBRID
 |           |           |
SQL       pgvector    SQL + vector
 \           |           /
  +----------+----------+
             |
             v
      Context Validation
             |
             v
        LLM / Generator
             |
             v
    Grounded Answer + Sources
```

Ingestion:

```text
PDF / Image / Screenshot / Text
        |
        v
File validation
        |
        v
OCR / extraction / table parsing
        |
        v
Metadata extraction
        |
        v
Sensitive-data filtering
        |
        v
Content classification
        |
        v
Human verification
        |
        v
CR submission / Admin approval
        |
        v
Normalization
        |
        +------------------+
        |                  |
        v                  v
 Structured DB       Documents + pgvector
```

---

# 7. COMPLETED: Semester 3 timetable vertical slice

Source:

`Data/Structured/Semester 3_TimeTable_Odd_2026.pdf`

Verified:

- 17 pages
- 608 final records
- 608 valid
- 0 rejected
- 0 duplicates
- 0 warnings
- 15 courses
- 37 faculty discovered
- 430 `timetable_entry_faculty` links
- 9 timetable periods
- slots 8/9 share the printed 5:00–7:00 PM range and are marked derived
- Saturday full-grid sports activity is emitted once per section
- no false faculty tokens such as `(T)`, `ECLABI`, `ICS`, `LAB`
- current timetable source is `Semester 3_TimeTable_Odd_2026.pdf`

The reference documentation is `docs/timetable.md`.

Existing implementation:

```text
backend/timetable/
  model.py
  extractor.py
  normalizer.py
  validator.py
  repository.py
  service.py

scripts/
  inspect_timetable.py
  ingest_timetable.py
  import_hosted.py
  verify_import.py
  supabase_sql.py
  create_test_students.py
  probe_supabase.py
  probe_schema.py

src/lib/
  timetable-api.ts
  supabase-server.ts
  timetable-demo.ts

src/routes/api/timetable/
  $*.tsx

supabase/migrations/
  20260909000001_timetable_vertical_slice.sql
  20260909210000_hosted_schema_alignment.sql
  20260909220000_entry_type_tutorial.sql
  20260909230000_fix_handle_new_user.sql
```

Pipeline:

```text
PDF -> extractor -> normalizer -> validator -> preview/validation JSON
    -> hosted adapter/import -> Supabase -> RPCs -> API -> frontend
```

Timetable is authoritative **structured** data. Do not replace it with RAG.

---

## 8. Timetable extraction rules

The PDF is positional and must be processed layout-aware.

Existing behavior:

- `pdfplumber` with geometry-first extraction.
- Period columns detected from digit-anchored headers.
- Word/PDF header artifacts tolerated.
- Cross-noon ranges handled correctly.
- Break columns detected structurally and never treated as classes.
- Day rows assigned using vertical overlap.
- Continuation rows attach to the preceding day.
- Per-page legends resolve course codes and faculty initials.
- Whole-grid activities are handled separately.
- Saturday merged sports cells become one record per section.
- Faculty initials are resolved only from supported evidence.
- Unknown courses/faculty are reported, never guessed.
- Exact duplicates use deterministic `source_uid`.

Do not replace this with naive text dumping.

---

## 9. Timetable normalization and validation

Canonical data includes:

```text
day
slot
start_time
end_time
course
faculty
entry_type
semester
programme
department
batch
section
source
validity
```

Entry types:

```text
class
lab
tutorial
seminar
project
club_activity
sports
break
other
```

Important:

- `(T)` means tutorial marker, not faculty initials.
- `(EC LAB I)`-style labels are not faculty initials.
- Never guess faculty mappings.
- Preserve multiple teachers using `timetable_entry_faculty`.
- `ord=0` represents the primary teacher where applicable.
- Validation rejects; it does not silently repair.

Validation includes:

- valid weekday
- start < end
- valid entry type
- resolvable teaching course
- resolvable faculty
- no impossible duplicates
- no invalid section/day overlaps
- context consistency
- valid source
- validity dates

Directory semantics:

```text
known_courses=None -> no directory available; cross-check skipped
known_courses={}    -> directory explicitly empty; teaching records fail checks
```

Do not change this distinction casually.

---

# 10. LIVE SUPABASE STATE

The hosted database is already populated with the Semester 3 timetable.

Current important counts:

```text
profiles                 2
student_profiles         2

departments              0

faculty                  37
courses                  15

rooms                    0
room_allocations         0

timetable_periods        9
timetable_entries        608
timetable_entry_faculty  430

academic_calendar        0
exams                    0
mess_menus               0
announcements            0

documents                0
document_versions        0
document_chunks          0

ingestion_jobs           0
ingestion_runs           3
approval_requests        0
audit_logs               0
```

Timetable aggregate:

```text
total_entries    608
active_entries   608
currently_valid  608
distinct courses 15
distinct faculty 35
distinct rooms   0
sources          1
```

The 37 faculty rows include 37 discovered faculty; 35 are currently referenced by the direct timetable `faculty_id` field. The many-to-many table contains 430 teacher links.

---

# 11. ACTUAL HOSTED SCHEMA — DO NOT ASSUME OLD COLUMN NAMES

The hosted schema is not identical to every earlier/local design. Always inspect it.

### courses

```text
id
course_code
course_name
credits
programme
specialisation
cohort
semester
prerequisites
syllabus_summary
status
created_at
updated_at
```

Do not assume `code` or `name`.

### rooms

```text
id
room_no
room_type
capacity
status
created_at
```

Do not assume `room_code`.

### timetable_entries

```text
id
course_id
faculty_id
room_id
day_of_week
slot_index
start_time
end_time
semester
programme
department
batch
section
entry_type
valid_from
valid_until
status
source_id
approved_at
approved_by
created_at
updated_at
source_uid
source_page
source_text
lab_batch
```

There is **no `branch` column** in the hosted table.

### faculty

```text
id
full_name
initials
department_id
email
office_location
office_hours
research_interests
status
created_at
updated_at
```

Current faculty enrichment:

```text
faculty rows       37
with initials      37
with email         0
with research      0
```

Faculty master data is therefore incomplete.

### academic_calendar

Uses `event_date`; do not assume `end_date`.

### mess_menus

Does not currently have `week_label`.

### documents

Uses `status` for lifecycle. Do not assume `approval_status`.

### ingestion_jobs

Uses `document_id`, `job_type`, `status`, etc. Do not assume `source_file`.

When a query gives PostgreSQL `42703 undefined_column`, inspect the actual schema instead of changing the schema just to satisfy the query.

---

# 12. Supabase table map

```text
profiles
departments
faculty
courses
rooms
room_allocations

timetable_entries
timetable_entry_faculty
timetable_periods

student_profiles

academic_calendar
exams
mess_menus
announcements

documents
document_versions
document_chunks

ingestion_jobs
ingestion_runs
approval_requests
audit_logs
```

RLS is enabled on the public tables. Do not disable it as a shortcut.

---

# 13. Supabase security model

## Normal user traffic

Use a request-scoped Supabase client carrying the caller's JWT.

Do **not** use service-role for ordinary user requests.

## Service role

Service-role bypasses RLS and is reserved for trusted server-side operations such as:

- ingestion
- controlled admin tooling
- maintenance
- integration tests

Never expose it in frontend/browser code or `NEXT_PUBLIC_*` variables. Never commit it.

## Identity rule

For normal callers:

```text
auth.uid() is authoritative
client-supplied p_user_id is ignored
```

Only trusted service-role / `orion_admin` tooling may explicitly act on behalf of another user.

Do not regress to:

```sql
coalesce(p_user_id, auth.uid())
```

for normal client calls.

## RLS

Prefer `SECURITY INVOKER`.

Do not add `SECURITY DEFINER` merely to bypass a permission error.

Never use user-editable `user_metadata` for authorization decisions.

---

# 14. Timetable RPC behavior

Existing conceptual RPCs:

```text
orion_student_context
orion_active_entries
orion_day_timetable
orion_week_timetable
orion_next_class
```

`orion_student_context` reads the authenticated student's:

```text
semester
programme
department
batch
section
```

from `student_profiles`.

`orion_next_class` uses a day-offset model:

```text
offset 0 -> same day; ongoing class still counts
offset 1..6 -> remaining days of current week
offset 7 -> same weekday next week
```

Validity is evaluated against the occurrence date.

Only `status='active'` is considered.

`break` is always excluded.

`sports` and `club_activity` are excluded unless `include_activities=true`.

Do not hard-code weekdays.

The implementation pins relevant day/time behavior consistently to UTC.

---

# 15. Existing API implementation

The current timetable API uses TanStack Start.

Important framework detail:

The current implementation obtains the request with:

```ts
getRequest()
```

from:

```ts
@tanstack/react-start/server
```

Do not assume the handler context contains a direct `request` property.

The API uses a request-scoped non-service-role Supabase client for user traffic.

Demo mode exists when Supabase/auth is unavailable and must be clearly distinguishable from real data.

---

# 16. Existing verification

Previously verified:

```text
pytest tests/ -q
=> 87 passed

npm run build
=> passes

npx tsc --noEmit
=> passes
```

The timetable slice has tests for extraction, normalization, validation, idempotency, expiry, timetable retrieval, next-class behavior, activities, and identity isolation.

There are known pre-existing repo-wide formatting/lint issues in untouched areas. Do not launch a broad formatting rewrite just to fix unrelated legacy files.

---

# 17. NOT COMPLETE YET

Do not claim the entire structured-data layer or AI system is complete.

### Timetables
- Semester 5 TODO
- Semester 7 TODO

### Rooms
- Classroom Details extraction TODO
- `rooms = 0`
- `room_allocations = 0`

### Academic calendar
- source exists
- database population TODO
- `academic_calendar = 0`

### Exams
- schema exists
- dataset population TODO
- `exams = 0`

### Mess
- schema exists
- dataset population TODO
- `mess_menus = 0`

### Faculty
- 37 basic faculty records exist
- email enrichment TODO
- research-interest enrichment TODO
- department normalization may require departments data

### Departments
- `departments = 0`

### Announcements
- `announcements = 0`

### Documents/RAG
- `documents = 0`
- `document_versions = 0`
- `document_chunks = 0`
- embeddings = 0
- production RAG TODO

### AI router
- final production structured/semantic/hybrid router TODO

### LLM orchestration
- final grounded answer pipeline TODO

### CR workflow
- schema foundations exist
- full upload/OCR/preview/approval/publish UX and processing pipeline TODO

---

# 18. Recommended implementation order

## Phase 1 — Finish structured data

1. Import/normalize faculty JSON.
2. Process Semester 5 timetable.
3. Process Semester 7 timetable.
4. Process Classroom Details.
5. Populate rooms and room allocations.
6. Process Academic Calendar.
7. Populate academic_calendar.
8. Process exams.
9. Process mess menu.
10. Populate/normalize departments.
11. Verify foreign keys, source IDs, validity, lifecycle, and query behavior.

## Phase 2 — Document ingestion

1. Upload/storage.
2. PDF/image extraction.
3. OCR.
4. Classification.
5. Sensitive-data detection/redaction.
6. Metadata.
7. Versioning.
8. Logical chunking.
9. Embeddings.
10. pgvector.
11. Retrieval filters.

## Phase 3 — CR workflow

```text
CR upload
 -> validate
 -> OCR/extract
 -> confidence check
 -> classify
 -> sensitive-data check
 -> preview
 -> submit
 -> approval_requests
 -> admin review
 -> approve/reject
 -> publish
 -> audit_logs
```

CR uploads must never directly modify authoritative tables.

## Phase 4 — Query router

Classify:

```text
STRUCTURED
SEMANTIC
HYBRID
RECOMMENDATION
UNSUPPORTED / AMBIGUOUS
```

Examples:

```text
"What is my next class?"
=> STRUCTURED

"What are the rules for course withdrawal?"
=> SEMANTIC

"Which faculty work on NLP and when can I meet them?"
=> HYBRID

"Recommend a faculty member for computer vision."
=> RECOMMENDATION
```

## Phase 5 — Grounded generation

```text
query
 -> route
 -> retrieve
 -> validate
 -> context
 -> generate
 -> grounding check
 -> answer
```

For deterministic results, return structured results directly when practical instead of spending an LLM call.

## Phase 6 — Product integration

Integrate dashboard, chat, timetable, calendar, exams, courses, faculty, mess, documents, announcements, CR workflows, and admin approval.

---

# 19. RAG design

Use PostgreSQL + pgvector for the prototype unless scale proves otherwise.

`document_chunks` contains:

```text
id
document_id
version_id
chunk_index
content
embedding
page_start
page_end
section_title
metadata
confidence_score
created_at
```

Useful metadata:

```text
document_id
source_id
document_type
category
programme
specialisation
cohort
department
role
valid_from
valid_until
status
page
section
confidence
```

Do not vectorize every relational record.

Chunk long documents by logical sections where possible. An initial target of roughly 500–800 tokens is reasonable, but semantic boundaries matter more than an arbitrary size.

---

# 20. Critical RAG rule: cohort isolation

The corpus includes different regulation cohorts, including:

```text
UG Regulations 26 onwards
UG Regulations 21-25
```

These must remain cohort-aware.

Never retrieve a rule from one cohort and present it as applying to another.

RAG filters must respect:

- cohort
- programme
- specialisation
- department
- role
- validity
- approval status

If evidence is insufficient, say so.

---

# 21. Data lifecycle

Time-sensitive records should use:

```text
created_at
updated_at
valid_from
valid_until
status
source_id
approved_at
approved_by
```

Examples:

| Data | Lifecycle |
|---|---|
| Timetable | Until superseded |
| Exam | Through exam period |
| Academic event | Relevant date/range |
| Mess menu | Daily/weekly |
| Announcement | Explicit expiry |
| Club event | Until completion |
| Batch group link | Normally 6 months unless renewed |
| Regulation | Version-controlled |
| Faculty achievement | Manual update/review |

Expired information must not be returned as current and must be filtered out of current RAG retrieval.

---

# 22. Sensitive data

Reject/redact unnecessary:

- government IDs
- passwords
- API keys
- authentication tokens
- financial information
- medical information
- unnecessary private contact data
- confidential communications
- disciplinary information
- unnecessary PII

Minimum-data principle:

> If ORION does not need the field, do not store it.

Do not log secrets or sensitive document contents unnecessarily.

---

# 23. Content classification

Potential categories:

```text
OFFICIAL
ACADEMIC
ANNOUNCEMENT
EVENT
TIMETABLE
CLUB
DOCUMENT
ADVERTISEMENT
IRRELEVANT
```

Pure advertisements should not become institutional knowledge.

Do not reject an official notice merely because it contains promotional language if it also contains useful institutional information.

---

# 24. Faculty data

Structured faculty:

```text
name
initials
department
email
office
office hours
status
```

Semantic faculty information:

```text
research interests
publications
achievements
areas of expertise
```

Faculty availability is derived from:

```text
faculty profile
+
current date/time
+
timetable
+
validity
```

Never claim a current physical location unless reliable data supports it.

Safer response:

> I don't have enough current schedule information to determine their availability.

---

# 25. Personalization

May use:

- authenticated user
- semester
- programme
- department
- batch
- section
- courses
- approved interests
- club memberships

Do not infer sensitive characteristics.

Personalization never overrides authorization.

Academic context should come from trusted server-side data, not arbitrary query parameters.

---

# 26. Frontend direction

ORION should feel like a modern AI product rather than a legacy college ERP.

Qualities:

- AI-first
- clean
- premium
- friendly
- fast
- responsive
- accessible
- strong visual hierarchy
- useful information density
- clear loading/error/empty states

Reuse existing design components/tokens before creating new ones.

---

# 27. API rules

Every protected endpoint must:

- authenticate
- authorize
- validate input
- use server-side identity
- enforce ownership
- return consistent errors
- avoid leaking internals

Never trust:

- client-side role checks
- hidden UI buttons
- request-body role fields
- request-body ownership
- client-supplied user IDs

---

# 28. Database rules

Use PostgreSQL for deterministic data.

Use pgvector for semantic data.

Avoid a separate vector DB unless technically justified.

For schema changes:

1. Inspect current hosted schema.
2. Inspect existing migrations.
3. Understand consumers.
4. Prefer additive/idempotent changes.
5. Test.
6. Verify using SQL.
7. Update documentation.

Never modify production schema just to accommodate an incorrect query.

---

# 29. Supabase operating rules

When implementing Supabase-specific functionality, verify current Supabase documentation because APIs/features evolve.

After changes:

- verify behavior with a real query/test
- preserve RLS
- check security/performance implications
- verify Data API access if new tables are exposed
- keep migrations version-controlled

Do not weaken authorization to make development easier.

---

# 30. Cost strategy

This is a prototype.

Prefer:

```text
Supabase PostgreSQL
+
pgvector
+
serverless/container backend
+
managed object storage
```

Avoid unnecessary:

- GPU servers
- always-on worker fleets
- dedicated vector DB
- multiple redundant cloud services

Reduce LLM spend with:

- deterministic SQL routing
- metadata filtering
- small context
- caching where safe
- smaller models for classification
- no LLM call when SQL can answer directly

---

# 31. Testing requirements

Test:

### Structured
- timetable
- context resolution
- expiry
- rooms
- exams
- announcements

### Security
- authentication
- authorization
- role restrictions
- user isolation
- service-role-only operations

### Ingestion
- extraction
- OCR artifacts
- normalization
- validation
- confidence
- duplicates
- idempotency

### CR
- upload
- pending
- approve
- reject
- audit

### RAG
- metadata filters
- cohort isolation
- expiry
- grounding
- source/page attribution
- no-answer behavior

### Router
Representative routing:

```text
next class -> structured
regulations -> semantic
faculty + availability -> hybrid
faculty recommendation -> recommendation
unsupported -> safe response/clarification
```

---

# 32. Observability and auditability

Track, where useful:

- API failures
- authentication failures
- ingestion failures
- OCR failures
- approval actions
- routing decisions
- retrieval failures
- latency
- model/API failures

Never log credentials, tokens, secrets, or unnecessary personal data.

Important mutations should answer:

```text
Who changed it?
What changed?
When?
What source caused it?
Who approved it?
What was the previous version?
```

---

# 33. Git rules

Keep commits focused:

```text
feat: import semester 5 timetable
feat: add academic calendar ingestion
feat: add document chunking pipeline
fix: filter expired RAG documents
fix: enforce authenticated timetable identity
feat: add CR approval flow
```

Never commit secrets, credentials, or unnecessary personal data.

Before a PR:

- run relevant tests
- run build/typecheck
- inspect diff
- check security implications
- update docs

---

# 34. Common schema/query pitfalls

Do not assume:

```text
timetable_entries.branch       # DOES NOT EXIST
courses.code                   # DOES NOT EXIST
courses.name                   # DOES NOT EXIST
rooms.room_code                # DOES NOT EXIST
academic_calendar.end_date     # DOES NOT EXIST
mess_menus.week_label          # DOES NOT EXIST
documents.approval_status      # DOES NOT EXIST
ingestion_jobs.source_file     # DOES NOT EXIST
```

Use the actual hosted schema.

---

# 35. First task for every new Claude session

```text
1. Read CLAUDE.md.
2. Read README.md.
3. Read AGENTS.md.
4. Inspect git status.
5. Inspect relevant source files.
6. Inspect relevant Supabase schema.
7. Determine what already exists.
8. State a minimal implementation plan.
9. Implement only the requested scope.
10. Run relevant tests.
11. Verify database changes if applicable.
12. Update documentation / Work-done if appropriate.
13. Summarize changed files and verification.
```

Do not immediately code after reading this file.

---

# 36. Immediate roadmap

Unless the user explicitly requests another task, prioritize:

1. Faculty JSON normalization/import.
2. Semester 5 timetable.
3. Semester 7 timetable.
4. Classroom Details.
5. Academic Calendar.
6. Mess menu.
7. Exams.
8. Departments/master data.
9. Structured-data verification.
10. Document ingestion.
11. RAG.
12. Query router.
13. LLM orchestration.
14. Hybrid retrieval.
15. CR approval UX/processing.
16. Full product integration.

The Semester 3 timetable pipeline is the reference implementation for future structured ingestion.

---

# 37. Definition of done

A feature is done only when:

- correct source of truth is used
- authorization is enforced
- validation exists
- errors are handled
- tests exist
- relevant tests pass
- database changes are verified
- no secrets are exposed
- documentation is updated
- validity/expiry is considered
- auditability is preserved where required
- representative real data is tested where practical

---

# 38. Golden rule

Before implementing any ORION feature, answer:

```text
1. What is the authoritative source?
2. Who may modify it?
3. Who may read it?
4. How long is it valid?
5. How do we prove the answer is grounded?
```

If those five questions cannot be answered, the feature design is incomplete.

**Optimize ORION for correctness, security, freshness, explainability, and usefulness — not merely for sounding intelligent.**
