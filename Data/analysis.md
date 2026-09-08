# ORION Data Folder — Analysis & Ingestion Guide

> Generated: 2026-09-08 · Scope: `Data/Structured/` and `Data/Unstructured/`
> Purpose: single reference for implementing ORION's ingestion pipeline (§9 of README),
> source-of-truth routing (AGENTS.md §5), RAG chunking, expiry metadata, and sensitive-data screening.

---

## 1. Folder Summary

| Folder | Files | Total size | Nature | ORION destination |
|---|---|---|---|---|
| `Data/Structured/` | 10 PDFs | ~3.3 MB | Timetables, calendar, mess menu, rooms, hostel rules, wardens, NIRF data | **Mostly → PostgreSQL (structured tables)** + a few → vector KB |
| `Data/Unstructured/` | 17 PDFs | ~11.8 MB | Curriculum/syllabi, UG regulations, anti-ragging documents, verification procedures, placement deck | **Mostly → Vector KB (pgvector)** after chunking |

**Total extractable embedded text across the corpus: ~3.15 million characters (~750–800K tokens).**
This is small enough to index cheaply with `pgvector` on Supabase — no dedicated vector DB needed (AGENTS.md §14, §24).

### Extraction capability at a glance

| Extraction status | Count | Files |
|---|---|---|
| ✅ Embedded text, directly extractable | 20 | Everything except the 4 below |
| ⚠️ Embedded text but **CID/UTF-16 encoded** (needs a real PDF library, not naive extraction) | 2 | `august_menu .pdf`, `Wardens Team July 2026 - Students Copy.pdf` |
| ❌ **Scanned images — OCR required** | 4 | `Letter-UGC-Antiragging.pdf`, `OM-Anti Ragging Committee-Squad-Jan2024.pdf`, `UGC Regulations- Anti-Ragging - 2009.pdf`, plus partial: `Wardens Team` (mixed) |

All files are unencrypted. None are password-protected.

---

## 2. Data/Structured — File-by-File

These map to **deterministic facts** → relational tables (AGENTS.md §5, §14). Each becomes a seed dataset for Phase 1/2.

### 2.1 `Semester 3_TimeTable_Odd_2026.pdf` (384 KB, Word-generated, ~23.7K chars)

- **Content:** B.Tech Semester III timetable for **July–November 2026** (Odd sem). Grid: days × 9 periods (9:00 AM–7:00 PM with breaks). Multiple branch sections (CSE etc.) and batch sub-groups (dm/…), each with its own grid.
- **Embedded course-faculty table:** e.g. `IMA 211 PROBABILITY, STATISTICS … — Dr. Anandhu Mohan (ANM)`, `ICS 211 DESIGN AND ANALYSIS OF … — Dr. Priyadarshini (PS)`, `ISC 211 — Dr. Jayakrishna Sahoo (JS)`, labs co-taught (DSL/SSJ), etc.
- **Faculty identified by initials in grid cells** (ANM, DJ, PS, JS, VS, SR) — resolved via the legend table.
- **ORION mapping →**
  - `timetable_entries` (day, period, start/end time, course_code, course_name, faculty_id, room, semester=3, branch, batch, section)
  - `courses` (code, name, credits — credits appear as L-T-P-S pattern like `3-1-`)
  - `faculty` (name, initials alias, department)
- **Validity:** `valid_from = 2026-07`, `valid_until = 2026-11` (exam end per calendar). Status: `active` until replaced.
- **Extraction notes:** Text is extractable but table geometry is positional. Naive text dumps garble cell order; use a layout-aware parser (pdfplumber/PyMuPDF `page.find_tables()`). Font `ABCDEE+Garamond` subset — a real library handles it.
- **Risk:** highest-value file in the folder; must go through OCR-extraction → preview → admin approval before becoming authoritative (README §6).

### 2.2 `Semester 5_Timetable_Odd_2026.pdf` (747 KB, Word, ~18.6K chars)

- Same structure as S3. Semester V, July–Nov 2026. Periods 9:30 AM–6:30 PM (different slot times from S3 — **do not hard-code period times**).
- Faculty legend: `CSS 311 — Dr. Sushitha Susan Joseph (SSJ)`, `CSE 311 — Dr. Reetha Thomas (RT)`, `CSE 312 Software Architecture — Dr. Anitha Ambat (ANA)`, `IHS 311 — Dr. Mathew Joseph (MJH)`, `IHS313 — Dr. Kumaresan (KMG)`, `IEG 311 — DSP/QC`, `IMA 311 — Dr. Raghunadhan T (RGT)` etc.
- Contains typo in original ("FACULTLY") — normalization step should not propagate typos into DB fields.
- **ORION mapping:** same tables as 2.1, `semester = 5`.

### 2.3 `Semester 7_TimeTable_Odd_2026.pdf` (513 KB, Word, ~10.9K chars)

- Semester VII, July–Nov 2026. **Multiple branch grids in one file** (CSE + others; headers repeat per branch: `dm - DAYS`, `Adm - DAYS` …).
- Notable: project/BTP blocks (`IBP 411 BTP-I`), seminar slots (`SEMINAR/COLLOQUIUM`), electives (`IOE 414 — Dr. Anu Maria Sebastian (AMS)`).
- **ORION mapping:** same as above; note `entry_type` column (`class | lab | seminar | project | club_activity | sports`) — club/sports slots exist in all three timetables and should not be treated as classes.

### 2.4 `Odd 2026-27_academic_calendar.pdf` (325 KB, Excel 2019, ~4.0K chars)

- Month-grid calendar **Jul–Dec 2026** with events: class begins for higher semesters (Jul 20), Independence Day, semester registration, committee meetings, BTP first review week, mid-semester exams, Diwali, repeat exams, end-semester exams, result publication, registration opens for Even sem 2026-27, submission deadlines.
- Text extracts but the **grid layout is positional** (dates scattered). Needs table-aware parsing keyed on month columns.
- **ORION mapping →** `academic_calendar` (`event_name, event_date, event_type, applies_to_semester, valid_from, valid_until`).
- High-value for deterministic queries: "when do end-sem exams start", "is tomorrow a holiday".

### 2.5 `Classroom Details_ODD_Sem _July_Nov_2026.pdf` (14 KB, Excel 2016, ~1K chars)

- Room allocation per batch & branch: e.g. 2026 batch 1st sem → 4 large classrooms (`BB 204 B1`, `BC 304 B2`…), 2025 batch (S3) → `AA 126 AI&DS`, `AC 322 CSY`…; labs: CSE Lab I (BB 218), CSY Lab I (BD 418), ECE Lab I (AB 203), etc.
- **ORION mapping →** `rooms` + `room_allocations` (semester, batch, branch, room_no, type, validity = odd sem 2026).
- Feeds timetable answers ("where is my next class") — must be joined with timetable, never invented.

### 2.6 `august_menu .pdf` (97 KB, Word 2021, ⚠️ CID-encoded)

- Mess menu for **August 2026** (monthly/weekly + daily meals). Text layer exists but is UTF-16 CID-encoded (`<0030 0028 0036 0036>…`) — requires a proper PDF text extractor (PyMuPDF/pdfplumber) or OCR fallback. Naive extraction yields nothing.
- **ORION mapping →** `mess_menu` (`day, meal, items, week, valid_from=2026-08-01, valid_until=2026-08-31`).
- **Time-sensitive:** expires at end of month. September menu must replace it; expired menus must never be served as current (AGENTS.md §13).

### 2.7 `IIIT Kottayam - Hostel Rules and Regulations - July 2026 .pdf` (174 KB, Word, ~13.4K chars)

- Full hostel rulebook: movement/curfew (9:30 PM campus, 11:00 PM hostel), outpass via "Flee Outpass portal" (outpass.iiitkottayam.ac.in), leave rules, warden contacts, disciplinary process.
- Long-form prose → **vector KB**, not SQL. Chunk by section (rules are numbered `1.1`, `2.1` — natural chunk boundaries).
- **Classification:** `OFFICIAL / POLICY`. Validity: July 2026 edition — versioned document, replace on new edition.
- Contains portal URLs and contact emails → keep in chunks (useful for answers) but they are institution-level facts; if extracted into SQL, must be admin-approved.

### 2.8 `Wardens Team July 2026 - Students Copy.pdf` (612 KB, ⚠️ mixed encoding, 2 pages)

- Warden/hostel contact list. Only ~110 chars extractable naively (emails like `chiefwarden@iiitkottayam.ac.in`, `ad_sa@iiitkottayam.ac.in`, labels like "Maintenance related Issues"); names/roles are in CID-encoded runs (`<002F>…` = "Warden" etc.).
- Needs proper extractor or OCR. 8 embedded fonts (CIDFont+F1..F4).
- **ORION mapping →** `contacts` / hostel metadata (name, role, hostel, email). PII-adjacent: store only official role contact info, not personal phone numbers unless institutionally approved (AGENTS.md §11).
- Validity: July 2026 team — expires on reconstitution.

### 2.9–2.10 `IIITK_nirf2026_engineering.pdf` (50 KB) & `IIITK_nirf2026_overall.pdf` (54 KB, iTextSharp, ~32K + ~36K chars)

- NIRF 2026 submission data: intake by year, student strength (UG 1362 male/288 female etc.), state distribution, economically-backward & SC/ST/OBC counts, fee-reimbursement numbers, faculty counts, financials, facilities.
- Clean Helvetica text, fully extractable, tabular.
- **ORION mapping:** NOT student-facing priority. Index into vector KB as `INSTITUTIONAL / REPORT` with low retrieval priority, or store key figures in a `institution_stats` table. Good candidate for "How many students…?" questions.
- Contains no sensitive personal data (aggregated only) — safe.

---

## 3. Data/Unstructured — File-by-File

These map to **semantic knowledge** → chunk → embed → pgvector. All are institutionally official (no advertisement filtering needed in this set).

### 3.1 Curriculum & Syllabus documents (the big ones — ~2.1M chars, 68% of corpus)

| File | Program | Applies to | Pages | ~Chars |
|---|---|---|---|---|
| `CSE_ADM_2026.pdf` | B.Tech CSE | **2026 admission onwards** | 103 | 376K |
| `AI_DS_ADM_2026.pdf` | B.Tech CSE (AI & DS spl.) | 2026 admission onwards | 100 | 364K |
| `ECE_ADM_2026.pdf` | B.Tech ECE | 2026 admission onwards | 90 | 328K |
| `BMC_ADM_2026.pdf` | B.Tech Mathematics & Computing | 2026 admission onwards | 71 | 255K |
| `Cyber_ADM_2026.pdf` | B.Tech CSE (Cyber Sec. spl.) | 2026 admission onwards | 71 | 251K |
| `Annexure I_CSE 21-25.pdf` | B.Tech CSE | **2021–25 batch** | 51 | 177K |
| `Annexure II_AI&DS 21-25.pdf` | B.Tech AI&DS | 2021–25 batch | 56 | 195K |
| `Annexure III_ECE 21-25.pdf` | B.Tech ECE | 2021–25 batch | 55 | 205K |
| `Annexure IV_CY 21-25.pdf` | B.Tech Cyber | 2021–25 batch | 42 | 138K |

- All are LaTeX/pdfTeX-generated → **clean embedded text**, hyperlinked TOCs, ~2 images each (logos).
- **Structure:** PEOs → POs/PSOs → Curriculum summary → Programme structure (credit tables) → Semester-wise detailed syllabus (course code, title, credits, prerequisites, syllabus units, references).
- **ORION mapping:** two-layer strategy:
  1. **Structured:** parse course records into `courses` (code, title, credits, semester, programme, prerequisites, syllabus_summary). This powers deterministic "How many credits in X?", "prerequisites for Y?" and course browsing. These PDFs are the authoritative seed for the course catalog.
  2. **Vector:** chunk full syllabi for semantic queries ("which course covers reinforcement learning?").
- **⚠️ Version-critical:** two cohorts with different regulations coexist. **Metadata is mandatory** for retrieval filtering: `programme`, `specialisation`, `cohort = ADM2026 | 21-25`, `doc_type = curriculum | regulations`. A 2026-batch student must never get 21-25 syllabus answers and vice versa (AGENTS.md §13, §16; README §9.4).
- Chunking: split at course entries (e.g. `ICS 211 …`) and semester headers; ~500–800 token chunks with `course_code` + `semester` + `programme` metadata attached to each chunk.

### 3.2 `UG_Regulations 26 onwards.pdf` (410 KB, 35 pages, ~72K chars) & `UG Regulations 21-25.pdf` (317 KB, 22 pages, ~45K chars)

- The B.Tech ordinance/regulation guidebooks: admission (R.1), programme structure (R.2), registration/enrolment (R.3), faculty advisor/class committee (R.4), attendance (R.5), assessment & grading (R.6 — SGPA/CGPA rules), continuation requirements (R.7), degree requirements (R.8), summer term (R.9)…
- LaTeX text, clean. Reference IDs like `IIITK/Acad/Reg./Ver.VIII(ADM2026)/Senate15.10(h)/July2026` → excellent natural `source_id` + version metadata.
- **ORION mapping:** vector KB, `doc_type = regulations`, `cohort` filter as above. Prime RAG target: "What is the attendance requirement?", "How is CGPA computed?", "Can I take a summer term?".
- The 26-onwards version supersedes 21-25 for new students; keep both retrievable but **filtered by cohort**, and prefer latest for ambiguous queries.

### 3.3 `Transcript verification procedure.pdf` (400 KB, 1 page, ~1.2K chars)

- Transcript request & payment guidelines: request via academics1@ (UG) / academics4@ (PG), Rs. 750 fee, 7 working days, sealed envelope rules, international dispatch requirements.
- **ORION mapping:** vector KB (`doc_type = procedure`, `category = academics`). Small doc → 2–3 chunks. Note: fee amounts/deadlines are institutional facts — if featured in answers, cite the document.

### 3.4 `educational verification.pdf` (1.6 MB, 4 pages, ~1.6K chars, ⚠️ 133 image objects)

- Certificate authentication/verification procedure: email request + documents list, hard-copy route, agent authorization letter, Rs. 750 fee.
- Text layer exists (Cambria/Courier fonts) but 133 embedded images suggest scanned stamps/signatures interleaved with text — extract text, ignore images.
- **ORION mapping:** vector KB, `doc_type = procedure`. Low-traffic but useful.

### 3.5 Anti-ragging set (3 files)

| File | Size | Pages | Text? | Notes |
|---|---|---|---|---|
| `UGC Regulations- Anti-Ragging - 2009.pdf` | 1.7 MB | 54 | ❌ **None — full scan** (CCITTFax 1-bit fax-encoded, 54 page-images) | UGC anti-ragging regulations. Needs OCR (Tesseract/PaddleOCR per README §16). OCR output quality on fax-encoded scans is moderate → flag low-confidence pages for review (AGENTS.md §10). |
| `Letter-UGC-Antiragging.pdf` | 1.6 MB | 2 | ❌ None (DCTDecode/JPEG scans, 721 raw Tj ops are just scanner artifacts) | Scanned official letter (Canon scanner). OCR needed. |
| `OM-Anti Ragging Committee-Squad-Jan2024.pdf` | 324 KB | 1 | ❌ None (NAPS2 scan → PDFsharp) | Office memorandum naming the committee/squad members (Jan 2024). OCR needed. **Contains personal names + designations + possibly phone numbers → sensitive-data screen before publishing (AGENTS.md §11).** |

- **ORION mapping:** vector KB, `doc_type = policy / circular`, `category = anti-ragging`, `valid_from = 2009 / Jan-2024`.
- **Expiry consideration:** committee composition (Jan 2024 OM) is time-sensitive — stale rosters must not be presented as current. The 2009 UGC regulations are long-lived policy.
- These are the **OCR pilot corpus** for Phase 2 ingestion: 3 files, ~57 scanned pages, exercises the whole validation → OCR → confidence-flag → review pipeline.

### 3.6 `recruiterscorner.pdf` (14.3 MB — largest file, Word 2019, ~598K chars, 447+ pages, 588 images)

- Placement/recruiter showcase: "Topmost IIIT in India", stats (75+ faculty, 2100 students, 115 PhD scholars, 275 MTech working professionals), recruiter lists, innovation-culture narrative. Updated 27 Sept 2024.
- **ORION mapping:** ⚠️ treat with care:
  - It is a **promotional/marketing deck** — partially matches the "ADVERTISEMENT" class in AGENTS.md §12. It contains useful institutional facts (placement stats, recruiter names) wrapped in promotional language. Per policy: extract the factual content (recruiters, statistics, dated as of Sept 2024), do not index promotional prose as institutional knowledge.
  - **Staleness risk:** placement data from Sept 2024 is outdated for 2026 queries → either exclude from retrieval or tag `valid_until` and low priority.
  - 14 MB / 588 images: strip images before embedding; text-only indexing is ~600K chars.
- Decision needed from product owner: index as `PLACEMENTS / MARKETING` with strict recency filter, or exclude entirely from the knowledge base initially.

---

## 4. Cross-Cutting Ingestion Plan (maps to README §6 pipeline)

### 4.1 Classification table (AGENTS.md §12 classes)

| Class | Files |
|---|---|
| `TIMETABLE` | S3/S5/S7 timetables |
| `ACADEMIC` | Academic calendar, classroom details, curricula (9), regulations (2) |
| `OFFICIAL` | Hostel rules, transcript procedure, verification procedure |
| `POLICY` | UGC anti-ragging regulations + letter |
| `ANNOUNCEMENT` | Anti-ragging committee OM (roster) |
| `EVENT`/`MESS` | (august menu → `MESS`) |
| `ADVERTISEMENT`/`MARKETING` | recruiterscorner.pdf (partial — see 3.6) |
| `IRRELEVANT` | none |

### 4.2 Structured extraction targets (→ PostgreSQL)

| Target table | Source | Method |
|---|---|---|
| `timetable_entries`, `courses`, `faculty` | 3 timetable PDFs | Layout-aware table extraction (pdfplumber/PyMuPDF) → **preview → CR/admin approval** |
| `academic_calendar` | Odd 2026-27 calendar | Month-grid parser |
| `rooms`, `room_allocations` | Classroom details | Table parser (simple) |
| `mess_menu` | august menu | Text extraction (CID-aware) or OCR → day/meal normalization |
| `institution_stats` (optional) | NIRF PDFs | Table parser or manual seed |

### 4.3 Vector indexing targets (→ pgvector)

| Corpus | ~Chunks (500–800 tok) | Metadata to attach |
|---|---|---|
| 9 curriculum/syllabus PDFs | ~1,400–1,800 | programme, specialisation, cohort, semester, course_code, doc_type |
| 2 UG regulation books | ~150 | cohort, version_id (Senate ref), doc_type |
| Hostel rules | ~20 | doc_type, edition (July 2026), section numbers |
| Procedures (transcript, verification) | ~6 | doc_type, category |
| Anti-ragging set (after OCR) | ~80–120 | doc_type, year, confidence_score |
| recruiterscorner (if approved) | ~800 (text-only) | datestamp, class=MARKETING, low priority |
| NIRF reports (if vectorized) | ~90 | year, class=REPORT |

**Estimated total vector corpus: ~2,500–3,000 chunks.** Trivial for pgvector with HNSW on a free-tier Postgres.

### 4.4 OCR queue (Phase 2)

1. `UGC Regulations- Anti-Ragging - 2009.pdf` — 54 pages, CCITT fax scans → preprocess (deskew, binarize) → Tesseract/PaddleOCR → confidence per page → human review for low-confidence pages (AGENTS.md §10).
2. `Letter-UGC-Antiragging.pdf` — 2 JPEG scans.
3. `OM-Anti Ragging Committee-Squad-Jan2024.pdf` — 1 scan; **sensitive-data screen** (names/phones) before release.
4. Fallback OCR for `august_menu .pdf` and `Wardens Team…pdf` if the CID extraction path is not built first.

### 4.5 Expiry metadata plan (AGENTS.md §13)

| Data | valid_from | valid_until | Replacement rule |
|---|---|---|---|
| Timetables | 2026-07 | 2026-11 (per calendar: exams end + result publication) | New PDF replaces; archive old |
| Academic calendar | 2026-07-01 | 2026-12-31 | Even-sem calendar supersedes |
| Mess menu | 2026-08-01 | 2026-08-31 | Monthly upload |
| Classroom allocation | 2026-07 | 2026-11 | Each odd/even sem |
| Wardens team | 2026-07 | Until reconstitution notice | Admin-managed |
| Curricula (ADM 2026) | 2026 admission | Until revised | Versioned by cohort |
| Regulations 26-onwards | 2026-07 (Senate 15.10) | Until new Senate version | Version-controlled |
| Regulations 21-25 | 2021 | Archived for 21-25 cohort | Cohort-filtered |
| Anti-ragging regs 2009 | 2009 | Long-lived | Manual |
| Committee roster Jan 2024 | 2024-01 | **Likely stale — verify** | Flag for admin review |
| recruiterscorner | 2024-09-27 | Stale for placements | Low priority / exclude |

### 4.6 Sensitive-data screening results (AGENTS.md §11)

- ✅ No government IDs, financial records, medical data, or credentials detected in any file.
- ⚠️ `OM-Anti Ragging Committee-Squad-Jan2024.pdf` — personal names/designations of committee members (public-role info, but screen phone numbers).
- ⚠️ `Wardens Team July 2026` — official contact emails only; do not ingest personal numbers if present after OCR.
- ✅ NIRF data is aggregated (no individuals).
- ✅ Curriculum/regulations contain no personal data.

### 4.7 Recommended processing order (Phase 1 → 2)

1. **S3/S5/S7 timetables + classroom details + calendar** → structured tables (highest student value, deterministic answers).
2. **2 UG regulation books + 9 curricula** → vector KB with cohort metadata (highest RAG value).
3. **Hostel rules, transcript & verification procedures** → vector KB (small, easy wins).
4. **Mess menu** → structured (needs CID extractor or OCR).
5. **Anti-ragging scans** → OCR pipeline pilot with confidence flags.
6. **NIRF + recruiterscorner** → optional/deferred; decide on placement content with product owner.

---

## 5. Tooling Notes (from this analysis)

- All PDFs are **unencrypted**; embedded text exists in 23/27 files.
- Naive `zlib`-stream text extraction works for the LaTeX/Word/Helvetica files but **fails silently on CID/UTF-16 subset fonts** (`august_menu`, `Wardens Team`, parts of Word-generated timetables' headers). **Use a real PDF library** — recommended: `pypdf` (pure-Python, free) for text, `pdfplumber` or `PyMuPDF` for table geometry. Both are free/open-source and fit the zero-cost constraint (README §16, AGENTS.md §24).
- The analysis script used for this audit is committed at `scripts/inspect_data_pdfs.py` (dependency-free, read-only) — rerun after adding new files: `python3 scripts/inspect_data_pdfs.py`.
- Page counts show `0` for several files because they use object-stream (compressed xref) structures; the count method is a heuristic. Authoritative page counts for the LaTeX files were read from their TOC structure (e.g. CSE_ADM = 103 pages).

---

## 6. Open Questions for Product Owner

1. **recruiterscorner.pdf** — index placements content (with Sept-2024 staleness tag) or exclude as marketing? (README §12 policy suggests extracting facts, excluding prose.)
2. **Committee roster (Jan 2024)** — verify current composition with admin before publishing, or publish with a "verify at office" caveat.
3. **Cohort model** — confirm ORION stores `admission_year` on user profiles so curriculum/regulation retrieval can filter 21-25 vs 26-onwards correctly (AGENTS.md §17 personalization fields).
4. **Even-semester data** — folder only covers Odd 2026-27; Even-sem timetables/calendar will be needed by Dec 2026 (per calendar: registration opens Nov).
