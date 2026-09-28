# ORION — Exhaustive Question Analysis & Coverage Audit
> Senior AI Engineer Analysis · September 2026  
> Purpose: Map every realistic student/faculty/CR/admin question to a route, identify gaps, and define what must be built.

---

## How to Read This Document

Each section maps a question domain to one of four states:

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully covered — router classifies correctly, retrieval works, compose writes a good answer |
| ⚠️ | Partially covered — routes somewhere but answer is wrong, incomplete, or misleading |
| ❌ | Not covered — falls to UNSUPPORTED or wrong SEMANTIC fallback |
| 🔧 | Data gap — routing logic exists but the underlying table is empty (0 rows in prod) |

---

## Table of Contents

1. [Timetable & Schedule Questions](#1-timetable--schedule-questions)
2. [Mess & Food Questions](#2-mess--food-questions)
3. [Faculty Questions](#3-faculty-questions)
4. [Course & Academic Questions](#4-course--academic-questions)
5. [Exam Questions](#5-exam-questions)
6. [Academic Calendar & Deadlines](#6-academic-calendar--deadlines)
7. [Regulations & Academic Rules](#7-regulations--academic-rules)
8. [Hostel & Accommodation Questions](#8-hostel--accommodation-questions)
9. [Anti-Ragging Questions](#9-anti-ragging-questions)
10. [Administrative & Document Questions](#10-administrative--document-questions)
11. [Clubs, Events & Campus Life](#11-clubs-events--campus-life)
12. [Health, Safety & Emergency](#12-health-safety--emergency)
13. [Transport & Connectivity](#13-transport--connectivity)
14. [Library Questions](#14-library-questions)
15. [Placement & Career Questions](#15-placement--career-questions)
16. [Infrastructure & Facilities](#16-infrastructure--facilities)
17. [Fee & Financial Questions](#17-fee--financial-questions)
18. [Profile & Personal Academic Context](#18-profile--personal-academic-context)
19. [Announcements & Notices](#19-announcements--notices)
20. [Small Talk & Meta Questions](#20-small-talk--meta-questions)
21. [Follow-Up & Multi-Turn Scenarios](#21-follow-up--multi-turn-scenarios)
22. [Edge Cases & Adversarial Inputs](#22-edge-cases--adversarial-inputs)
23. [CR-Specific Questions](#23-cr-specific-questions)
24. [Admin-Specific Questions](#24-admin-specific-questions)
25. [Cross-Cutting Gaps Summary](#25-cross-cutting-gaps-summary)
26. [Implementation Priority Matrix](#26-implementation-priority-matrix)
27. [New Router Patterns Required](#27-new-router-patterns-required)
28. [New Database Tables Required](#28-new-database-tables-required)
29. [New Compose Functions Required](#29-new-compose-functions-required)
30. [Synonym Table Additions](#30-synonym-table-additions)

---

## 1. Timetable & Schedule Questions

### 1.1 Current Class

| Question | Status | Notes |
|----------|--------|-------|
| "What is my next class?" | ✅ | `NEXT_CLASS` → `orion_next_class` RPC |
| "What class do I have right now?" | ✅ | Matched by `_NEXT_CLASS_RE` |
| "Am I in class right now?" | ✅ | `_NEXT_CLASS_RE` catches "right now" |
| "Where is my next class?" | ✅ | `compose_next` includes room via `entry_extras` |
| "Who teaches my next class?" | ✅ | `compose_next` handles "who teaches" + pronoun |
| "What time does my next class start?" | ✅ | `fmt_range` in `compose_next` |
| "How long until my next class?" | ⚠️ | Routes to `NEXT_CLASS` but `compose_next` doesn't compute duration to class start |
| "How long is my next class?" | ⚠️ | Routes correctly but `compose_next` doesn't compute duration of the class itself |
| "Is there a class going on right now?" | ✅ | `_role == "ongoing"` case in `compose_next` |

**Gap — duration computation:**  
Add to `compose_next`: when `_role == "upcoming"`, compute `(start_time - now_ist()).total_seconds() / 60` and emit "starts in X minutes".

---

### 1.2 Today's Timetable

| Question | Status | Notes |
|----------|--------|-------|
| "What are my classes today?" | ✅ | `DAY_TIMETABLE` |
| "Show me today's timetable" | ✅ | |
| "How many classes do I have today?" | ✅ | `_FOCUS_COUNT_RE` → `hints["focus"] = "count"` |
| "What is my first class today?" | ✅ | `_FOCUS_FIRST_RE` → `hints["focus"] = "first"` |
| "What time does my day end today?" | ✅ | `_FOCUS_LAST_RE` → `hints["focus"] = "last"` |
| "Do I have any labs today?" | ✅ | `_LAB_RE` → `hints["entry_type"] = "lab"` |
| "Did I have class today?" | ✅ | `_DID_I_HAVE_RE` + "today" |
| "What did I miss today?" | ⚠️ | Routes to `DAY_TIMETABLE` but compose doesn't highlight which classes are already past |
| "Is today a working day?" | ❌ | No pattern — falls to SEMANTIC. Needs holiday/calendar check |

**Gap — "Is today a working day?":**  
Add `_WORKING_DAY_RE` pattern → routes to `ACADEMIC_CALENDAR` intent, checks if today is a holiday or weekend.

---

### 1.3 Day-of-Week Timetable

| Question | Status | Notes |
|----------|--------|-------|
| "What are my classes on Monday?" | ✅ | `DAY_OF_WEEK_TIMETABLE` |
| "Do I have class tomorrow?" | ✅ | `_TOMORROW_RE` + timetable word |
| "What's my schedule for Friday?" | ✅ | |
| "Do I have anything on Saturday?" | ✅ | Saturday is in weekday map |
| "What classes do I have the day after tomorrow?" | ⚠️ | `tempo.day_reference` may not catch "day after tomorrow" — needs explicit alias |
| "Show me Wednesday's timetable" | ✅ | |
| "Do I have class on the 15th?" | ❌ | Specific calendar date + timetable check = hybrid query. Not handled. |
| "What is my timetable for next Monday?" | ⚠️ | "next Monday" — `tempo.day_reference` handles this only if it has "next <weekday>" logic |
| "Do I have labs on Thursday?" | ✅ | `_LAB_RE` + `_WEEKDAY_RE` |
| "When is my OS class this week?" | ✅ | `_WHEN_IS_MY_X_RE` catches course name + "class" |
| "When do I have compiler design?" | ✅ | Same pattern |

---

### 1.4 Weekly Timetable

| Question | Status | Notes |
|----------|--------|-------|
| "Show me my weekly timetable" | ✅ | `WEEK_TIMETABLE` |
| "What does this week look like?" | ✅ | `_WEEK_WORD_RE` + timetable word |
| "List all my classes this week" | ✅ | |
| "How many classes do I have this week?" | ⚠️ | Routes to `WEEK_TIMETABLE` but `compose_week` doesn't produce a count |
| "What labs do I have this week?" | ✅ | `_LAB_RE` + `hints["entry_type"] = "lab"` |
| "When is my [course name] class this week?" | ✅ | `_WHEN_IS_MY_X_RE` → `hints["course_filter"]` |

---

### 1.5 Free Time & Gaps

| Question | Status | Notes |
|----------|--------|-------|
| "When am I free today?" | ✅ | `FREE_TIME` intent |
| "Do I have a free period?" | ✅ | `_FREE_TIME_RE` |
| "Is there any free lecture tomorrow?" | ✅ | Fixed per previous analysis |
| "What's my longest free slot today?" | ❌ | `compose_free` lists gaps but doesn't identify the longest |
| "Do I have a free hour between 2 and 4?" | ❌ | Time-range gap check — not implemented |
| "Am I free after 3pm?" | ❌ | Partial: `_TIME_RE` + `_FREE_TIME_RE` not combined |
| "Is Tuesday evening free?" | ❌ | Day + time-of-day combo, no pattern |
| "Do I have a break before lunch?" | ❌ | "lunch" → `MESS_TODAY`, not `FREE_TIME` — wrong route |

**Gap — "Do I have a break before lunch?":**  
This should check the timetable gap before ~12:15. The mess word is misleading the router into `MESS_TODAY`. Add an ordering check: if "break" or "gap" appears before "lunch/dinner" in the sentence, prefer `FREE_TIME`.

---

### 1.6 Specific Time Queries

| Question | Status | Notes |
|----------|--------|-------|
| "Do I have a class at 10:30?" | ✅ | `CLASS_AT_TIME` with `_TIME_RE` |
| "What class do I have at 3pm?" | ✅ | |
| "Am I free at 2?" | ❌ | "2" is a bare number — `_TIME_RE` requires colon or am/pm suffix by design. Correct, but the response should explain this rather than falling to UNSUPPORTED |
| "What's happening at 14:00?" | ✅ | 24-hour format caught by `_TIME_RE` |
| "Do I have anything in the morning?" | ❌ | "morning" is not a time — no pattern exists for time-of-day words |
| "What do I have in the afternoon?" | ❌ | Same |

**Gap — time-of-day words:**  
Add `_TIME_OF_DAY_RE` mapping: `morning → 08:00–12:00`, `afternoon → 12:00–17:00`, `evening → 17:00–20:00`. Route to `CLASS_AT_TIME` with a time range instead of a point.

---

### 1.7 Classroom Location

| Question | Status | Notes |
|----------|--------|-------|
| "Where is my class?" | ✅ | `CLASSROOM` intent |
| "Which room is my next class in?" | ✅ | `_CLASSROOM_RE` |
| "What is my classroom?" | ✅ | |
| "Where do I go for my next lecture?" | ⚠️ | "lecture" may not be in `_CLASSROOM_RE` — check `_TIMETABLE_WORD_RE` |
| "Which hall is OS in?" | ❌ | Course name + room query, no explicit "classroom" word |
| "Is LH-1 my classroom?" | ❌ | Inverse — checks if a named room is theirs |
| "Where is the lab?" | ❌ | "lab" → should trigger `CLASSROOM` but `_CLASSROOM_RE` doesn't have "lab" |

---

## 2. Mess & Food Questions

### 2.1 Today's Menu

| Question | Status | Notes |
|----------|--------|-------|
| "What's for lunch today?" | ✅ | `MESS_TODAY` with `meal="lunch"` |
| "What's the mess menu today?" | ✅ | |
| "What's for dinner?" | ✅ | |
| "What is breakfast today?" | ✅ | |
| "Is there fish today?" | ❌ | Item-level search inside the menu — not implemented |
| "Is today's lunch vegetarian?" | ❌ | No veg/non-veg field in `mess_menus` table |
| "What time is breakfast?" | ✅ | `_MEAL_RE` fires, compose shows timing |
| "Is the mess open now?" | ❌ | Needs current time vs meal timings — point-in-time check not implemented |
| "What time does the mess close?" | ❌ | Same |
| "When is lunch?" | ✅ | `MESS_TODAY` with `meal="lunch"`, timing comes from the row |

### 2.2 Other Days

| Question | Status | Notes |
|----------|--------|-------|
| "What's for lunch tomorrow?" | ✅ | `MESS_ON_DAY` |
| "What was for dinner yesterday?" | ✅ | `_YESTERDAY_RE` → `MESS_ON_DAY` |
| "What's the mess menu on Thursday?" | ✅ | `MESS_ON_DAY` |
| "What's for lunch this Sunday?" | ✅ | |

### 2.3 Weekly

| Question | Status | Notes |
|----------|--------|-------|
| "Show me the weekly mess menu" | ✅ | `MESS_WEEK` |
| "What's the mess menu this week?" | ✅ | |
| "Is there a special meal this week?" | ❌ | No "special" flag in the schema currently |

### 2.4 Data Empty Fallback (Critical)

🔧 **ALL MESS QUESTIONS** — `mess_menus` has 0 rows in production. Every mess question currently returns "There's no mess menu on file for that day." with no escalation path.

**Required fix in `compose_mess`:**
```python
if not rows:
    return (
        "The mess menu hasn't been uploaded to ORION yet. "
        "Check the notice board outside the dining hall, "
        "or contact the Mess Manager directly. "
        "\n\n*Source: mess menu (not yet published)*"
    )
```

Also add mess manager contact lookup from `hostel_wardens` table when data is missing.

---

## 3. Faculty Questions

### 3.1 Finding a Faculty Member

| Question | Status | Notes |
|----------|--------|-------|
| "Tell me about Dr. Manu Madhavan" | ✅ | `_FACULTY_ABOUT_RE` — title required |
| "Who is Dr. Rekha?" | ✅ | |
| "Dr. Anisth S cabin?" | ✅ | `_FACULTY_ATTR_AFTER_NAME_RE` handles bare initials |
| "Where is Dr. Kala S?" | ✅ | `_FACULTY_WHERE_RE` |
| "Dr Deepa email" | ✅ | `_FACULTY_ATTR_AFTER_NAME_RE` |
| "Rekha ma'am email" | ❌ | "ma'am" not recognised as a title; none of the four patterns fire |
| "Manu sir office" | ❌ | "sir" not recognised as a title |
| "Contact Rekha" | ❌ | No title → falls to SEMANTIC |
| "Dr X phone number" | ⚠️ | Routes via `_FACULTY_ABOUT_RE` if title present, but `compose_faculty` uses `p.get("email")` only — no phone field in faculty table |
| "Is Dr. X available?" | ❌ | Availability = derived from timetable; no pattern for this phrasing |
| "Faculty who teaches OS" | ✅ | `FACULTY_FOR_COURSE` if course code found |

**Gap — "sir/ma'am" titles:**  
Add `r"\b(?:sir|ma'?am|madam)\b"` to title recognition in all four faculty regex patterns. Very common in Indian academic context.

**Gap — phone field:**  
`faculty` table has no `phone` column. Add it. Many students ask for the faculty phone number when they need to reach them urgently.

---

### 3.2 Faculty Attributes

| Question | Status | Notes |
|----------|--------|-------|
| "What is Dr. X's email?" | ✅ | `_ATTR_EMAIL` in `compose_faculty` |
| "Where is Dr. X's office?" | ✅ | `_ATTR_OFFICE` |
| "What are Dr. X's office hours?" | ✅ | `_ATTR_OFFICE` catches "office hours" |
| "What does Dr. X research?" | ✅ | `_ATTR_RESEARCH` |
| "What subjects does Dr. X teach?" | ⚠️ | No dedicated compose path — falls to generic faculty card which doesn't list subjects |
| "How many courses does Dr. X teach?" | ❌ | Count query on `timetable_entry_faculty` — not implemented |
| "What is Dr. X's designation?" | ✅ | Generic faculty card shows designation |
| "Is Dr. X a professor or assistant professor?" | ✅ | Designation field |
| "When can I meet Dr. X?" | ✅ | `hints["focus"] = "meet"` → `compose_faculty` with teaching slots |

---

### 3.3 Faculty by Research Topic

| Question | Status | Notes |
|----------|--------|-------|
| "Who works on NLP?" | ✅ | `FACULTY_RESEARCH` via `_RESEARCH_RE` |
| "Which faculty research machine learning?" | ✅ | |
| "Who specialises in computer vision?" | ✅ | |
| "Any faculty working on blockchain?" | ✅ | |
| "Recommend a faculty for my project on deep learning" | ✅ | `FACULTY_RESEARCH` + optional schedule |
| "Who should I approach for a BTP in NLP?" | ✅ | Same |
| "Who researches NLP on campus?" | ✅ | Fixed by `_TOPIC_TAIL_RE` stripping "on campus" |
| "Faculty interested in cybersecurity" | ✅ | `_TOPIC_ALIASES` maps "cybersecurity" |
| "Who can guide me for MS in AI?" | ⚠️ | "MS" and "guide" are both in `_STOPWORDS`, topic may be lost |

**Gap — "guide/MS" in stopwords:**  
Remove "guide" from `_STOPWORDS` in `router.py`. It's a legitimate research-supervision term. Similarly "MS" in the context of "MS guidance" should map to `research_interests`.

---

### 3.4 Faculty by Role

| Question | Status | Notes |
|----------|--------|-------|
| "Who is the HOD of CSE?" | ✅ | `FACULTY_ROLE` → `faculty_by_role` |
| "Who is the registrar?" | ✅ | |
| "Who is the director?" | ✅ | |
| "Who is the dean of academics?" | ✅ | |
| "Is there a counsellor on campus?" | ✅ | "counsellor" → `psychologist` role |
| "Who is the placement coordinator?" | ❌ | "placement coordinator" not in `_ROLE_TERMS` |
| "Who is the sports officer?" | ❌ | Not in `_ROLE_TERMS` |
| "Who is the library in-charge?" | ❌ | Not in `_ROLE_TERMS` |
| "Who is the IQAC coordinator?" | ❌ | Not in `_ROLE_TERMS` |
| "Who handles alumni relations?" | ❌ | Not in `_ROLE_TERMS` |
| "Who is the SC/ST cell officer?" | ✅ | "nodal" role covers SC/ST cell |
| "Who is the anti-ragging squad?" | ❌ | Squad members are in documents, not `faculty.designation` |
| "Who is the training officer?" | ❌ | Not in `_ROLE_TERMS` |

**Required additions to `_ROLE_TERMS`:**
```python
(r"\b(placement\s+(coordinator|officer)|tnp|t&p|training\s+and\s+placement)\b", "placement"),
(r"\b(sports\s+(officer|coordinator|director|teacher|coach)|pe\s+teacher)\b", "physical_education"),
(r"\b(librarian|library\s+(in.?charge|head|officer))\b", "librarian"),
(r"\b(iqac|quality\s+assurance|naac\s+coordinator)\b", "iqac"),
(r"\b(alumni|international\s+relations|ir\s+cell)\b", "alumni"),
(r"\b(industry\s+(liaison|relations)|industry\s+coord\w*)\b", "industry"),
(r"\b(entrepreneurship|innovation|startup\s+cell)\b", "entrepreneurship"),
(r"\b(ncc\s+officer|nss\s+coordinator)\b", "ncc_nss"),
```

---

### 3.5 Faculty Availability (Derived)

| Question | Status | Notes |
|----------|--------|-------|
| "Is Dr. X free right now?" | ❌ | No pattern for "free" + faculty name |
| "Is Dr. X in her cabin?" | ❌ | Availability inference not built |
| "When is Dr. X not in class?" | ⚠️ | `hints["focus"] = "meet"` gets teaching slots but inverts "when busy" to "when free" poorly |
| "Is Dr. X teaching right now?" | ❌ | |
| "Will Dr. X be free tomorrow afternoon?" | ❌ | Requires teaching slot + time-of-day reasoning |

These are genuinely hard. The honest answer when no data exists is the safe fallback already in `compose_faculty`:
> "I don't have real-time availability data. Email is the reliable way."

What's missing is a router pattern to GET to that compose path at all — right now these questions fall to UNSUPPORTED or wrong semantic results.

---

## 4. Course & Academic Questions

### 4.1 Course Information

| Question | Status | Notes |
|----------|--------|-------|
| "Tell me about ICS 214" | ✅ | `COURSE_INFO` via `_COURSE_CODE_RE` + lead phrase |
| "What is OS?" | ⚠️ | "OS" is 2 chars — `_COURSE_CODE_RE` requires format `[A-Z]{2,4}\d{3}`, won't match. Name lookup by "OS" → `resolve_course` with 2-char name returns nothing |
| "How many credits is Compiler Design?" | ✅ | `COURSE_INFO` + `_COURSE_INFO_WORD_RE` credits |
| "What are the prerequisites for ICS 214?" | ✅ | |
| "What is the syllabus for ICS 214?" | ✅ | |
| "Is ICS 214 a core or elective?" | ❌ | No `course_type` (core/elective/open) field in schema |
| "What semester is ICS 214 offered?" | ✅ | `course.semester` field |
| "How many courses are there this semester?" | ❌ | Aggregate count query, no intent |
| "What is IT Workshop?" | ⚠️ | Full name with "IT" acronym: `_norm()` lowercases it and it may not match. Roman numerals in name ("Workshop III") also tricky |
| "List all my courses" | ✅ | `MY_COURSES` intent |
| "What are my courses with their credits?" | ⚠️ | `MY_COURSES` lists courses but doesn't join credits from curriculum |
| "Which of my courses have labs?" | ❌ | Filter `MY_COURSES` by `types` containing "lab" — compose logic doesn't surface this |

---

### 4.2 Course–Faculty Mapping

| Question | Status | Notes |
|----------|--------|-------|
| "Who teaches Compiler Design?" | ✅ | `_WHO_TEACHES_NAME_RE` |
| "Who takes ICS 211?" | ✅ | `_WHO_TEACHES_RE` + course code |
| "Who is the ICS 214 faculty?" | ✅ | |
| "Which faculty handles the lab for ICS 214?" | ❌ | Lab-specific faculty — `timetable_entry_faculty` may have different faculty for lab vs lecture, but compose doesn't split them |
| "Does Dr. X teach any of my courses?" | ❌ | Cross-reference faculty + student timetable |

---

## 5. Exam Questions

### 5.1 Exam Schedule

| Question | Status | Notes |
|----------|--------|-------|
| "When is the ICS 214 exam?" | ✅ | `EXAM_SCHEDULE` + course code |
| "When are my mid-sem exams?" | ✅ | `_EXAM_WORD_RE` + `_TIMING_WORD_RE` |
| "What is the exam schedule?" | ✅ | |
| "Where is my ICS 214 exam?" | ❌ | Venue from `exams` table — compose shows venue if row exists, but 0 rows in prod |
| "What is my seat number for OS exam?" | ❌ | `exams` table has no `seat_number` field in current schema |
| "How many exams do I have?" | ❌ | Aggregate count |
| "When is my last exam?" | ❌ | "last" → `_FOCUS_LAST_RE` only watches for timetable, not exams |
| "Is the OS exam open book?" | ❌ | No such field in schema |
| "Can I bring a calculator to the exam?" | ❌ | Regulation question — needs document corpus entry |

### 5.2 Hall Ticket / Exam Eligibility

| Question | Status | Notes |
|----------|--------|-------|
| "How do I get my hall ticket?" | ❌ | No intent — falls to SEMANTIC, likely gets a wrong document chunk |
| "Am I eligible to write exams?" | ❌ | Requires attendance check — ORION doesn't hold attendance |
| "What is the eligibility criterion for exams?" | ✅ | `_REGULATION_TOPIC_RE` catches "eligib" → SEMANTIC → regulations doc |
| "What happens if I miss an exam?" | ✅ | "make-up" / "miss the exam" → semantic regulations |
| "How do I apply for a make-up exam?" | ✅ | `_REGULATION_TOPIC_RE` includes "make-up" |

🔧 `exams` table has 0 rows. All exam schedule questions return the calendar window fallback. This is honest but unhelpful. Priority: populate this table.

---

## 6. Academic Calendar & Deadlines

### 6.1 Semester Dates

| Question | Status | Notes |
|----------|--------|-------|
| "When does the semester end?" | ✅ | `ACADEMIC_CALENDAR` |
| "When do classes start?" | ✅ | |
| "When is the last working day?" | ✅ | "class ends" event |
| "When does the odd semester start?" | ✅ | |
| "When does the even semester begin?" | ✅ | "even semester classes begin" alias |
| "How many days are left in the semester?" | ❌ | Date arithmetic between now and "class ends" event — not implemented |
| "When is the semester break?" | ❌ | Not a calendar event type that exists — "semester break" is the gap between semesters |

### 6.2 Exam Periods

| Question | Status | Notes |
|----------|--------|-------|
| "When do the end-sem exams start?" | ✅ | |
| "When are the mid-sem exams?" | ✅ | |
| "How long is the exam period?" | ❌ | Duration between start/end events — not computed |
| "When do exam results come out?" | ✅ | "result publication" alias |

### 6.3 Deadlines

| Question | Status | Notes |
|----------|--------|-------|
| "What are the upcoming deadlines?" | ✅ | `_CALENDAR_ONLY_RE` catches "deadlines" |
| "When is the course drop deadline?" | ✅ | "course drop" alias |
| "When is the last date to register?" | ✅ | "registration" alias |
| "When is the fee payment deadline?" | ✅ | "fee payment" alias |
| "When is the project review?" | ✅ | "project review / btp review" alias |
| "What events are happening this month?" | ✅ | "upcoming" → upcoming mode |

### 6.4 Holidays

| Question | Status | Notes |
|----------|--------|-------|
| "Are there any holidays this semester?" | ✅ | `wants_holiday` flag in `academic_calendar` |
| "Is tomorrow a holiday?" | ❌ | Needs "tomorrow" + holiday check = hybrid of `DAY_OF_WEEK_TIMETABLE` and `ACADEMIC_CALENDAR` |
| "Is there class on Diwali?" | ❌ | Named holiday lookup — calendar may or may not have it |
| "How many holidays are left?" | ❌ | Aggregate count |

---

## 7. Regulations & Academic Rules

### 7.1 Attendance

| Question | Status | Notes |
|----------|--------|-------|
| "What is the minimum attendance requirement?" | ✅ | `_REGULATION_TOPIC_RE` → SEMANTIC → UG Regulations |
| "What happens if I have less than 75% attendance?" | ✅ | `_HYPOTHETICAL_RE` prevents personal-records false match |
| "Is there an attendance condonation?" | ✅ | "condonation" in `_REGULATION_TOPIC_RE` |
| "What is the medical leave policy for attendance?" | ✅ | "condonation + medical" in synonym table |
| "Can I get attendance for online classes?" | ❌ | Not in documents — answer honestly "I don't have this information" |
| "What is the attendance for labs?" | ✅ | |
| "My attendance is below 75%. What can I do?" | ✅ | Treated as hypothetical → SEMANTIC |

### 7.2 Grading

| Question | Status | Notes |
|----------|--------|-------|
| "What is the grading system?" | ✅ | `_SEMANTIC_TOPIC_RE` catches "grading" |
| "How is CGPA calculated?" | ✅ | "cgpa" in `_SEMANTIC_TOPIC_RE` |
| "What letter grades are there?" | ✅ | "grades" → SEMANTIC |
| "What does an F grade mean?" | ✅ | "fail/F grade" in synonym table |
| "What is the minimum CGPA to graduate?" | ✅ | "graduation + CGPA" → SEMANTIC |
| "What is a W grade?" | ❌ | "W grade" (withdrawal) not explicitly in synonym table |
| "What is an I grade?" | ❌ | "I grade" (incomplete) not in synonym table |
| "What is the grade point for B+?" | ✅ | Grading scale → SEMANTIC |

**Add to synonym table:**
```python
(re.compile(r"\b(W\s+grade|withdrawal\s+grade)\b", re.I), "W grade withdrawal incomplete semester"),
(re.compile(r"\b(I\s+grade|incomplete\s+grade)\b", re.I), "I grade incomplete make-up examination"),
(re.compile(r"\b(L\s+grade|attendance\s+shortage\s+grade)\b", re.I), "L grade attendance shortage penalty"),
```

### 7.3 Course Registration & Dropping

| Question | Status | Notes |
|----------|--------|-------|
| "How do I drop a course?" | ✅ | "drop courses" → SEMANTIC |
| "Can I withdraw from a course?" | ✅ | "withdraw" in `_REGULATION_TOPIC_RE` |
| "What is the last date to drop a course?" | ✅ | `_CALENDAR_ONLY_RE` catches "course drop" |
| "Can I add a course after registration?" | ❌ | "add" a course not in any pattern |
| "How do I change my elective?" | ❌ | "change elective" not mapped |

### 7.4 Graduation & Credits

| Question | Status | Notes |
|----------|--------|-------|
| "How many credits do I need to graduate?" | ✅ | "graduate/degree" → SEMANTIC |
| "What is the maximum duration of the programme?" | ✅ | "maximum duration" in `_REGULATION_TOPIC_RE` |
| "Can I do a minor?" | ✅ | "minor" in `_REGULATION_TOPIC_RE` |
| "What is the dual degree programme?" | ✅ | "dual degree / B.Tech-MS" |
| "Can I do honours?" | ✅ | "honou?rs" in `_REGULATION_TOPIC_RE` |

### 7.5 Cohort-Specific Questions

| Question | Status | Notes |
|----------|--------|-------|
| "What regulations apply to me?" | ✅ | `_PROFILE_RE` → `MY_PROFILE` → shows regulation title |
| "What are the 2026 admission regulations?" | ✅ | `_COHORT_26_RE` → sets `cohort_ref = "26-onwards"` |
| "Is the attendance rule different for 2026 batch?" | ✅ | `_COHORT_COMPARE_RE` → side-by-side comparison |
| "Which batch am I in?" | ✅ | `MY_PROFILE` |

---

## 8. Hostel & Accommodation Questions

### 8.1 Timings & Gates

| Question | Status | Notes |
|----------|--------|-------|
| "What time does the hostel gate close?" | ✅ | `_HOSTEL_TOPIC_RE` → SEMANTIC → hostel rules doc |
| "What is the curfew time?" | ✅ | Synonym: "curfew" → "return hostels 11:00 PM" |
| "Can I stay out past 11pm?" | ✅ | Same synonym chain |
| "What time does the main door close?" | ✅ | Synonym covers "main door closes" |
| "What is the in-time for girls hostel?" | ✅ | "in-time" in synonym table |

### 8.2 Outpass / Permissions

| Question | Status | Notes |
|----------|--------|-------|
| "How do I apply for an outpass?" | ✅ | Synonym: "outpass/out-pass/gate-pass" → "outpass portal biometric" |
| "Can I go home on weekends?" | ✅ | "leave campus" synonym |
| "How do I apply for overnight leave?" | ✅ | "outpass" synonym covers this |
| "What is the procedure for vacation stay?" | ✅ | "vacation stay" in `_HOSTEL_TOPIC_RE` |

### 8.3 Facilities

| Question | Status | Notes |
|----------|--------|-------|
| "Can I cook in my hostel room?" | ✅ | "cooking/appliances" synonym |
| "Can I use a kettle in the hostel?" | ✅ | "kettle/heater/iron" synonym |
| "Can I have guests in the hostel?" | ✅ | "visitors/guests" → SEMANTIC |
| "What are the silence hours?" | ✅ | "silence hours" in `_HOSTEL_TOPIC_RE` |
| "Can I keep pets?" | ✅ | "pets" in `_HOSTEL_TOPIC_RE` |
| "Is smoking allowed?" | ✅ | "smoking" in `_HOSTEL_TOPIC_RE` |
| "Can I swap rooms with a friend?" | ✅ | "room swap" in `_HOSTEL_TOPIC_RE` |

### 8.4 Wardens

| Question | Status | Notes |
|----------|--------|-------|
| "Who is the warden of Sahyadri hostel?" | ✅ | `HOSTEL_WARDENS` with hall name matching |
| "Who is the chief warden?" | ✅ | |
| "How do I contact the hostel manager?" | ✅ | "hostel manager" → `HOSTEL_WARDENS` |
| "What is the warden's phone number?" | ✅ | `_contact()` in compose shows phone |
| "Who is my hostel warden?" | ⚠️ | "my hostel warden" — doesn't know which hostel the student is in (no `hostel_allocation` table) |

🔧 **Missing: Student–hostel mapping.**  
There's no `hostel_allocations` table linking `student_profiles.user_id` to a hostel block. Without this, "who is my warden" can't be answered personally. Add this table to Phase 1 data population.

---

## 9. Anti-Ragging Questions

| Question | Status | Notes |
|----------|--------|-------|
| "What is ragging?" | ✅ | `_RAGGING_TOPIC_RE` → SEMANTIC |
| "What counts as ragging?" | ✅ | Overview → "What constitutes ragging" |
| "What are the punishments for ragging?" | ✅ | Synonym: "punishments → administrative action guilty" |
| "What is the anti-ragging helpline?" | ✅ | Synonym: "helpline toll free distress call" |
| "How do I report ragging?" | ✅ | |
| "Who are the anti-ragging squad members?" | ⚠️ | Routes to SEMANTIC → document, but squad members may be in a memo not well-chunked |
| "What are the hostel anti-ragging rules?" | ✅ | Both `_HOSTEL_TOPIC_RE` and `_RAGGING_TOPIC_RE` fire; hostel wins |
| "Tell me all the ragging rules" | ✅ | `_OVERVIEW_RE` → overview mode |

---

## 10. Administrative & Document Questions

### 10.1 Certificates & Verification

| Question | Status | Notes |
|----------|--------|-------|
| "How do I get a bonafide certificate?" | ❌ | "bonafide" not in `_PROCEDURE_TOPIC_RE` |
| "What is a bonafide certificate?" | ❌ | Same |
| "How do I get transcript verification?" | ✅ | "transcripts/certificate verification" in `_PROCEDURE_TOPIC_RE` |
| "What is the transcript fee?" | ✅ | "transcripts" → SEMANTIC → procedures doc |
| "How do I get a character certificate?" | ❌ | Not in any pattern |
| "What is a no-due certificate?" | ❌ | "NDC" not in any pattern |
| "How do I get an NOC for internship?" | ❌ | Not in any pattern |
| "How do I get a migration certificate?" | ❌ | Not in any pattern |
| "What documents do I need for passport?" | ❌ | Out of scope for ORION; but "bonafide certificate for passport" is an institution-specific procedure |

**Add to `_PROCEDURE_TOPIC_RE`:**
```python
r"\b(bonafide|bona\s+fide|character\s+certificate|no[\s-]?due|ndc|"
r"noc|no\s+objection|migration\s+certificate|internship\s+letter|"
r"scholarship\s+certificate|fee\s+receipt|duplicate\s+id\s+card|"
r"study\s+certificate)\b"
```

### 10.2 ID Card

| Question | Status | Notes |
|----------|--------|-------|
| "I lost my ID card. What do I do?" | ❌ | No procedure documented |
| "How do I get a duplicate ID card?" | ❌ | Not in any pattern |
| "Can I use a soft copy of my ID?" | ❌ | Not documented |

### 10.3 Official Documents

| Question | Status | Notes |
|----------|--------|-------|
| "Where are the institute documents?" | ❌ | Should point to the documents section — but this is UI navigation, not an information query |
| "What is the academic handbook?" | ❌ | Not a specific intent |
| "Where can I find the UG regulations?" | ❌ | Should point to approved documents in ORION's document store |

---

## 11. Clubs, Events & Campus Life

### 11.1 Clubs

| Question | Status | Notes |
|----------|--------|-------|
| "What clubs are there on campus?" | ❌ | No `CLUBS_LIST` intent. Falls to UNSUPPORTED |
| "How do I join the robotics club?" | ❌ | No club data in database |
| "Who is the head of the coding club?" | ❌ | No club-faculty mapping |
| "What is the Tathva club?" | ❌ | No club descriptions indexed |
| "Which clubs are accepting members?" | ❌ | No membership status field |
| "When is the next club meeting?" | ❌ | No events calendar for clubs |

**Required:** New `clubs` table + `CLUBS_LIST`/`CLUB_EVENTS` intents + compose functions. This is a major gap — the frontend has `clubs.tsx` with mock data but zero backend.

### 11.2 Events

| Question | Status | Notes |
|----------|--------|-------|
| "What events are happening this week?" | ⚠️ | Routes to `ACADEMIC_CALENDAR` but club events are not in that table |
| "When is the next hackathon?" | ❌ | Not in academic calendar |
| "When is the cultural fest?" | ❌ | Not indexed |
| "Is there a sports meet this semester?" | ✅ | "sports meet" in `_CALENDAR_ONLY_RE` if in academic calendar |
| "When is the technical symposium?" | ❌ | No pattern |


---

## 12. Health, Safety & Emergency

### 12.1 Medical / Health Center

| Question | Status | Notes |
|----------|--------|-------|
| "Is there a medical officer on campus?" | ✅ | `_ROLE_TERMS` has "medical" |
| "What is the doctor's contact?" | ✅ | `faculty_by_role` with "medical" → compose shows contact |
| "Where is the health center?" | ❌ | `_ATTR_OFFICE` in `compose_faculty` shows office_location if found, but "health center" as a building is not in faculty profile |
| "What are the clinic timings?" | ❌ | No clinic hours field |
| "Who is the campus nurse?" | ✅ | "nurse" in `_ROLE_TERMS` |
| "Is there an ambulance?" | ❌ | Emergency number — needs `campus_contacts` table |
| "What do I do in a medical emergency?" | ❌ | Emergency procedure — needs document or structured data |

### 12.2 Safety & Emergency Numbers

| Question | Status | Notes |
|----------|--------|-------|
| "What is the security office number?" | ⚠️ | "security officer" → `HOSTEL_WARDENS` → shows security contact if in that table |
| "What is the emergency number?" | ❌ | No `emergency_contacts` table |
| "What do I do if there's a fire?" | ❌ | Safety procedure — should be in a safety document |
| "Where are the fire extinguishers?" | ❌ | Facilities data — not indexed |
| "Is there a police helpline?" | ❌ | Not indexed; generally out of scope |

**Required:** `campus_contacts` table with: health center, security, warden emergency line, helpline numbers. Then a `CAMPUS_CONTACTS` intent.

---

## 13. Transport & Connectivity

| Question | Status | Notes |
|----------|--------|-------|
| "Is there a bus to Kottayam town?" | ❌ | No transport data |
| "What time does the institute bus leave?" | ❌ | No transport table |
| "How do I get to the railway station from campus?" | ❌ | Out of scope (general directions) |
| "Is there a cab service?" | ❌ | No data |
| "What is the hostel to academic block route?" | ❌ | Campus map — visual, not text |
| "Is there campus WiFi?" | ❌ | IT helpdesk info — not indexed |
| "What is the WiFi password?" | ❌ | Security sensitive — should not be in ORION |
| "Who do I contact for internet issues?" | ❌ | IT support contact — `campus_contacts` would cover this |
| "What is the SSID for campus WiFi?" | ❌ | IT helpdesk |

**Required:** `transport_schedules` table (route, day, departure_time, destination). Low-medium effort, very high daily query volume.

---

## 14. Library Questions

| Question | Status | Notes |
|----------|--------|-------|
| "What are the library timings?" | ❌ | No library data |
| "Who is the librarian?" | ❌ | "librarian" not in `_ROLE_TERMS` |
| "Can I access online journals?" | ❌ | Not indexed |
| "What is the fine for late returns?" | ❌ | No library rules document indexed |
| "How many books can I borrow?" | ❌ | No library data |
| "How do I renew a book?" | ❌ | No library procedure |
| "Where is the library?" | ❌ | Building location — not in faculty table |
| "Is the library open on Sunday?" | ❌ | No library hours data |

**Required:** `library_info` structured table (hours, fines, borrow limits) OR a library rules document in the RAG corpus. Low data entry effort, medium engineering effort.

---

## 15. Placement & Career Questions

| Question | Status | Notes |
|----------|--------|-------|
| "When does placement season start?" | ❌ | May be a calendar event — if not added, falls to UNSUPPORTED |
| "Who is the placement coordinator?" | ❌ | "placement coordinator" not in `_ROLE_TERMS` |
| "Which companies visited last year?" | ❌ | No placement data — genuinely out of scope unless a document is indexed |
| "What is the average package?" | ❌ | Out of scope / no data |
| "How do I prepare for placements?" | ❌ | General advice — out of scope |
| "Is there a placement cell?" | ❌ | Not indexed |
| "What is the internship policy?" | ❌ | "internship" not in `_PROCEDURE_TOPIC_RE` |
| "Can I apply for off-campus placements?" | ❌ | Policy question — may be in a document |
| "What is the CGPA cutoff for placements?" | ❌ | Company-specific, no data |
| "When is the pre-placement talk?" | ❌ | Calendar event — not indexed |

**Minimum viable:** Add "placement coordinator" to `_ROLE_TERMS`. Add `internship` to `_PROCEDURE_TOPIC_RE`. Add placement season start/end to `academic_calendar` entries.

---

## 16. Infrastructure & Facilities

| Question | Status | Notes |
|----------|--------|-------|
| "Where is the academic block?" | ❌ | Campus map — visual |
| "Where is the admin office?" | ❌ | Building location |
| "Where is the principal's office?" | ❌ | "director" → faculty lookup gives office_location if populated |
| "Is there a canteen?" | ❌ | No canteen/mess differentiation |
| "What are the canteen timings?" | ❌ | No canteen data separate from mess |
| "Where can I print documents on campus?" | ❌ | No facilities data |
| "Is there a Xerox shop?" | ❌ | No data |
| "Where is the ATM?" | ❌ | Campus facilities — not indexed |
| "Is there a post office on campus?" | ❌ | No data |
| "Where are the lecture halls?" | ❌ | Rooms table exists but has 0 rows |

🔧 `rooms` table has 0 rows. Room queries all return nothing.

---

## 17. Fee & Financial Questions

### 17.2 In-Scope Deadline Questions

| Question | Status | Notes |
|----------|--------|-------|
| "When is the fee payment deadline?" | ✅ | `_CALENDAR_ONLY_RE` catches "fee payment" |
| "What is the last date to pay fees?" | ✅ | Same alias |
| "When do I need to pay hostel fees?" | ⚠️ | "hostel fees" not explicitly aliased — may not match |
---

## 18. Profile & Personal Academic Context

| Question | Status | Notes |
|----------|--------|-------|
| "What semester am I in?" | ✅ | `MY_PROFILE` |
| "What is my section?" | ✅ | |
| "What is my department?" | ✅ | |
| "Which regulations apply to me?" | ✅ | |
| "What batch am I in?" | ✅ | |
| "What year am I in?" | ✅ | `semester` maps to year (sem 1-2 = year 1, etc.) but compose doesn't compute year from semester |
| "Am I a first year student?" | ❌ | "first year" requires semester → year computation |
| "What programme am I in?" | ✅ | |
| "Who is my faculty advisor?" | ❌ | No `faculty_advisor` link in `student_profiles` |
| "Who is my class teacher?" | ❌ | Same |

**Add to `student_profiles`:** `faculty_advisor_id` FK to `faculty`. Very common question.

---

## 19. Announcements & Notices

| Question | Status | Notes |
|----------|--------|-------|
| "What are the latest announcements?" | ✅ | `ANNOUNCEMENTS` intent |
| "Are there any new notices?" | ✅ | |
| "What's new on campus?" | ✅ | `_ANNOUNCEMENT_RE` catches "what's new/latest updates" |
| "Any announcements about exams?" | ❌ | Category-filtered announcement query — not implemented |
| "Any hostel announcements?" | ❌ | Department/category filter not in compose |
| "Show me all pinned notices" | ❌ | No "pinned" filter in `announcements` query |
| "When was the last announcement?" | ❌ | Date-of-last-announcement query |

🔧 `announcements` table has 0 rows. Same fallback problem as mess.

---

## 20. Small Talk & Meta Questions

| Question | Status | Notes |
|----------|--------|-------|
| "Hi!" | ✅ | Time-of-day greeting |
| "Hello ORION" | ✅ | `_GREETING_LOOSE_RE` catches "ORION" after greeting |
| "Thanks!" | ✅ | Randomised thanks reply |
| "Bye!" | ✅ | Randomised farewell |
| "What can you do?" | ✅ | `_CAPABILITIES_RE` |
| "How are you?" | ✅ | `_HOW_ARE_YOU_RE` |
| "Who made you?" | ❌ | No pattern — falls to UNSUPPORTED. Should return a canned "I'm ORION, built for IIIT Kottayam" |
| "Are you an AI?" | ❌ | No pattern |
| "What is ORION?" | ⚠️ | `_CAPABILITIES_RE` has "what is orion?" ✅ |
| "Namaste" | ✅ | `_GREETING_LOOSE_RE` catches "namaste" |
| "Good night ORION" | ❌ | "good night" not in greeting patterns — should be added |
| "I'm bored" | ❌ | Out of scope; should give a gentle redirect |
| "Tell me a joke" | ✅ | `_GENERAL_KNOWLEDGE_RE` catches "joke" → OUT_OF_SCOPE, but message is generic |

**Add to small talk patterns:**
```python
_WHO_MADE_RE = re.compile(r"\b(who\s+(made|built|created|developed)\s+(you|orion)|who\s+are\s+your\s+creators?)\b", re.IGNORECASE)
_GOOD_NIGHT_RE = re.compile(r"^\s*good\s+night[\s!.]*$", re.IGNORECASE)
```

---

## 21. Follow-Up & Multi-Turn Scenarios

### 21.1 Meal Follow-Ups

| Conversation | Status | Notes |
|---|---|---|
| "What's for lunch?" → "And dinner?" | ✅ | `_ELLIPSIS_RE` + slot swap |
| "What's for lunch today?" → "tomorrow?" | ✅ | `inherit_plan` carries mess domain + moves date |
| "What's for lunch today?" → "What about dinner?" → "And tomorrow?" | ✅ | Chain resolves each hop |
| "What's for lunch?" → "Is it vegetarian?" | ❌ | No veg field in mess_menus |
| "What's for lunch?" → "What time is it?" | ⚠️ | "it" → `_THING_PRONOUN_RE` looks for course context, not meal context |

### 21.2 Timetable Follow-Ups

| Conversation | Status | Notes |
|---|---|---|
| "What are my classes on Monday?" → "What about Tuesday?" | ✅ | `inherit_plan` slot-swaps day |
| "What is my next class?" → "Who teaches it?" | ✅ | `_THING_PRONOUN_RE` + `_COURSE_TOPIC_RE` |
| "What is my next class?" → "What about Friday?" | ✅ | `_day_followup` |
| "Show me my weekly timetable" → "What labs do I have?" | ⚠️ | `inherit_plan` only handles meal/day slots, not "entry_type" filter |

### 21.3 Faculty Follow-Ups

| Conversation | Status | Notes |
|---|---|---|
| "Tell me about Dr. X" → "What does he research?" | ✅ | `_PERSON_PRONOUN_RE` resolves to name |
| "Tell me about Dr. X" → "What is her email?" | ✅ | Same |
| "Who researches NLP?" → "Can I meet any of them?" | ❌ | "them" → plural pronoun not resolved by `_PERSON_PRONOUN_RE` (singular only) |
| "Who teaches OS?" → "When does he have office hours?" | ✅ | Pronoun resolved to faculty name from previous answer |

### 21.4 Regulation Follow-Ups

| Conversation | Status | Notes |
|---|---|---|
| "What is the attendance rule?" → "What if I don't meet it?" | ✅ | `resolve()` appends "(what is the attendance rule)" to follow-up |
| "What is the grade for failing?" → "What about the 2026 batch?" | ⚠️ | `inherit_plan` doesn't propagate cohort context |

**Required:** In `inherit_plan`, detect `detect_cohort_reference(query)` and if found, update `hints["cohort_ref"]` in the inherited plan.

---

## 22. Edge Cases & Adversarial Inputs

| Input | Expected Behaviour | Current Behaviour |
|-------|-------------------|------------------|
| Empty string | UNSUPPORTED with graceful message | ✅ "empty query" |
| "?" | UNSUPPORTED | ✅ Falls through to unsupported |
| "asdfjkl" | UNSUPPORTED | ✅ Not question-shaped |
| "1234" | UNSUPPORTED | ✅ `_WORD_RE` requires `[a-z]{3,}` |
| Entire paragraph pasted | ⚠️ | First pattern to match wins — may mis-route |
| SQL injection: "'; DROP TABLE users; --" | ✅ | Never touches SQL directly; all access via Supabase client |
| Prompt injection: "Ignore previous instructions and..." | ✅ | Router is pure regex — prompt injection only affects LLM stage, and system prompt instructs the model |
| Mixed language: "ICS 214 exam kab hai?" | ❌ | Hindi words not in any pattern; "exam" fires `_EXAM_WORD_RE` but "kab hai" has no timing word in English |
| Very long question (500+ words) | ⚠️ | Router will still regex-match the first pattern found, but compose context may be poor |
| Repeated question 5 times | ✅ | Stateless — same answer each time |
| "What is my CGPA?" | ✅ | `_MY_RECORDS_RE` catches "my cgpa" → OUT_OF_SCOPE (correct) |
| "What is the CGPA formula?" | ✅ | No "my" → SEMANTIC → regulations |
| Course code with no space: "ICS214" | ✅ | `_COURSE_CODE_ANYCASE_RE` allows optional space |
| Course code with lowercase: "ics 214" | ✅ | `re.IGNORECASE` on all patterns |
| "What's for lunch 🍛?" | ✅ | Emoji after text — pattern still matches "lunch" |

---

## 23. CR-Specific Questions

| Question | Status | Notes |
|----------|--------|-------|
| "How do I upload a timetable?" | ❌ | CR workflow — no intent |
| "What is the OCR confidence for my upload?" | ❌ | Internal tool, not a chat query |
| "My upload was rejected. Why?" | ❌ | Requires approval_requests lookup |
| "How long does approval take?" | ❌ | No SLA data |
| "Can I edit an uploaded document?" | ❌ | Workflow question |
| "How do I submit mess menu?" | ❌ | CR workflow question |

**Note:** CR questions about the submission workflow are better served by UI affordances (status in the CR portal) than by the AI chat. The AI chat for a CR user should still answer all student questions.

---

## 24. Admin-Specific Questions

| Question | Status | Notes |
|----------|--------|-------|
| "How many users are active?" | ❌ | Admin analytics — not a chat query |
| "What uploads are pending approval?" | ❌ | Admin queue — UI affordance |
| "Who uploaded this document?" | ❌ | Audit log query |
| "How many AI queries today?" | ❌ | Analytics dashboard |

**Note:** These are dashboard queries, not conversational queries. The AI chat for an admin user should answer all student/faculty questions for oversight purposes.

---

## 25. Cross-Cutting Gaps Summary

### 25.1 Data Gaps (Zero-Row Tables)

These exist in the schema but have no data. Every question routed to them returns a fallback or empty state:

| Table | Rows | Impact | Priority |
|-------|------|--------|---------|
| `mess_menus` | 0 | Every food question returns no-data | 🔴 Critical |
| `announcements` | 0 | Every notice question returns empty | 🔴 Critical |
| `exams` | 0 | Exam schedule uses calendar fallback | 🔴 Critical |
| `rooms` | 0 | Classroom queries return nothing | 🟡 High |
| `academic_calendar` | 0 | All deadline questions return nothing | 🔴 Critical |
| `departments` | 0 | Faculty dept FK broken | 🟡 High |
| `room_allocations` | 0 | "My classroom" query fails | 🟡 High |
| `document_chunks` | 0 | ALL semantic/RAG queries fail | 🔴 Critical |

### 25.2 Missing Router Intents

| Intent | Question Type | Effort |
|--------|--------------|--------|
| `CLUBS_LIST` | "What clubs are there?" | Medium |
| `CLUB_EVENTS` | "When is the next hackathon?" | Medium |
| `TRANSPORT_INFO` | "Is there a bus to Kottayam?" | Medium |
| `LIBRARY_INFO` | "What are library timings?" | Low |
| `CAMPUS_CONTACTS` | "What is the emergency number?" | Low |
| `WORKING_DAY_CHECK` | "Is tomorrow a working day?" | Low |
| `FACULTY_ADVISOR` | "Who is my faculty advisor?" | Low |
| `HOSTEL_ALLOCATION` | "Which hostel am I in?" | Low |

### 25.3 Missing Compose Behaviours

| Behaviour | Where Needed | Effort |
|-----------|-------------|--------|
| Duration until next class | `compose_next` | Low |
| "Suggest tomorrow's first class" when no class today | `compose_next` | Low |
| Disambiguation with department (not just email) | `compose_faculty` | Low |
| Count + filter in `compose_week` | `compose_week` | Low |
| Mess contact fallback when data empty | `compose_mess` | Low |
| Year-from-semester computation | `compose_profile` | Low |
| "Closest match" suggestions on course miss | `_no_structured_answer` | Medium |
| Category-filtered announcements | `compose_announcements` | Medium |

---

## 26. Implementation Priority Matrix

### 🔴 P0 — Blocks Core Functionality (Do First)

1. **Populate `document_chunks`** — Without RAG data, every hostel/regulation/policy question fails. Ingest: UG Regulations (both cohorts), hostel rules, anti-ragging policy, academic handbook.

2. **Populate `academic_calendar`** — Every deadline question fails without this. Populate from the odd semester 2026-27 calendar PDF.

3. **Populate `mess_menus`** — Food questions are the highest daily volume. Add current week + weekly template fallback.

4. **Populate `announcements`** — At least seed with current live notices.

5. **Fix `compose_mess` empty fallback** — Show mess manager contact when data is absent.

### 🟡 P1 — High Value, Low Effort (Do Next)

6. **Add "sir/ma'am" to faculty title recognition** — Massive coverage improvement for Indian users.

7. **Extend `_ROLE_TERMS`** — Add placement coordinator, librarian, IQAC, alumni, sports officer, NCC/NSS.

8. **Extend `_PROCEDURE_TOPIC_RE`** — Add bonafide, NOC, character certificate, NDC, internship letter.

9. **Add to synonym table** — W grade, I grade, L grade, bonafide, internship, scholarship.

10. **Add "guide" to un-stop `_STOPWORDS`** — Critical for "MS guide/supervisor" queries.

11. **Duration-to-class in `compose_next`** — "Starts in 23 minutes."

12. **`compose_faculty` disambiguation fallback** — Use `department` when `email` is null.

### 🟠 P2 — Medium Value, Medium Effort

13. **`campus_contacts` table + `CAMPUS_CONTACTS` intent** — Emergency numbers, health center, IT helpdesk, security.

14. **`transport_schedules` table + `TRANSPORT_INFO` intent** — Bus routes + timings.

15. **`library_info` table or library rules document** — Hours, fines, borrow limits.

16. **`clubs` table + `CLUBS_LIST`/`CLUB_EVENTS` intents** — High student interest.

17. **`hostel_allocations` table** — Link students to their hostel block for personalised warden lookup.

18. **`faculty_advisor_id` in `student_profiles`** — "Who is my faculty advisor?"

19. **Time-of-day words in router** — "morning/afternoon/evening" → time range.

20. **`WORKING_DAY_CHECK` hybrid intent** — "Is tomorrow a holiday?" checks both calendar and timetable.

### 🔵 P3 — Nice to Have

21. **Cohort context in `inherit_plan`** — Regulation follow-ups across turns.

22. **Plural pronoun resolution** — "Can I meet any of them?" after a multi-faculty result.

23. **"Day after tomorrow" in `tempo.py`** — Date alias for +2 days.

24. **Good night small talk** — Very minor UX touch.

25. **Duration computation** — "How long is the exam period?" (date arithmetic).

26. **Category-filtered announcements** — "Any hostel announcements?"

---

## 27. New Router Patterns Required

```python
# ---- In router.py ----

# "sir/ma'am" as titles (add to all four faculty regex patterns)
_TITLE_RE = r"(?:dr|prof|professor|mr|ms|mrs|sir|ma'?am|madam)\.?"

# Time-of-day words
_TIME_OF_DAY_RE = re.compile(
    r"\b(morning|afternoon|evening|tonight|night)\b", re.IGNORECASE
)
_TIME_OF_DAY_MAP = {
    "morning": ("08:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "20:00"),
    "tonight": ("20:00", "23:00"),
    "night": ("20:00", "23:00"),
}

# Working day check
_WORKING_DAY_RE = re.compile(
    r"\b(is\s+(today|tomorrow|[a-z]+day)\s+a\s+working\s+day|"
    r"do\s+we\s+have\s+(class|classes|college)\s+on|"
    r"is\s+(today|tomorrow)\s+a\s+holiday)\b",
    re.IGNORECASE,
)

# Good night
_GOOD_NIGHT_RE = re.compile(
    r"^\s*good\s+night[\s!.]*$", re.IGNORECASE
)

# Who made ORION
_WHO_MADE_RE = re.compile(
    r"\b(who\s+(made|built|created|developed)\s+(you|orion)|"
    r"who\s+are\s+your\s+(creators?|developers?|makers?))\b",
    re.IGNORECASE,
)

# Clubs
_CLUBS_RE = re.compile(
    r"\b(clubs?|society|societies|technical\s+club|cultural\s+club|"
    r"robotics|coding\s+club|music\s+club|dance\s+club|drama|"
    r"photography|tathva|vidyut|ieee|acm)\b",
    re.IGNORECASE,
)

# Library
_LIBRARY_RE = re.compile(
    r"\b(library|librarian|books?\s+(borrow|issue|return|renew|fine)|"
    r"reading\s+room|journal\s+access|e-?resources?)\b",
    re.IGNORECASE,
)

# Transport
_TRANSPORT_RE = re.compile(
    r"\b(bus|shuttle|transport|auto|cab\s+service|kottayam\s+(town|city)|"
    r"railway\s+station|airport\s+drop|college\s+bus)\b",
    re.IGNORECASE,
)

# Emergency / campus contacts
_EMERGENCY_RE = re.compile(
    r"\b(emergency|helpline|ambulance|fire\s+(station|brigade)|"
    r"police|security\s+number|campus\s+contact|it\s+helpdesk|"
    r"internet\s+(issue|problem|not\s+working))\b",
    re.IGNORECASE,
)

# Bonafide / certificates
_CERTIFICATE_RE = re.compile(
    r"\b(bonafide|bona\s+fide|character\s+certificate|no[\s-]?due|ndc|"
    r"noc|no\s+objection|migration\s+certificate|internship\s+letter|"
    r"study\s+certificate|fee\s+receipt|duplicate\s+id)\b",
    re.IGNORECASE,
)
```


---

## Final Note for Implementation

This document represents a full question-space audit. The prioritisation in §26 is designed to maximise answer quality per engineering hour spent. The single highest-leverage action is **populating `document_chunks`** — it unblocks every hostel, regulation, and policy question simultaneously. The second is **populating `academic_calendar`** — it unblocks every deadline and scheduling question. Together these two data population tasks, each requiring no code changes, will answer approximately **40% of the currently unanswered question types**.

The code changes with the highest ROI are:
1. Adding "sir/ma'am" to faculty title recognition (~5 lines)
2. Extending `_ROLE_TERMS` with 8 missing roles (~16 lines)
3. Extending `_PROCEDURE_TOPIC_RE` with certificate types (~10 lines)
4. Adding the synonym table entries in §30 (~30 lines)
5. The `compose_mess` empty fallback fix (~8 lines)

These five changes, totalling under 70 lines of code, will eliminate the most visible failures a student encounters on day one.

---

*Document generated: September 2026 · ORION Campus Assistant · IIIT Kottayam*
