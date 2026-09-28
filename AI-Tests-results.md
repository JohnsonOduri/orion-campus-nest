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
