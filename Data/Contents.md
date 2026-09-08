# Data Folder Contents & RAG Analysis

## Repository: ORION --- AI-Powered Campus Assistant
**Source**: Data/ directory under `/Users/johnsonoduri/Coding/orion-campus-nest`

---

## Purpose

This document provides a detailed analysis of all files in the `Data/` directory, categorized by type and RAG (Retrieval-Augmented Generation) relevance. This analysis supports the implementation of ORION's document ingestion, vector search, and structured data pipelines as defined in `AGENTS.md` and `README.md`.

---

## Data/Structured (10 files)

*Deterministic facts best stored in PostgreSQL. Timetable data should be converted to structured records whenever possible.*

| File | Type | RAG Relevance | Extraction Priority |
|------|------|---------------|---------------------|
| `august_menu .pdf` | Mess Menu | Daily/weekly validity → structured DB | Medium |
| `Classroom Details_ODD_Sem _July_Nov_2026.pdf` | Classroom info | Room assignments → structured records | High |
| `IIIT Kottayam - Hostel Rules and Regulations - July 2026 .pdf` | Hostel rules | Policy document → vector + structured metadata | High |
| `IIITK_nirf2026_engineering.pdf` | NIRF ranking | Static semantic retrieval | Low |
| `IIITK_nirf2026_overall.pdf` | NIRF overall | Static semantic retrieval | Low |
| `Odd 2026-27_academic_calendar.pdf` | Academic calendar | Semester dates, holidays → structured + semantic | High |
| `Semester 3_TimeTable_Odd_2026.pdf` | Timetable (Sem 3) | **Convert to PostgreSQL records** (critical) | Critical |
| `Semester 5_Timetable_Odd_2026.pdf` | Timetable (Sem 5) | **Convert to PostgreSQL records** (critical) | Critical |
| `Semester 7_TimeTable_Odd_2026.pdf` | Timetable (Sem 7) | **Convert to PostgreSQL records** (critical) | Critical |
| `Wardens Team July 2026 - Students Copy.pdf` | Warden info | Semantic retrieval for contact hierarchy | Medium |

**Structured Data Pipeline** (per AGENTS.md:§7, §117-129, §276):
- Extract tables → PostgreSQL records with lifecycle metadata
- Fields: `id`, `course_code`, `day`, `slot_index`, `start_time`, `end_time`, `room`, `faculty_name`, `batch_semester`, `valid_from`, `valid_until`, `status`, `source_id`, `approved_at`, `approved_by`, `created_at`, `updated_at`
- **Do NOT** index raw OCR into vector DB
- Vector index only minimal metadata for filtering

**Lifecycle Metadata** (per AGENTS.md:467-499):
```
created_at, updated_at, valid_from, valid_until, status, source_id, approved_at, approved_by
```

---

## Data/Unstructured (17 files)

*Semantic/regulatory documents for vector retrieval. Must detect/redact sensitive information (AGENTS.md:§11).*

| File | Type | RAG Relevance | Priority |
|------|------|---------------|----------|
| `AI_DS_ADM_2026.pdf` | Admission/Course doc | Semantic course regulations | High |
| `Annexure I_CSE 21-25.pdf` | CSE annexure | Department-specific docs | High |
| `Annexure II_AI&DS 21-25.pdf` | AI&DS annexure | Department-specific docs | High |
| `Annexure III_ECE 21-25.pdf` | ECE annexure | Department-specific docs | High |
| `Annexure IV_CY 21-25.pdf` | CY annexure | Cross-department docs | Medium |
| `BMC_ADM_2026.pdf` | BMC admission | Batch admission info | Medium |
| `CSE_ADM_2026.pdf` | CSE admission | Department-specific admission | High |
| `Cyber_ADM_2026.pdf` | Cyber security | Policy document | Medium |
| `ECE_ADM_2026.pdf` | ECE admission | Department-specific admission | High |
| `educational verification.pdf` | Verification proc | Student services procedures | High |
| `Letter-UGC-Antiragging.pdf` | Anti-ragging letter | **CRITICAL** - compliance requirement | Critical |
| `OM-Anti Ragging Committee-Squad-Jan2024.pdf` | Anti-ragging committee | **CRITICAL** - compliance requirement | Critical |
| `recruiterscorner.pdf` | Recruitment | Placement information | Low |
| `Transcript verification procedure.pdf` | Transcript proc | Student services | High |
| `UG Regulations 21-25.pdf` | Undergrad regs | **CRITICAL** - academic policy | Critical |
| `UG_Regulations 26 onwards.pdf` | New UG regs | **CRITICAL** - academic policy | Critical |
| `UGC Regulations- Anti-Ragging - 2009.pdf` | Anti-ragging UGC | **CRITICAL** - compliance | Critical |

**Unstructured Data Pipeline** (per AGENTS.md:§8, §11, §12):
1. PDF → OCR → Text cleaning
2. **Sensitive data detection & redaction** (AGENTS.md:299-317):
   - Govt ID numbers → REDACT
   - Financial data → REDACT
   - Medical data → REDACT
   - Private personal info → REDACT
   - Student disciplinary info → REDACT/REJECT
3. Chunking into logical sections
4. Metadata enrichment (department, version, validity, classification)
5. Embedding → Vector index
6. Metadata filters: `department`, `valid_from`, `valid_until`, `status`, `source_id`, `approved_at`, `approved_by`

**Advertisement Classification** (per AGENTS.md:325-337):
Classify content into: `OFFICIAL`, `ACADEMIC`, `ANNOUNCEMENT`, `EVENT`, `TIMETABLE`, `CLUB`, `DOCUMENT`, `ADVERTISEMENT`, `IRRELEVANT`
- Pure advertisements should NOT enter searchable knowledge base
- Legitimate institutional info inside notices should NOT be discarded

**Critical Policy Docs** (require special handling):
- `Letter-UGC-Antiragging.pdf` + `OM-Anti Ragging Committee-Squad-Jan2024.pdf` → Must be indexed, anti-ragging info extracted
- `UG Regulations 21-25.pdf` + `UG_Regulations 26 onwards.pdf` → Both versions must coexist, new supersedes old
- All anti-ragging documents → compliance-critical, must provide source references

---

## RAG Pipeline Requirements (per AGENTS.md:§16)

```
Query → Intent Classification → Metadata Filtering → Retrieval → Reranking → Context Assembly → LLM Generation → Validation/Citation → Response
```

### Intent Classification Categories

| Category | Description | Example Query | Retrieval Method |
|----------|-------------|---------------|------------------|
| **Structured** | Deterministic facts from database | "What classes do I have at 10 AM?" | SQL / Domain APIs |
| **Semantic** | Long-form documents, policies | "What are the rules for course withdrawal?" | Vector Search |
| **Hybrid** | Both structured facts + semantic context | "Who teaches NLP and when can I meet them?" | SQL + Vector + Timetable |

### Prohibited LLM Behavior (per AGENTS.md:158-175, §453-463)

**Never silently invent:**
- Faculty schedules
- Room numbers
- Exam dates
- Timetable entries
- Official deadlines
- Announcements
- Registration links

**Safe behavior**: If reliable information cannot be retrieved, say so.

### Metadata Filtering (per AGENTS.md:446-448, §376-377)

**Apply before/while searching:**
- `batch` constraints (e.g., "2022-2026", "Odd 2026-27")
- `department` constraints (e.g., "CSE", "ECE", "All")
- `role` constraints (STUDENT, FACULTY, CR, ADMIN)
- `valid_until` > current date (exclude expired)
- `status` = "active" (exclude superseded/archived)

**Expired data must NOT be presented as current information.**
When indexing documents into vector search, metadata filters must prevent expired documents from being retrieved as current information.

---

## CR Data Workflow (per AGENTS.md:§8)

```
Upload → Validation → OCR/Extraction → Preview → Submit → Pending → Admin Review → Approve/Reject → Publish
```

**Key Rules:**
- Rejected submissions must preserve a reason (AGENTS.md:239)
- Approved changes must be auditable (AGENTS.md:241)
- CRs are contributors, NOT authoritative administrators
- **Never**: `CR upload -> immediate production database mutation`
- Full audit trail: who uploaded/approved/rejected, when, what changed, previous version

**Submission Metadata** (track throughout workflow):
```
submitted_by, file_name, file_type, extraction_status, extraction_confidence (0-100%), 
content_classification (OFFICIAL/ACADEMIC/EVENT/TIMETABLE/CLUB/DOCUMENT/ADVERTISEMENT/IRRELEVANT),
rejection_reason, approval_status, approved_at, approved_by, published_at
```

---

## Expiry & Freshness (per AGENTS.md:§13)

Every time-sensitive record should have lifecycle metadata:

| Data Type | Lifecycle |
|-----------|-----------|
| Announcement | Explicit expiry date |
| Event | Expires after event |
| Exam | Expires after examination period |
| Timetable | Valid until replaced |
| Mess menu | Daily/weekly validity |
| Batch group link | Default expiry after 6 months unless renewed |
| Faculty achievement | Long-lived/manual update |
| Institute document | Manual/version-controlled |
| Club event | Expires after completion |

**Expired information must NOT be presented as current.**
When indexing into vector search, metadata filters must prevent expired retrieval.

---

## Sensitive Information Filtering (per AGENTS.md:§11)

Reject/redact where appropriate:
- Government identification numbers
- Personal financial information
- Medical information
- Passwords
- Authentication tokens
- Financial data
- Private personal information
- Confidential internal information
- Student disciplinary information

**Data minimization**: Store only information necessary for ORION's intended functionality.

---

## Implementation Priority Order

| Priority | Data Type | Target Storage | RAG Treatment |
|----------|-----------|----------------|---------------|
| **1** | Anti-ragging/Regulation PDFs | PostgreSQL + Vector DB | Vector search with strict metadata filters |
| **2** | Timetable PDFs (3 semesters) | PostgreSQL only | Structured records - NO raw OCR in vector |
| **3** | Academic Calendar | PostgreSQL + Vector DB | Hybrid: structured dates + semantic chunks |
| **4** | Admission/Course PDFs | PostgreSQL + Vector DB | Department-specific vector chunks |
| **5** | Mess Menu | PostgreSQL only | Structured records with daily/weekly validity |
| **6** | Faculty/Warden Info | PostgreSQL + Vector DB | Hybrid: structured records + semantic research |
| **7** | Clubs/Events/Announcements | PostgreSQL + Vector DB | Role/batch/department filtered retrieval |

---

## Query Routing Examples

### Example 1: Structured Query
- **User**: "What classes do I have at 10 AM?"
- **Context**: Student authenticated, branch: CSE, semester: 6
- **Routing**: SQL query on timetable entries
- **Answer**: "You have CS312 Computer Networks in LH-1 from 10:00-10:55" (from PostgreSQL)
- **Do NOT** use vector search (per AGENTS.md:456-463)

### Example 2: Semantic Query
- **User**: "What are the rules for course withdrawal?"
- **Routing**: Vector search on UG Regulations docs
- **Answer**: Retrieve from `UG Regulations 21-25.pdf` or `UG_Regulations 26 onwards.pdf`
- **Provide source reference** (per AGENTS.md:449)

### Example 3: Hybrid Query
- **User**: "Who teaches courses related to NLP and when can I meet them?"
- **Routing**: Hybrid - SQL faculty data + vector research interests + timetable
- **Answer**: "Dr. Rekha Nair teaches CS304 (ML) and CS318 (Lab), research: Deep Learning, Vision. Office hours: Mon-Wed 3-5 PM."
- **Per AGENTS.md:430-434**: "Use faculty data + research information + timetable/availability"

### Example 4: Expiry-Filtered Query
- **User**: "What announcements are relevant to me?"
- **Context**: Student, batch: 2022-2026, department: CSE
- **Routing**: Vector search + metadata filters
- **Filters**: `batch` matches or null, `department` = "CSE" OR null, `valid_until` > current date, `status` = "active"
- **Per AGENTS.md:376-377**: "When indexing documents into vector search, metadata filters must prevent expired documents from being retrieved as current information"

### Example 5: Prohibited - LLM Inventing
- **User**: "When is the Machine Learning exam?"
- **Prohibited**: LLM hallucinating a date
- **Required**: SQL query on `exams` table → "Machine Learning exam is on 18 Aug 2026, 09:30-11:30, Hall A"
- **Per AGENTS.md:158-175**: "Never Hallucinate Institutional Facts"

---

## File Extraction Pipelines

### Timetable PDFs → PostgreSQL Records

```
PDF → OCR → Table Detection → Row/Column Extraction → Structured Record → PostgreSQL
```

### Anti-Ragging/Regulation PDFs → Vector-Indexed Text Chunks

```
PDF → OCR → Text Cleaning → Sensitive Data Detection → Redact/Reject → Chunking → Metadata Enrichment → Embedding → Vector Index
```

### Admission/Course PDFs → Department-Specific Vector Chunks

```
PDF → OCR → Department Tagging → Key Information Extraction → Chunking → Metadata → Embedding
```

### Academic Calendar → Structured + Semantic Hybrid

```
PDF → OCR → Date/Event Extraction → Structured Records (PostgreSQL) → Semantic Chunks (Vector Index)
```

### Mess Menu → Daily Validity Structured Records

```
PDF → OCR → Meal/Item Extraction → Structured Record → PostgreSQL with valid_from/valid_until
```

### CR Submission Workflow

```
Upload → Validation → OCR/Extraction → Preview → Submit → Pending → Admin Review → Approve/Reject (with reason) → Publish → Audit log
```

---

## Directory Structure

```
/Data/
├── Structured/          (10 PDFs - deterministic facts)
│   ├── august_menu .pdf
│   ├── Classroom Details_ODD_Sem _July_Nov_2026.pdf
│   ├── IIIT Kottayam - Hostel Rules and Regulations - July 2026 .pdf
│   ├── IIITK_nirf2026_engineering.pdf
│   ├── IIITK_nirf2026_overall.pdf
│   ├── Odd 2026-27_academic_calendar.pdf
│   ├── Semester 3_TimeTable_Odd_2026.pdf
│   ├── Semester 5_Timetable_Odd_2026.pdf
│   ├── Semester 7_TimeTable_Odd_2026.pdf
│   └── Wardens Team July 2026 - Students Copy.pdf
└── Unstructured/        (17 PDFs - semantic/regulatory)
    ├── AI_DS_ADM_2026.pdf
    ├── Annexure I_CSE 21-25.pdf
    ├── Annexure II_AI&DS 21-25.pdf
    ├── Annexure III_ECE 21-25.pdf
    ├── Annexure IV_CY 21-25.pdf
    ├── BMC_ADM_2026.pdf
    ├── CSE_ADM_2026.pdf
    ├── Cyber_ADM_2026.pdf
    ├── ECE_ADM_2026.pdf
    ├── educational verification.pdf
    ├── Letter-UGC-Antiragging.pdf
    ├── OM-Anti Ragging Committee-Squad-Jan2024.pdf
    ├── recruiterscorner.pdf
    ├── Transcript verification procedure.pdf
    ├── UG Regulations 21-25.pdf
    ├── UG_Regulations 26 onwards.pdf
    └── UGC Regulations- Anti-Ragging - 2009.pdf
```

---

## Key Principles (from AGENTS.md & README.md)

1. **Use structured database data for**: Timetables, courses, faculty schedules, exam schedules, academic calendar, mess schedules, event dates, club metadata, user profiles, roles, announcements with structured metadata (AGENTS.md:117-129)

2. **Use vector retrieval for**: Long-form institute documents, regulations, policies, circulars, OCR text, notices, semantic faculty research information, other approved unstructured content (AGENTS.md:131-140)

3. **Use hybrid retrieval when**: A query needs both structured facts and semantic context (AGENTS.md:142-155)

4. **Never hallucinate institutional facts**: Room numbers, faculty availability, exam dates, timetable entries, course information, deadlines, official links, announcements, event dates (AGENTS.md:158-175)

5. **Data expiry**: Every time-sensitive record needs `valid_from`/`valid_until` metadata. Expired data must NOT be presented as current (AGENTS.md:346-377)

6. **Sensitive information**: Redact Govt IDs, financial, medical, personal data before ingestion (AGENTS.md:299-317)

7. **Advertisement filtering**: Classify as OFFICIAL/ACADEMIC/EVENT/TIMETABLE/CLUB/DOCUMENT/ADVERTISEMENT/IRRELEVANT. Pure ads should NOT enter knowledge base (AGENTS.md:321-343)

8. **CR workflow**: Upload → Validate → OCR → Preview → Submit → Pending → Admin Review → Approve/Reject (with reason) → Publish (AGENTS.md:207-241)

9. **Auditability**: Log who uploaded/approved/rejected, when, what changed, previous version (AGENTS.md:751-774)

10. **RAG pipeline**: Intent classification → Metadata filtering → Retrieval → Reranking → Context assembly → LLM generation → Validation/citation → Response (AGENTS.md:426-451)