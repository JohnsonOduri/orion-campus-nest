# AGENTS.md --- ORION Agent Instructions

## 1. Purpose

This file defines the operating rules for AI coding agents and
developers working on the ORION repository.

ORION is an AI-powered campus assistant combining:

-   Structured institutional data.
-   Document and image ingestion.
-   OCR.
-   Semantic/vector search.
-   Retrieval-Augmented Generation (RAG).
-   Role-based access control.
-   CR submission workflows.
-   Administrator approval.
-   Personalization.
-   Data expiry and lifecycle management.

Agents must understand the existing project before making changes.

------------------------------------------------------------------------

# 2. First Rule: Inspect Before Acting

Before implementing anything:

1.  Inspect the repository tree.
2.  Read `README.md`.
3.  Read this file.
4.  Inspect existing package manifests.
5.  Inspect environment/configuration examples.
6.  Inspect database schemas/migrations.
7.  Inspect API routes.
8.  Inspect existing UI components.
9.  Inspect tests.
10. Determine what already exists.

Do not assume the project is empty.

Do not recreate components that already exist.

Do not replace architecture simply because another architecture is
personally preferred.

------------------------------------------------------------------------

# 3. Product Context

ORION is not a generic chatbot.

It is a campus knowledge and assistance platform.

The source of truth is institutional data.

The LLM is an interface and reasoning layer over trusted data.

The system must prioritize:

``` text
Correctness
>
Security
>
Data Integrity
>
Freshness
>
Maintainability
>
Cost
>
Convenience
```

When a fluent AI answer conflicts with verified database information,
the verified data wins.

------------------------------------------------------------------------

# 4. Core Architectural Principle

Use the correct data source for the question.

``` text
                    User Query
                        |
                        v
              Authentication Context
                        |
                        v
                 Query Router
                  /    |     \
                 /     |      \
                v      v       v
             SQL     Vector   Hybrid
              |        |        |
              +--------+--------+
                       |
                       v
                 Context Builder
                       |
                       v
                  LLM / RAG
                       |
                       v
               Grounded Response
```

The router must not blindly send every question to vector search.

------------------------------------------------------------------------

# 5. Source-of-Truth Rules

## Use structured database data for:

-   Timetables.
-   Courses.
-   Faculty schedules.
-   Exam schedules.
-   Academic calendar.
-   Mess schedules.
-   Event dates.
-   Club metadata.
-   User profiles.
-   Roles.
-   Announcements with structured metadata.

## Use vector retrieval for:

-   Long-form institute documents.
-   Regulations.
-   Policies.
-   Circulars.
-   OCR text.
-   Notices.
-   Semantic faculty research information.
-   Other approved unstructured content.

## Use hybrid retrieval when:

A query needs both structured facts and semantic context.

Example:

> "Which faculty work in NLP and when can I meet them?"

This may require:

-   Faculty research interests.
-   Faculty schedule.
-   Office hours.

------------------------------------------------------------------------

# 6. Never Hallucinate Institutional Facts

Agents must preserve safeguards against fabricated:

-   Room numbers.
-   Faculty availability.
-   Exam dates.
-   Timetable entries.
-   Course information.
-   Deadlines.
-   Official links.
-   Announcements.
-   Event dates.

If reliable information cannot be retrieved, the assistant should say
so.

A safe answer is preferable to a confident incorrect answer.

------------------------------------------------------------------------

# 7. Authentication and Authorization

Every protected operation must enforce authorization server-side.

Never trust:

-   Client-side role checks.
-   Hidden UI buttons.
-   Request body role fields.
-   User-provided user IDs.
-   Client-provided ownership claims.

Use the authenticated identity from the server-side authentication
context.

Required roles:

``` text
STUDENT
FACULTY
CR
ADMIN
```

A user must only access resources they are authorized to access.

------------------------------------------------------------------------

# 8. CR Data Workflow

CRs are contributors, not authoritative administrators.

Never implement:

``` text
CR upload -> immediate production database mutation
```

The expected workflow is:

``` text
Upload
  |
Validation
  |
OCR / Extraction
  |
Preview
  |
Submission
  |
Pending
  |
Admin Review
  |
Approve / Reject
  |
Publish
```

Rejected submissions must preserve a reason.

Approved changes must be auditable.

------------------------------------------------------------------------

# 9. OCR and Document Ingestion

When handling PDFs/images:

``` text
Input
 ↓
File validation
 ↓
OCR / text extraction
 ↓
Table extraction
 ↓
Metadata extraction
 ↓
Sensitive information detection
 ↓
Content classification
 ↓
Human review when necessary
 ↓
Normalization
 ↓
Structured DB and/or Vector DB
```

Do not blindly embed raw OCR output.

OCR can contain errors.

Timetable/table information should be converted into structured records
whenever possible.

------------------------------------------------------------------------

# 10. OCR Confidence

If extraction confidence is low or table structure is ambiguous:

-   Flag the record.
-   Require human verification.
-   Do not silently publish uncertain institutional information.

For example:

``` text
OCR confidence: 62%
Status: Requires verification
```

is preferable to silently storing incorrect data.

------------------------------------------------------------------------

# 11. Sensitive Information

Do not ingest or expose unnecessary sensitive information.

Reject/redact where appropriate:

-   Government ID numbers.
-   Passwords.
-   API keys.
-   Authentication tokens.
-   Financial data.
-   Medical data.
-   Private personal information.
-   Confidential internal information.
-   Student disciplinary information.

Apply data minimization.

If a feature does not require a sensitive field, do not store it.

------------------------------------------------------------------------

# 12. Advertisement Filtering

Pure advertisements should not become institutional knowledge.

Classify uploaded content where practical:

``` text
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

Reject or exclude pure advertisements.

Do not remove legitimate institutional information merely because a
notice contains promotional content.

------------------------------------------------------------------------

# 13. Expiry and Freshness

Time-sensitive information must contain validity metadata.

Prefer:

``` text
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

``` text
Announcement -> explicit expiry
Event -> after event
Exam -> after examination
Mess menu -> daily/weekly
Timetable -> until replacement
Batch group link -> normally 6 months
```

Expired information must not be presented as current.

When indexing documents into vector search, metadata filters must
prevent expired documents from being retrieved as current information.

------------------------------------------------------------------------

# 14. Database Rules

Use relational data for deterministic facts.

Do not introduce a vector database when PostgreSQL can solve the problem
directly.

Prefer:

``` text
PostgreSQL
+
pgvector
```

for the prototype when it satisfies requirements.

Avoid unnecessary infrastructure.

Database migrations must be version-controlled.

Never manually modify production schema without a migration.

------------------------------------------------------------------------

# 15. API Rules

APIs should:

-   Validate input.
-   Authenticate requests.
-   Authorize operations.
-   Return consistent error structures.
-   Avoid leaking internal exceptions.
-   Use appropriate HTTP status codes.
-   Validate uploaded file types and sizes.
-   Prevent unauthorized object access.

Do not put secrets in frontend code.

Never commit `.env` files containing secrets.

------------------------------------------------------------------------

# 16. AI/RAG Rules

AI features must be grounded.

A RAG pipeline should generally:

``` text
Query
 ↓
Intent classification
 ↓
Metadata filtering
 ↓
Retrieval
 ↓
Reranking if required
 ↓
Context assembly
 ↓
LLM generation
 ↓
Validation / citation handling
 ↓
Response
```

The LLM should not be allowed to invent missing context.

For deterministic questions, bypass unnecessary generation where
practical.

For example:

``` text
"What is my next class?"
```

should be resolved from timetable data instead of relying on semantic
retrieval.

------------------------------------------------------------------------

# 17. Personalization

Personalization may use:

-   Department.
-   Semester.
-   Section.
-   Courses.
-   Approved interests.
-   Club memberships.

Do not infer sensitive characteristics.

Do not use personalization to override authorization.

Example:

``` text
"What classes do I have tomorrow?"
```

should use the authenticated student's actual section/timetable.

------------------------------------------------------------------------

# 18. Faculty Availability

Faculty location/availability must be derived from reliable schedule
information.

Example logic:

``` text
Current time
+
Current date
+
Faculty schedule
+
Current academic validity
=
Likely scheduled activity
```

If the data cannot establish availability, say:

> "I don't have enough current schedule information to determine their
> availability."

Never fabricate real-time location.

------------------------------------------------------------------------

# 19. Frontend Rules

Before adding UI:

1.  Find existing layout components.
2.  Find existing design tokens.
3.  Find existing buttons/forms/cards.
4.  Reuse existing components.
5.  Preserve responsive behavior.
6.  Implement loading, error, and empty states.

Do not create one-off visual components when a reusable component should
exist.

The product should feel like one coherent application.

------------------------------------------------------------------------

# 20. UX Direction

ORION should feel like a modern AI SaaS product rather than a
traditional college ERP.

Desired qualities:

-   AI-first.
-   Premium.
-   Clean.
-   Friendly.
-   Fast.
-   Responsive.
-   Accessible.
-   Information-dense without being cluttered.

The student experience should prioritize:

``` text
Ask ORION
+
Quick access to frequently used information
```

------------------------------------------------------------------------

# 21. Required Product Areas

Agents should preserve support for:

### Student

-   Dashboard.
-   AI chat.
-   Timetable.
-   Academic calendar.
-   Exams.
-   Courses.
-   Faculty.
-   Clubs.
-   Events.
-   Mess.
-   Documents.
-   Announcements.
-   Notifications.
-   Search.
-   Profile.
-   Settings.

### CR

-   Dashboard.
-   Upload.
-   OCR verification.
-   Submission details.
-   Upload history.

### Admin

-   Dashboard.
-   Approval queue.
-   Submission review.
-   User management.
-   Faculty management.
-   Announcement management.
-   Data management.
-   Analytics.
-   Audit logs.

------------------------------------------------------------------------

# 22. Coding Standards

Use the conventions already present in the repository.

Prefer:

-   Small focused functions.
-   Clear names.
-   Explicit types.
-   Reusable utilities.
-   Separation of concerns.
-   Meaningful error handling.
-   Testable business logic.

Avoid:

-   Giant components.
-   Duplicate logic.
-   Hard-coded institutional data.
-   Hidden side effects.
-   Unnecessary abstractions.
-   Premature microservices.
-   Global mutable state without justification.

------------------------------------------------------------------------

# 23. Dependency Rules

Before adding a dependency, ask:

1.  Is it actually necessary?
2.  Does the project already have an equivalent?
3.  Is the dependency maintained?
4.  Does it increase bundle/runtime cost?
5.  Is there a simpler native solution?

Do not add libraries merely for convenience.

------------------------------------------------------------------------

# 24. Cost Optimization

This is initially a prototype.

Prefer low-cost/free infrastructure.

Avoid unnecessarily expensive:

-   Managed databases.
-   Dedicated vector databases.
-   GPU servers.
-   Multiple cloud services.
-   Always-on workers.

Where appropriate, use:

``` text
Supabase/PostgreSQL
+
pgvector
+
serverless/container deployment
+
managed object storage
```

Optimize LLM usage through:

-   Query routing.
-   Small context windows.
-   Metadata filtering.
-   Caching where safe.
-   Deterministic SQL answers.
-   Avoiding unnecessary LLM calls.

------------------------------------------------------------------------

# 25. Testing Requirements

Important business logic requires tests.

At minimum, test:

-   Authentication.
-   Authorization.
-   Role permissions.
-   Timetable retrieval.
-   Expiry handling.
-   Announcement filtering.
-   CR approval.
-   Rejection.
-   OCR normalization.
-   Sensitive data filtering.
-   RAG retrieval filters.
-   Faculty availability logic.

AI tests should include representative questions and expected grounding
behavior.

------------------------------------------------------------------------

# 26. Error Handling

Every user-facing feature should have:

-   Loading state.
-   Empty state.
-   Error state.
-   Retry action where appropriate.

Errors should be understandable.

Avoid exposing:

-   Stack traces.
-   SQL errors.
-   API keys.
-   Internal service names.
-   Infrastructure details.

------------------------------------------------------------------------

# 27. Observability

For backend systems, use structured logs where practical.

Track:

-   Request failures.
-   Authentication failures.
-   Ingestion failures.
-   OCR failures.
-   Approval actions.
-   AI routing decisions where safe.
-   Retrieval failures.
-   Latency.
-   External API errors.

Do not log sensitive information.

------------------------------------------------------------------------

# 28. Auditability

Important mutations should create audit records.

Examples:

``` text
Who uploaded it?
Who approved it?
Who rejected it?
When?
What changed?
What was the previous version?
```

This is particularly important for:

-   Timetables.
-   Exams.
-   Announcements.
-   Faculty information.
-   Documents.
-   Administrative changes.

------------------------------------------------------------------------

# 29. Git Rules

Keep commits focused.

Good:

``` text
feat: add timetable retrieval API
fix: prevent expired announcements from retrieval
feat: add CR submission approval flow
```

Avoid giant commits containing unrelated changes.

Never commit:

-   Secrets.
-   API keys.
-   Credentials.
-   Personal data.
-   Generated build artifacts unless explicitly required.

------------------------------------------------------------------------

# 30. Change Management

Before modifying an existing feature:

1.  Understand why it exists.
2.  Find its consumers.
3.  Check API/database dependencies.
4.  Check tests.
5.  Make the smallest safe change.
6.  Run relevant tests.
7.  Verify no unrelated behavior changed.

Do not perform broad refactors during feature work unless necessary.

------------------------------------------------------------------------

# 31. Documentation

Update documentation when changing:

-   Architecture.
-   APIs.
-   Database schema.
-   Environment variables.
-   Deployment.
-   Ingestion flow.
-   AI routing.
-   Authentication.
-   Major UI flows.

Architecture decisions should be recorded under:

``` text
docs/decisions/
```

when the project structure supports it.

------------------------------------------------------------------------

# 32. Environment Variables

Use an example environment file.

Example:

``` text
.env.example
```

Document:

-   Variable name.
-   Purpose.
-   Whether required.
-   Where to obtain it.

Never expose actual secrets.

------------------------------------------------------------------------

# 33. Agent Workflow

For every task:

### Step 1 --- Understand

Read relevant files and determine existing behavior.

### Step 2 --- Plan

Identify:

-   Files to change.
-   APIs affected.
-   Database changes.
-   Security implications.
-   Tests required.

### Step 3 --- Implement

Make the smallest coherent change.

### Step 4 --- Validate

Run:

-   Type checks.
-   Lint.
-   Unit tests.
-   Integration tests where relevant.
-   Build checks.

### Step 5 --- Review

Check:

-   Security.
-   Authorization.
-   Data correctness.
-   Expiry.
-   Error handling.
-   Responsive UI.
-   Regressions.

### Step 6 --- Report

Summarize:

-   What changed.
-   Why.
-   Tests run.
-   Known limitations.

------------------------------------------------------------------------

# 34. When Requirements Are Ambiguous

Do not invent institutional rules.

If ambiguity affects architecture, security, permissions, or data
integrity:

-   Inspect existing documentation.
-   Inspect existing implementation.
-   Infer only when the repository provides evidence.
-   Otherwise clearly identify the assumption.

Prefer conservative behavior.

------------------------------------------------------------------------

# 35. Do Not Over-Engineer

ORION is a prototype.

Do not automatically introduce:

-   Kubernetes.
-   Kafka.
-   Complex event buses.
-   Multiple microservices.
-   Separate vector infrastructure.
-   Dedicated GPU clusters.
-   Complex agent frameworks.

unless the repository or requirements demonstrate a real need.

A simple architecture that works is preferable.

------------------------------------------------------------------------

# 36. AI Agent Safety

AI coding agents must never:

-   Remove authentication to make a feature work.
-   Disable authorization.
-   Expose environment secrets.
-   Hard-code credentials.
-   Bypass admin approval.
-   Store sensitive information unnecessarily.
-   Trust LLM output as authoritative data.
-   Delete production data without explicit requirements.
-   Replace working architecture without investigation.

------------------------------------------------------------------------

# 37. Preferred Architecture

For the prototype, a strong default is:

``` text
                 ORION
                   |
        +----------+----------+
        |                     |
    Frontend               Backend
        |                     |
        |              FastAPI / API
        |                     |
        |          +----------+----------+
        |          |          |          |
        |        Auth       Router    Ingestion
        |          |          |          |
        |          |          |       OCR/Extract
        |          |          |
        +----------+----------+
                   |
             PostgreSQL
              + pgvector
                   |
              Object Storage
```

The exact implementation may differ. Existing repository architecture
takes precedence.

------------------------------------------------------------------------

# 38. Priority of Decisions

When two approaches conflict, use this order:

1.  Explicit current project requirements.
2.  Security/privacy.
3.  Existing working architecture.
4.  Data correctness.
5.  SRS/product requirements.
6.  Maintainability.
7.  Cost.
8.  Developer convenience.

------------------------------------------------------------------------

# 39. Final Agent Checklist

Before declaring a task complete, verify:

``` text
[ ] Read repository context
[ ] Read README.md
[ ] Read AGENTS.md
[ ] Reused existing architecture/components
[ ] Authentication preserved
[ ] Authorization preserved
[ ] Sensitive data protected
[ ] Data expiry handled
[ ] Validation added
[ ] Error states handled
[ ] Loading states handled
[ ] Empty states handled
[ ] Tests added/updated
[ ] Existing tests pass
[ ] Build/type checks pass
[ ] Documentation updated if required
[ ] No secrets committed
[ ] No unnecessary dependencies added
[ ] No unnecessary infrastructure added
[ ] No hallucination-prone institutional data logic introduced
```

------------------------------------------------------------------------

# 40. Golden Rule

When working on ORION, always ask:

> **What is the authoritative source of this information, who is allowed
> to modify it, how long is it valid, and how can ORION prove that the
> answer is grounded in trusted data?**

If an implementation cannot answer those four questions, it should be
reconsidered before being merged.
