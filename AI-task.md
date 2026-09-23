# ORION AI — question bank and expected behaviour

Rebuilt 2026-09-23 after the Gemini embedding backfill finished (1,269/1,269
document chunks, 146/146 faculty rows — `todo.md`, `docs/embeddings.md`).
Sections 1-14 are the original 134-question functional bank; §15 is new and
exists specifically to stress-test what the completed backfill unlocks:
semantic faculty-topic ranking against the recalibrated similarity floor
(`FACULTY_MIN_SIMILARITY = 0.65`) and cohort isolation across the two
regulation/curriculum document sets now that both are fully vectorized.

The questions a student (or CR/admin) would realistically ask ORION, grouped by
what they need. `scripts/run_ai_task.py` runs every one of them through the
real answer pipeline with a real signed-in test student
(`orion-test-student-a`, Semester 3, CSE section I, cohort `2021_2025`) and
writes the answers to `AI-task-results.md`.

Ground rules every answer must follow (CLAUDE.md §1, §5, §20, §24):

- Facts come from Supabase or approved documents, never from model memory.
- Every factual answer names its source.
- Regulations are answered for the student's own cohort, and any rule quoted
  from a document says which cohort it belongs to.
- When the data isn't there, say so plainly and point to where to look — no
  guesses, no invented dates, grades or availability.
- Works with **no Gemini at all** (quota exhausted): structured answers are
  written from the data directly, document answers quote the relevant rule.

Lines are `- question` or `- question → expectation`. `>>` marks a follow-up
asked in the same conversation as the line above it.

## 1. Greetings, help, small talk
- Hi → greeting + what ORION can help with
- hello there → greeting
- Good morning → greeting
- What can you do? → capability list
- Who are you? → introduces ORION
- How are you? → friendly reply
- Thanks! → acknowledgement
- Bye → farewell

## 2. Timetable — now, today, specific days
- What is my next class? → course, day, time, teacher
- What class is going on right now? → current or next class
- What classes do I have today? → full list for today with times
- What's my timetable for tomorrow? → tomorrow's list
- What classes do I have on Monday? → Monday list
- Do I have classes on Saturday? → Saturday list or "no classes"
- Do I have any class on Sunday? → "no classes on Sunday"
- What did I have yesterday? → yesterday's list
- What is my timetable for this week? → grouped by day
- What class do I have at 10 AM? → class covering 10 AM
- What class do I have at 5 PM? → class covering 5 PM
- What is my first class tomorrow? → earliest class tomorrow
- When does my last class end today? → end time of last class
- How many classes do I have today? → count + list
- When am I free today? → gaps between classes
- When is my Data Structures class this week? → matching slots
- Which labs do I have this week? → lab entries only
- Who teaches my next class? → faculty of next class
- Where is my next class? → classroom, or honest note that rooms aren't printed

## 3. Courses
- What courses do I have this semester? → distinct courses from own timetable
- List my subjects → same
- Tell me about ICS 211 → course name, semester, what's on file
- What is ICS 212 about? → course info
- Who teaches ICS 213? → faculty list
- Who teaches Database Management Systems? → resolves course by name
- Who teaches Theory of Computation? → resolves course by name
- How many credits is ICS 213? → credits if on file, else honest + curriculum pointer
- Which semester is Data Structures II taught in? → semester 3
- What is IT Workshop III? → course info

## 4. Faculty — contact, roles, research
- What is Dr. Manu Madhavan's email? → email
- Where is Dr. Manu Madhavan's office? → office location
- Tell me about Dr. Manu Madhavan → profile incl. research interests
- What is the email of Dr. Vengadeswaran S? → email or "not on file"
- Who is the HOD of Computer Science? → HOD(s) with contacts
- Who is the HOD of ECE? → HOD ECE
- Who is the Registrar? → registrar
- Who is the Associate Dean of Academic Affairs? → dean
- Is there a medical officer on campus? → medical officer contact
- Is there a counsellor or psychologist I can talk to? → psychologist
- Which faculty work on Natural Language Processing? → matching faculty
- Which faculty work on NLP and when can I meet them? → faculty + teaching schedule, no invented office hours
- Recommend a faculty member for machine learning research. → ranked faculty
- Who researches computer vision? → matching faculty
- Who works on cyber security? → matching faculty
- Who researches underwater sensor networks? → Dr. Jalaja M J (or honest no match)
- Is anyone working on blockchain? → matches or honest no match
- When can I meet Dr. Manu Madhavan? → teaching schedule, explicit that office hours aren't on file

## 5. Mess
- What is on the mess menu today? → all meals, with staleness caveat if repeated cycle
- What's for lunch today? → lunch only
- What's for dinner tomorrow? → dinner tomorrow
- What is for breakfast on Monday? → Monday breakfast
- What is being served for dinner this week? → dinner by day
- What are the snacks today? → snacks
- What did we have for dinner yesterday? → yesterday dinner

## 6. Academic calendar and exams
- When do the end semester exams start? → 2026-10-28
- When do mid semester exams start? → 2026-09-02 (already past — say so)
- When does the semester end? → 2026-11-13
- When is the last instructional day? → Class Ends 2026-10-26
- What is the last date for course drop? → 2026-07-30 (past)
- What are the upcoming deadlines? → next deadlines from today
- What's coming up on the academic calendar? → next events
- When is the sports meet? → 2026-09-25 to 2026-09-27
- When will results be published? → 2026-12-03
- When does the even semester start? → 2026-12-21
- When is the next class committee meeting? → next meeting date
- When is registration for the even semester? → 2026-12-14
- When is my ICS 213 exam? → per-course schedule not published; end-sem window
- Are there any holidays this month? → honest: calendar has no holiday entries

## 7. Regulations (answered for the student's cohort)
- What is the attendance requirement? → 80%, cited to the 2021-25 regulations
- What happens if my attendance is below 80%? → consequence per regulations
- Is there attendance condonation? → condonation rule
- How is CGPA calculated? → grading/CGPA rule
- What is the grading system? → grade points
- How many credits do I need to graduate? → degree credit requirement
- What is the maximum duration to complete the B.Tech? → 12 semesters
- Can I take a summer term? → summer term rule or honest
- How do I drop a course? → drop/withdrawal rule
- What happens if I fail a course? → backlog/repeat rule
- What is an incomplete grade? → I grade rule
- Can I write a make-up exam if I miss the end semester exam? → make-up rule
- What is required for the B.Tech-MS dual degree? → eligibility
- What is the minimum CGPA to get the degree? → minimum CGPA

## 8. Hostel
- What are the hostel curfew rules? → in-time / gate timings from hostel rules
- What time should I be back in the hostel? → in-time
- How does the outpass process work? → leave/outpass rule
- Can visitors come to the hostel? → visitor rule
- Can I cook in my hostel room? → electrical appliance / cooking rule
- Who is the warden of Sahyadri hostel? → warden(s) with phone/email
- Who are the wardens for Anamudi hostel? → wardens
- How do I contact my hostel warden? → warden contacts (asks which hostel if unknown)

## 9. Anti-ragging
- What are the anti-ragging rules? → summary from UGC regulations / memo
- What counts as ragging? → definition
- What is the punishment for ragging? → punishments
- How do I report ragging? → reporting / helpline
- Who is on the anti-ragging squad? → members from the office memorandum

## 10. Procedures
- How do I request transcript verification? → steps
- What is the transcript verification fee? → fee from the procedure
- How does educational certificate verification work? → steps

## 11. Announcements
- Are there any current announcements? → current approved announcements or "none right now"
- Any new notices? → same
- What's the latest news on campus? → same

## 12. About me
- What semester am I in? → 3
- Which section am I in? → I
- What is my department? → CSE
- Which regulations apply to me? → UG Regulations 2021-25 batch

## 13. Follow-up conversations
- Tell me about ICS 211
>> Who teaches it?
>> What credits does it have?
- What is my next class?
>> Who teaches it?
- What is Dr. Manu Madhavan's email?
>> What does he research?
- What's for lunch today?
>> And dinner?
- What is the attendance requirement?
>> What if I don't meet it?

## 14. Out of scope — must not invent anything
- What are my exam grades this semester? → ORION doesn't hold grades; where to check
- What is my CGPA? → same
- What is my attendance percentage? → not held; ask faculty / portal
- How do I pay my fees? → fee payment not in ORION; fee deadlines from calendar if relevant
- What is the weather today? → out of scope
- What is the capital of France? → out of scope, campus assistant
- Write a Python program to sort a list → out of scope
- What is the meaning of life? → out of scope, friendly
- asdkfj qwer nonsense query → didn't understand + examples
- Who will win the IPL this year? → out of scope

## 15. Semantic search & cohort isolation (post-embedding-backfill, 2026-09-23)

Every faculty/document answer here should be traceable to real data — no
faculty name or rule invented, no rule from one cohort presented as if it
applies to the other (CLAUDE.md §20). `>>` follow-ups test that a resolved
answer survives into the next turn without re-fetching from scratch.

### Faculty research topics — real matches (`scripts/eval_retrieval.py` confirmed real hits)
- Which faculty work on natural language processing? → Kashyap / Athira B / Sara Renjit or similar
- Who researches computer vision on campus? → Sivaiah Bellamkonda / Sreelakshmy I J or similar
- Which faculty specialise in VLSI design? → Lakshmi N S / Kala S or similar
- Who works on cryptography and network security? → Ragesh G K / A Balu / Amit Kumar Roy or similar
- Which faculty research wireless communication? → Emy Mariam George / Ananth A or similar

### Faculty research topics — should NOT match (tests the 0.65 similarity floor)
- Which faculty specialise in cooking recipes? → honest "no matching faculty" — must not surface language-teacher false positives (the pre-recalibration floor of 0.60 did)
- Recommend someone for quantum computing hardware. → honest no-match if nothing on file, never a fabricated name
- Is anyone researching medieval history? → honest no-match

### Cross-cohort regulation traps — student's own cohort is 2021-25
- What is the attendance requirement for students admitted in 2026? → cites the "26-onwards" regulations explicitly, not the student's own 21-25 rule
- Is the attendance rule different for the 2026 admission batch compared to mine? → states both cohort values explicitly and compares, doesn't blend them
- What is the maximum duration to complete the B.Tech under the 2026 regulations? → cites 26-onwards cohort, flags if it differs from the student's own answer (§7)
- How many total credits does the 2026 CSE curriculum require? → cites the ADM 2026 CSE curriculum document, not the 2021-25 CSE curriculum used elsewhere for this student

### Hybrid (research match + live schedule)
- Which faculty work in machine learning and when could I meet them this week? → research match + teaching-schedule proxy, explicit that it's not confirmed office hours
- Recommend a faculty member for NLP research who's teaching soon. → ranked match + nearest upcoming class if any

### Follow-ups
- Which faculty work on computer vision?
>> Which of them teaches a class this week?
- What is the attendance requirement for the 2026 admission batch?
>> How is that different from mine?
