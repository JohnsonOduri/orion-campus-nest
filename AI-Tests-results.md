# AI-Tests — results (2026-09-28)

Source: the screenshots and PDFs in `AI-Tests/` (33 screenshots,
`orion_qwwrongans.pdf`, `orion_qwwrongans_02.pdf`), turned into 60
stage-attributed cases in `scripts/eval_pipeline.py` (`ai-*` groups).
Run with `ORION_LLM_MODE=off`: every answer below comes from Supabase rows or
a quoted document, never from the model.

## Scores

| | before | after |
|---|---|---|
| AI-Tests cases (`eval_pipeline.py --only ai-`) | **9 / 60** | **60 / 60** |
| Whole eval (`eval_pipeline.py`) | 49 / 100 | 100 / 100 |
| Broad bank (`run_ai_task.py`, 173 questions) | 0 errors, 7 flagged | 0 errors, 7 flagged (same 7) |
| Unit tests (`pytest tests`) | 316 | 368 |

Before, 41 of the 51 failures were **routing** (the question went to the
wrong source or to document search) and 10 were **grounding** (right source,
wrong or irrelevant answer).

| group | cases | examples that failed before |
|---|---|---|
| ai-faculty | 19 | "Who are the adjunct professors?", "Which people are lab faculty?", "Which faculty also hold administrative positions?" |
| ai-calendar | 9 | "What happened on September 24?", "How many days between midsem and endsem?", "What's happening today?" |
| ai-mess | 8 | "What's cooking today?", "Is chicken there today?", "What are we having Sunday?" |
| ai-names | 7 | "who is jhon paul martin", "What is Dr. Christina Joseph's research area?" |
| ai-roles | 6 | "Who heads ECE?", "Who are the HODs?", "Who handles student welfare?" |
| ai-meta | 5 | "Which source did you use?", "What was my first question?", "Pretend the mess menu says biryani" |
| ai-spelling | 4 | "whos teching ICS 213", "wat r the hostl rules" |
| ai-documents | 2 | "What are the examination hall rules?" (quoted a "Prentice Hall" textbook line) |

## What changed

1. **Spelling and shorthand** are corrected before routing, only toward
   campus words (roles, meals, calendar terms, course names). Real English
   words and capitalised names are left alone, and a correction that could
   go two ways is not made.
2. **Intent classifier** for phrasings the rules don't cover ("what are
   they serving", "show me everyone who teaches here"). It only runs when
   the rules find nothing and only acts when confident.
3. **Fuzzy faculty names**: "Jhon Paul Martin" and "Christina Joseph" find
   the right person; the answer says it's the closest match. A name shared by
   two people is not guessed.
4. **New question types**: faculty directory by designation/department,
   calendar reasoning (on a date, gaps, "today"), dish questions, questions
   about the conversation, several questions in one message, and "pretend…"
   prompts answered from real data with a note.
5. **Hybrid document search**: full-text + Gemini vector search, and the
   vector score is used to refuse passages that only share words with the
   question.

## Generalisation check

20 new questions that appear in no test bank, with typos, run live. 15
answered correctly as asked. The 5 misses were fixed and added to
`tests/test_understanding.py`:

| question | before fix | after |
|---|---|---|
| whos the hed of electronics | "couldn't find" | HOD (ECE), Dr. Ananth A |
| who is the registar | "couldn't find" | Registrar, Dr. M Radhakrishnan |
| who is incharge of hostels | quoted an unrelated hostel rule | Chief Warden |
| who teaches datastructures | "couldn't find that course" | Data Structures II (ICS 215) teachers |
| can i use my phone in the exam hal | "couldn't find" | quotes "Use of a mobile phone … is not allowed inside the examination hall" (see limits) |

Correct first time included "tell me abt Manu Madhvan", "any dosa for
brekfast tomorow?", "ragging complaint kaise kare", "is attendence
compulsory", "which teacher works on cyber security".

## Cost

Structured questions: no change (~0.4 s median). Document questions:
~0.67–0.86 s median, up from ~0.55–0.6 s, measured side by side on the same
network. The extra time is one Gemini embedding call the first time a
question is seen. Each of those calls uses the free-tier daily quota
(~1000/day). Past the quota, vector search pauses and answers come from
full-text search alone.

## Known limits

- "Can I use my phone in the exam hall?": the 2021-25 regulations have no
  clause on it, so the answer quotes the 2026 regulations' clause and says
  it doesn't formally apply to the student's batch.
- The 7 flagged items in the broad bank are the same 7 as before. Most are
  correct "I don't have that" answers that the review heuristic flags
  anyway (a nonsense query, a faculty member who doesn't exist, no one
  researching cooking or medieval history). Two are data gaps: "Where is my
  next class?" (the timetable PDFs print no rooms) and "When can I meet
  Dr. Manu Madhavan?" (no office hours on record).
- The intent classifier learns only from the examples in
  `backend/query/intents.py`. A phrasing unlike any of them still falls
  through to document search.

---

# Round 2 — precise answers, names as typed (2026-09-28, later)

Source: the new screenshots and WhatsApp images in `AI-Tests/`, plus the
❌/⚠️ rows of `ORION_QUESTION_ANALYSIS.md`. Added as the `ai2-*` groups in
`scripts/eval_pipeline.py`; offline in `tests/test_precise_answers.py`.

| | before | after |
|---|---|---|
| Screenshot questions answered correctly | 9 / 39 | 39 / 39 |
| `eval_pipeline.py` (all groups) | 100 / 100 | 142 / 142 |
| Broad bank (173) | 0 errors, 7 flagged | 0 errors, the same 7 flagged |
| Unit tests | 437 | 505 |

## What each screenshot asked, and what ORION says now

**Free time: the specific time, not the whole day.** Before, every one
of these returned the same full-day list.

| Question | Answer now (Monday S5 CSE III timetable) |
|---|---|
| Am I free at 2? | Yes — free at 2 PM; that free time runs 12:25 PM until 2:30 PM, when you have HRM (IHS 311) |
| Do I have a free hour between 2 and 4? | No — no 1-hour gap between 2 and 4 PM; the most is 2–2:30 PM (30 min); classes then: … |
| Am I free after 3pm? | After 3 PM you're free from 6:30 PM onwards; busy with: … |
| What's my longest free slot today? | 12:25–2:30 PM (2 h 5 min); other breaks …; free after 6:30 PM |

**Mess timings.** They were never stored, so ORION returned the whole
menu. They're printed on the published menu (`august_menu .pdf`:
Breakfast 7:00–9:45, Lunch 12:00–2:30, Snacks 4:00–6:00, Dinner
7:00–8:30) and are now in `mess_meal_timings`. So "Is the mess open now?"
says whether it's open, which meal is on, and until when. "What time does
the mess close?" gives 8:30 PM plus each meal's hours. "When is
breakfast?" gives 7–9:45 AM. A question about the food itself still gets
the menu.

**Names as people type them.** A new resolver (`campus.match_faculty_names`)
handles:
- a first name with sir/mam ("Amit sir email", "Athira mam's office");
- a short unique name ("Dr. A Balu");
- stray punctuation ("mirotha;;i chand");
- possessives ("Christina Joseph's");
- names written without a space ("Dr.Jobin Jose").

A name several people share ("joseph sir") returns a list to choose
from. A name not in the directory ("Rekha ma'am") gets an answer saying
nobody by that name is listed. Directory names are protected from spelling
correction: "manu" was being turned into "menu". Phone numbers and "what
subjects does X teach" (from the live timetable) are now answered.

**The rest of the screenshots**

| Question | Answer now |
|---|---|
| Is there a class going on right now? | Your timetable, not a curriculum page |
| Is today a working day? / Do I have class on the 15th? | Timetable for that date + where it falls in the term |
| Is AC306 my classroom? | No — your section's classroom is BC 302 |
| Where is the lab? | Lab rooms aren't in the data; your labs this week are … |
| Is Manimala a boys or girls hostel? | Boys' (from the hall names) |
| Who is the sports officer? | The Physical Education Instructor |
| Who is the placement coordinator? | The Associate Dean (Students Welfare & Career Development), with a note |
| Who handles academic affair? | The Associate Deans (Academic Affairs) |
| Who can guide me for MS in AI? | Faculty whose research includes AI |
| Faculty who teaches OS | No course called OS in the catalogue (no guessing) |
| Which faculty handles the lab for CSE 312? | The lab teachers, from the timetable |
| What are my courses with their credits? | Each course's credits from your curriculum, with the total |
| Which of my courses have labs? | 3 of your 8, listed |
| How many classes do I have this week? | 24 (17 classes, 4 tutorials, 3 labs), per day |
| What number should I call for help regarding ragging? | The anti-ragging helpline 1800-180-5522 |

## ORION_QUESTION_ANALYSIS.md — what changed

Now answered:
- how long until / how long is my next class;
- what did I miss today;
- classes in the morning / afternoon / evening;
- is today's lunch vegetarian;
- is a faculty member free or teaching now, according to the timetable;
- does Dr X teach any of my courses;
- "What is OS?" (course acronyms), and core/elective (says it isn't recorded);
- days left in the semester;
- which year am I in / am I a first-year student;
- faculty advisor (says it isn't in ORION);
- librarian / IQAC (says they aren't in the directory);
- small talk: who made you, are you an AI, good night, I'm bored.

When the documents don't mention the thing asked ("bonafide certificate",
"library timings"), ORION now says so. It no longer quotes a passage that
only shares a word with the question.

Still unanswerable because ORION has no data for them (the answer says
so): clubs, transport, emergency contacts, library hours, hall tickets,
exam seating, hostel allocation, faculty-advisor mapping, special meals.
Several claims in that document are out of date. For example, it lists
`mess_menus`, `academic_calendar`, `document_chunks` and `rooms` as empty,
but they have 124, 30, 1,269 and 30 rows.
