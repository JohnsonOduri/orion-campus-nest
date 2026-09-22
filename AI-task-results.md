# ORION AI-task results — 2026-09-22 16:53 UTC

Signed in as `orion-test-student-a@iiitkottayam.ac.in` (Semester 3, CSE section I). Answers come from `backend/app/api/ai.answer()`, the function behind `POST /ai/ask`. LLM rewording: **off**.

**134 questions** · 0 errors · 3 flagged for review · median 125 ms · p95 300 ms

## 1. Greetings, help, small talk

### Hi
`small_talk` · `none` · 173 ms · composer
*Expected:* greeting + what ORION can help with

Good evening! I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations.

### hello there
`small_talk` · `none` · 57 ms · composer
*Expected:* greeting

Good evening! I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations.

### Good morning
`small_talk` · `none` · 54 ms · composer
*Expected:* greeting

Good evening! I'm ORION — ask me about your timetable, mess menu, courses, faculty, or campus regulations.

### What can you do?
`small_talk` · `none` · 56 ms · composer
*Expected:* capability list

I'm ORION, your campus assistant. I can help with: your timetable (today, a specific day, a specific time, tomorrow/yesterday), the mess menu (today, this week, a specific meal or day), course info (credits, syllabus, prerequisites), faculty details (email, office, office hours), who teaches a course, faculty who work in a research area, and campus regulations/policies. Just ask in your own words!

### Who are you?
`small_talk` · `none` · 57 ms · composer
*Expected:* introduces ORION

I'm ORION, your campus assistant. I can help with: your timetable (today, a specific day, a specific time, tomorrow/yesterday), the mess menu (today, this week, a specific meal or day), course info (credits, syllabus, prerequisites), faculty details (email, office, office hours), who teaches a course, faculty who work in a research area, and campus regulations/policies. Just ask in your own words!

### How are you?
`small_talk` · `none` · 54 ms · composer
*Expected:* friendly reply

All good here! What do you need help with today?

### Thanks!
`small_talk` · `none` · 56 ms · composer
*Expected:* acknowledgement

No problem at all — ask away if you need anything else.

### Bye
`small_talk` · `none` · 92 ms · composer
*Expected:* farewell

See you! Come back anytime you need campus info.

## 2. Timetable — now, today, specific days

### What is my next class?
`structured` · `next_class` · 128 ms · composer
*Expected:* course, day, time, teacher

Your next class is **IT Workshop III (ICS 214)** — tomorrow (Wednesday), 10:00–10:55 AM — Dr. Deepak Jose · lab. You have no more classes today.

*Source: your live timetable*

### What class is going on right now?
`structured` · `next_class` · 113 ms · composer
*Expected:* current or next class

You don't have a class right now. Your next class is **IT Workshop III (ICS 214)** — tomorrow (Wednesday), 10:00–10:55 AM — Dr. Deepak Jose · lab. You have no more classes today.

*Source: your live timetable*

### What classes do I have today?
`structured` · `day_timetable` · 121 ms · composer
*Expected:* full list for today with times

Here's your timetable today:

- **9:00–9:55 AM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(done)*
- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose *(done)*
- **11:05 AM – 12:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S *(done)*
- **12:05–1:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(done)*
- **2:00–2:55 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S · tutorial *(done)*
- **5:00–7:00 PM** · Physical Training (IPT 211) — Ms. Priya Mol K *(done)*

*Source: your live timetable*

### What's my timetable for tomorrow?
`structured` · `day_of_week_timetable` · 113 ms · composer
*Expected:* tomorrow's list

Here's your timetable tomorrow:

- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose · lab
- **11:05 AM – 12:00 PM** · Probability, Statistics and Random Processes (IMA 211) — Dr. Anandhu Mohan
- **12:05–1:00 PM** · ICS
- **3:00–3:55 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit · lab
- **4:00–4:55 PM** · Introduction to Bioinformatics (ISC 211) — Dr. Jayakrushna Sahoo
- **5:00–7:00 PM** · Coding Club Activities — club activity

*Source: your live timetable*

### What classes do I have on Monday?
`structured` · `day_of_week_timetable` · 114 ms · composer
*Expected:* Monday list

Here's your timetable on Monday (28 September):

- **9:00–9:55 AM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **11:05 AM – 12:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph
- **12:05–1:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **2:00–2:55 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph · tutorial
- **3:00–3:55 PM** · FA Interaction
- **5:00–7:00 PM** · Coding Club Activities — club activity

*Source: your live timetable*

### Do I have classes on Saturday?
`structured` · `day_of_week_timetable` · 115 ms · composer
*Expected:* Saturday list or "no classes"

You have no classes on Saturday (26 September).

### Do I have any class on Sunday?
`structured` · `day_of_week_timetable` · 112 ms · composer
*Expected:* "no classes on Sunday"

You have no classes on Sunday. Enjoy the weekend!

### What did I have yesterday?
`structured` · `day_of_week_timetable` · 121 ms · composer
*Expected:* yesterday's list

Here's your timetable yesterday:

- **9:00–9:55 AM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **11:05 AM – 12:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph
- **12:05–1:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **2:00–2:55 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph · tutorial
- **3:00–3:55 PM** · FA Interaction
- **5:00–7:00 PM** · Coding Club Activities — club activity

*Source: your live timetable*

### What is my timetable for this week?
`structured` · `week_timetable` · 121 ms · composer
*Expected:* grouped by day

Here's your timetable for this week:

**Monday**
- **9:00–9:55 AM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **11:05 AM – 12:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph
- **12:05–1:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **2:00–2:55 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph · tutorial
- **3:00–3:55 PM** · FA Interaction
- **5:00–7:00 PM** · Coding Club Activities — club activity

**Tuesday**
- **9:00–9:55 AM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph
- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose
- **11:05 AM – 12:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S
- **12:05–1:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph
- **2:00–2:55 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S · tutorial
- **5:00–7:00 PM** · Physical Training (IPT 211) — Ms. Priya Mol K

**Wednesday**
- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose · lab
- **11:05 AM – 12:00 PM** · Probability, Statistics and Random Processes (IMA 211) — Dr. Anandhu Mohan
- **12:05–1:00 PM** · ICS
- **3:00–3:55 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit · lab
- **4:00–4:55 PM** · Introduction to Bioinformatics (ISC 211) — Dr. Jayakrushna Sahoo
- **5:00–7:00 PM** · Coding Club Activities — club activity

**Thursday**
- **9:00–9:55 AM** · Database Management Systems (ICS 213) — Dr. Vengadeswaran S
- **10:00–10:55 AM** · Probability, Statistics and Random Processes (IMA 211) — Dr. Anandhu Mohan
- **11:05 AM – 12:00 PM** · Database Management Systems (ICS 213) — Dr. Vengadeswaran S · lab
- **2:00–2:55 PM** · Probability, Statistics and Random Processes (IMA 211) — Dr. Anandhu Mohan · tutorial
- **3:00–3:55 PM** · IT Workshop III (ICS 214) — Dr. Deepak Jose · tutorial
- **4:00–4:55 PM** · Introduction to Bioinformatics (ISC 211) — Dr. Jayakrushna Sahoo
- **5:00–7:00 PM** · Coding Club Activities — club activity

**Friday**
- **9:00–9:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose
- **10:00–10:55 AM** · Probability, Statistics and Random Processes (IMA 211) — Dr. Anandhu Mohan
- **11:05 AM – 12:00 PM** · Database Management Systems (ICS 213) — Dr. Vengadeswaran S
- **12:05–1:00 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit
- **2:00–2:55 PM** · Technical Club Activities — club activity
- **3:00–3:55 PM** · Technical Club Activities — club activity
- **4:00–4:55 PM** · Technical Club Activities — club activity
- **5:00–7:00 PM** · Coding Club Activities — club activity

*Source: your live timetable*

### What class do I have at 10 AM?
`structured` · `class_at_time` · 177 ms · composer
*Expected:* class covering 10 AM

At 10:00 AM you have **IT Workshop III (ICS 214)** (10:00–10:55 AM) — Dr. Deepak Jose. After that, your next class is **Design and Analysis of Algorithms (ICS 211)** today (Tuesday), 11:05 AM – 12:00 PM — Dr. Priyadharshini S.

*Source: your live timetable*

### What class do I have at 5 PM?
`structured` · `class_at_time` · 179 ms · composer
*Expected:* class covering 5 PM

At 5:00 PM you have **Physical Training (IPT 211)** (5:00–7:00 PM) — Ms. Priya Mol K. After that, your next class is **IT Workshop III (ICS 214)** tomorrow (Wednesday), 10:00–10:55 AM — Dr. Deepak Jose · lab.

*Source: your live timetable*

### What is my first class tomorrow?
`structured` · `day_of_week_timetable` · 123 ms · composer
*Expected:* earliest class tomorrow

Your first class tomorrow is **IT Workshop III (ICS 214)** at 10:00 AM (10:00–10:55 AM) — Dr. Deepak Jose · lab.

*Source: your live timetable*

### When does my last class end today?
`structured` · `day_timetable` · 121 ms · composer
*Expected:* end time of last class

Your last class today is **Physical Training (IPT 211)**, which ends at **7:00 PM** — Ms. Priya Mol K.

*Source: your live timetable*

### How many classes do I have today?
`structured` · `day_timetable` · 115 ms · composer
*Expected:* count + list

You have **6 classes** today:

- **9:00–9:55 AM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(done)*
- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose *(done)*
- **11:05 AM – 12:00 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S *(done)*
- **12:05–1:00 PM** · Theory of Computation (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(done)*
- **2:00–2:55 PM** · Design and Analysis of Algorithms (ICS 211) — Dr. Priyadharshini S · tutorial *(done)*
- **5:00–7:00 PM** · Physical Training (IPT 211) — Ms. Priya Mol K *(done)*

*Source: your live timetable*

### When am I free today?
`structured` · `free_time` · 117 ms · composer
*Expected:* gaps between classes

You're free today 1:00–2:00 PM, 2:55–5:00 PM and after 7:00 PM.

Your classes today: 9:00–9:55 AM Theory of Computation (ICS 212); 10:00–10:55 AM IT Workshop III (ICS 214); 11:05 AM – 12:00 PM Design and Analysis of Algorithms (ICS 211); 12:05–1:00 PM Theory of Computation (ICS 212); 2:00–2:55 PM Design and Analysis of Algorithms (ICS 211); 5:00–7:00 PM Physical Training (IPT 211).

*Source: your live timetable*

### When is my Data Structures class this week?
`structured` · `week_timetable` · 121 ms · composer
*Expected:* matching slots

Your **Data Structures II (ICS 215)** sessions this week:

**Wednesday**
- **3:00–3:55 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit · lab

**Friday**
- **12:05–1:00 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit

*Source: your live timetable*

### Which labs do I have this week?
`structured` · `week_timetable` · 127 ms · composer
*Expected:* lab entries only

Your labs this week:

**Wednesday**
- **10:00–10:55 AM** · IT Workshop III (ICS 214) — Dr. Deepak Jose · lab
- **3:00–3:55 PM** · Data Structures II (ICS 215) — Dr. Sara Renjit · lab

**Thursday**
- **11:05 AM – 12:00 PM** · Database Management Systems (ICS 213) — Dr. Vengadeswaran S · lab

*Source: your live timetable*

### Who teaches my next class?
`structured` · `next_class` · 116 ms · composer
*Expected:* faculty of next class

Dr. Deepak Jose teaches your next class, **IT Workshop III (ICS 214)** — tomorrow (Wednesday), 10:00–10:55 AM.

*Source: your live timetable*

### Where is my next class?
`structured` · `classroom` · 175 ms · composer · ⚠️ review
*Expected:* classroom, or honest note that rooms aren't printed

Your section's classroom this semester is **BC 302**. Your next class is **IT Workshop III (ICS 214)** — tomorrow (Wednesday), 10:00–10:55 AM. It's a lab, so it will be in the lab rather than the classroom. (The timetable doesn't list a room for each class, so this is your section's allocated room.)

*Source: classroom allocation, Odd semester 2026; your live timetable*

## 3. Courses

### What courses do I have this semester?
`structured` · `my_courses` · 124 ms · composer
*Expected:* distinct courses from own timetable

You have **8 courses** this semester:

- **Design and Analysis of Algorithms** (ICS 211) — Dr. Priyadharshini S *(tutorial)*
- **Theory of Computation** (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(tutorial)*
- **Database Management Systems** (ICS 213) — Dr. Vengadeswaran S *(lab)*
- **IT Workshop III** (ICS 214) — Dr. Deepak Jose *(lab, tutorial)*
- **Data Structures II** (ICS 215) — Dr. Sara Renjit *(lab)*
- **Probability, Statistics and Random Processes** (IMA 211) — Dr. Anandhu Mohan *(tutorial)*
- **Physical Training** (IPT 211) — Ms. Priya Mol K
- **Introduction to Bioinformatics** (ISC 211) — Dr. Jayakrushna Sahoo

*Source: your live timetable*

### List my subjects
`structured` · `my_courses` · 117 ms · composer
*Expected:* same

You have **8 courses** this semester:

- **Design and Analysis of Algorithms** (ICS 211) — Dr. Priyadharshini S *(tutorial)*
- **Theory of Computation** (ICS 212) — Dr Divya Sindhu Lekha and Dr. Sushitha Susan Joseph *(tutorial)*
- **Database Management Systems** (ICS 213) — Dr. Vengadeswaran S *(lab)*
- **IT Workshop III** (ICS 214) — Dr. Deepak Jose *(lab, tutorial)*
- **Data Structures II** (ICS 215) — Dr. Sara Renjit *(lab)*
- **Probability, Statistics and Random Processes** (IMA 211) — Dr. Anandhu Mohan *(tutorial)*
- **Physical Training** (IPT 211) — Ms. Priya Mol K
- **Introduction to Bioinformatics** (ISC 211) — Dr. Jayakrushna Sahoo

*Source: your live timetable*

### Tell me about ICS 211
`structured` · `course_info` · 462 ms · composer
*Expected:* course name, semester, what's on file

**Design and Analysis of Algorithms** (ICS 211) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 3-1-0).

Taught by Dr. Priyadharshini S, Dr. Jisha Mariyam John, Dr. Manu Madhavan and Dr. Nandini J. Warrier.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 2*

### What is ICS 212 about?
`structured` · `course_info` · 294 ms · composer
*Expected:* course info

**Theory of Computation** (ICS 212) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 3-1-0).

Taught by Dr Divya Sindhu Lekha, Dr. Krishnendhu S P, Dr. Rosebell Paul and Dr. Jaisooraj J.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 15*

### Who teaches ICS 213?
`structured` · `faculty_for_course` · 224 ms · composer
*Expected:* faculty list

**Database Management Systems** (ICS 213) is taught by Dr. Vengadeswaran S, Dr. Syamala S, Dr. Amit Kumar Roy and Dr. E. Silambarasan. Different sections may have different teachers.

- Dr. Vengadeswaran S — vengadesh@iiitkottayam.ac.in
- Dr. Syamala S — syamala@iiitkottayam.ac.in
- Dr. Amit Kumar Roy — amit@iiitkottayam.ac.in
- Dr. E. Silambarasan — silambarasan@iiitkottayam.ac.in

*Source: your live timetable; faculty directory*

### Who teaches Database Management Systems?
`structured` · `faculty_for_course` · 228 ms · composer
*Expected:* resolves course by name

**Database Management Systems** (ICS 213) is taught by Dr. Vengadeswaran S, Dr. Syamala S, Dr. Amit Kumar Roy and Dr. E. Silambarasan. Different sections may have different teachers.

- Dr. Vengadeswaran S — vengadesh@iiitkottayam.ac.in
- Dr. Syamala S — syamala@iiitkottayam.ac.in
- Dr. Amit Kumar Roy — amit@iiitkottayam.ac.in
- Dr. E. Silambarasan — silambarasan@iiitkottayam.ac.in

*Source: your live timetable; faculty directory*

### Who teaches Theory of Computation?
`structured` · `faculty_for_course` · 233 ms · composer
*Expected:* resolves course by name

**Theory of Computation** (ICS 212) is taught by Dr Divya Sindhu Lekha, Dr. Krishnendhu S P, Dr. Rosebell Paul and Dr. Jaisooraj J. Different sections may have different teachers.

- Dr Divya Sindhu Lekha — divyaslekha@iiitkottayam.ac.in
- Dr. Krishnendhu S P — krishnendhu@iiitkottayam.ac.in
- Dr. Rosebell Paul — rosebell@iiitkottayam.ac.in
- Dr. Jaisooraj J — jaisooraj@iiitkottayam.ac.in

*Source: your live timetable; faculty directory*

### How many credits is ICS 213?
`structured` · `course_info` · 297 ms · composer
*Expected:* credits if on file, else honest + curriculum pointer

**Database Management Systems** (ICS 213) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 2-1-2).

Taught by Dr. Vengadeswaran S, Dr. Syamala S, Dr. Amit Kumar Roy and Dr. E. Silambarasan.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech AI & DS Curriculum (2021-25 batch), p. 2*

### Which semester is Data Structures II taught in?
`structured` · `course_info` · 397 ms · composer
*Expected:* semester 3

**Data Structures II** (ICS 215) is a semester 3 B.Tech course. It carries **2 credits** (lecture-tutorial-practical: 1-0-2).

Taught by Dr. Sara Renjit, Dr. Dhakshayani J and Dr. Sivaiah Bellamkonda.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 18*

### What is IT Workshop III?
`structured` · `course_info` · 328 ms · composer
*Expected:* course info

**IT Workshop III** (ICS 214) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 2-1-2).

Taught by Dr. Deepak Jose, Dr. P. Victer Paul, Dr. R Tharaniya Sairaj and Dr. Alkha Mohan.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 5*

## 4. Faculty — contact, roles, research

### What is Dr. Manu Madhavan's email?
`structured` · `faculty_lookup` · 137 ms · composer
*Expected:* email

Dr. Manu Madhavan's email is **manum@iiitkottayam.ac.in**.

*Source: faculty directory*

### Where is Dr. Manu Madhavan's office?
`structured` · `faculty_lookup` · 129 ms · composer
*Expected:* office location

Dr. Manu Madhavan's office is **BC 307**. Email: manum@iiitkottayam.ac.in.

*Source: faculty directory*

### Tell me about Dr. Manu Madhavan
`structured` · `faculty_lookup` · 130 ms · composer
*Expected:* profile incl. research interests

**Dr. Manu Madhavan** (MM)
- Assistant Professor
- Email: manum@iiitkottayam.ac.in
- Office: BC 307
- Research: Natural Language Processing; Bioinformatics; Machine Learning; Computational Linguistics; Deep Learning, Graph Neural Networks

*Source: faculty directory*

### What is the email of Dr. Vengadeswaran S?
`structured` · `faculty_lookup` · 114 ms · composer
*Expected:* email or "not on file"

Dr. Vengadeswaran S's email is **vengadesh@iiitkottayam.ac.in**.

*Source: faculty directory*

### Who is the HOD of Computer Science?
`structured` · `faculty_role` · 120 ms · composer
*Expected:* HOD(s) with contacts

Here's who holds that role:

- **Dr. Rubell Marion Lincy G** — HOD(Computer Science & Engineering-2) · lincy@iiitkottayam.ac.in · 0482-2202152 · office BC 317 / AB 219
- **Dr. Christina Terese Joseph** — HOD(Computer Science & Engineering-1) · christina@iiitkottayam.ac.in · 0482-2202190, 0482-2202173 · office AA 108 / AC 318

*Source: faculty directory*

### Who is the HOD of ECE?
`structured` · `faculty_role` · 122 ms · composer
*Expected:* HOD ECE

**Dr. Ananth A** is the HOD (Electronics & Communication Engineering). Contact: ananth@iiitkottayam.ac.in · 0482-2202176 · office AB 208 / AC 313.

*Source: faculty directory*

### Who is the Registrar?
`structured` · `faculty_role` · 116 ms · composer
*Expected:* registrar

**Dr. M Radhakrishnan** is the Registrar, IIIT Kottayam. Contact: registrar@iiitkottayam.ac.in · +91 0482-2202100.

*Source: faculty directory*

### Who is the Associate Dean of Academic Affairs?
`structured` · `faculty_role` · 140 ms · composer
*Expected:* dean

Here's who holds that role:

- **Dr. Ebin Deni Raj** — Associate Dean (Academic Affairs) · ebindeniraj@iiitkottayam.ac.in · +91 (0) 482-2202195 · office AC 308 / AA 117
- **Dr Divya Sindhu Lekha** — Associate Dean (Academic Affairs-PG) · divyaslekha@iiitkottayam.ac.in · +91 (0) 482-2202161 · office BD 417 / AA 116

*Source: faculty directory*

### Is there a medical officer on campus?
`structured` · `faculty_role` · 115 ms · composer
*Expected:* medical officer contact

Here are the campus medical contacts:

- **Dr. Rani Stanly** — Medical Officer · mo1@iiitkottayam.ac.in · +91 0482-2202132 · office BB 203
- **Dr. Radhakrishnan Nair** — Medical Officer · mo2@iiitkottayam.ac.in · +91 0482-2202132 · office BB 203

*Source: faculty directory*

### Is there a counsellor or psychologist I can talk to?
`structured` · `faculty_role` · 125 ms · composer
*Expected:* psychologist

Yes — the institute has a psychologist you can reach out to:

- **Ms. Renjitha T.R** — Psychologist · counsellor@iiitkottayam.ac.in · +91 0482-2202107 · office AB 209 D
- **Ms. Anjali Girish** — Psychologist · counsellor1@iiitkottayam.ac.in · +91 0482-2202240 · office BB 203

*Source: faculty directory*

### Which faculty work on Natural Language Processing?
`hybrid` · `faculty_research` · 123 ms · composer
*Expected:* matching faculty

9 faculty list **Natural Language Processing** among their research interests — here are the 5 for whom it's most central:

**Dr. Manu Madhavan** — Assistant Professor · manum@iiitkottayam.ac.in · office BC 307
- Research: Natural Language Processing; Bioinformatics; Machine Learning; Computational Linguistics; Deep Learning, Graph Neural Networks

**Dr. Sara Renjit** — Assistant Professor · sararenjit@iiitkottayam.ac.in · office CAB 202 F
- Research: Natural Language Processing; Software Engineering; Machine Learning; Database Management Systems; Deep Learning; Explainable AI; DevOps & Agile

**Dr. Athira B** — Assistant Professor · athirab@iiitkottayam.ac.in · office BB 213
- Research: Data Mining; Natural Language Processing; Health Informatics; Machine Learning

**Dr. Lavanya Settipalli** — Assistant Professor · lavanya@iiitkottayam.ac.in · office AB 204
- Research: Big Data Analytics; Natural Language Processing; Image Processing; Block Chain Technologies

**Dr. Balasubramanian P** — Assistant Professor · pbala@iiitkottayam.ac.in · office BD 408
- Research: Machine Learning; Deep Learning; Natural Language Processing; Social Network Analysis

*Source: faculty directory*

### Which faculty work on NLP and when can I meet them?
`hybrid` · `faculty_research` · 440 ms · composer
*Expected:* faculty + teaching schedule, no invented office hours

9 faculty list **NLP** among their research interests — here are the 5 for whom it's most central:

**Dr. Manu Madhavan** — Assistant Professor · manum@iiitkottayam.ac.in · office BC 307
- Research: Natural Language Processing; Bioinformatics; Machine Learning; Computational Linguistics; Deep Learning, Graph Neural Networks
- Teaching (busy): Mon 11:05 AM – 12:00 PM; Mon 2:00–2:55 PM; Tue 10:00–10:55 AM; Tue 12:05–1:00 PM; Tue 1:05–2:00 PM; Tue 3:00–3:55 PM

**Dr. Sara Renjit** — Assistant Professor · sararenjit@iiitkottayam.ac.in · office CAB 202 F
- Research: Natural Language Processing; Software Engineering; Machine Learning; Database Management Systems; Deep Learning; Explainable AI; DevOps & Agile
- Teaching (busy): Mon 11:00–11:55 AM; Mon 1:05–2:00 PM; Tue 12:05–1:00 PM; Tue 1:05–2:00 PM; Wed 11:00–11:55 AM; Wed 2:00–2:55 PM

**Dr. Athira B** — Assistant Professor · athirab@iiitkottayam.ac.in · office BB 213
- Research: Data Mining; Natural Language Processing; Health Informatics; Machine Learning
- Teaching (busy): Tue 11:30 AM – 12:25 PM; Tue 12:30–1:25 PM; Tue 9:30–10:25 AM; Wed 12:30–1:25 PM; Thu 12:30–1:25 PM

**Dr. Lavanya Settipalli** — Assistant Professor · lavanya@iiitkottayam.ac.in · office AB 204
- Research: Big Data Analytics; Natural Language Processing; Image Processing; Block Chain Technologies
- Teaching (busy): Wed 12:30–1:25 PM; Thu 3:30–4:25 PM; Thu 4:30–5:25 PM; Thu 9:30–10:25 AM; Fri 10:30–11:25 AM

**Dr. Balasubramanian P** — Assistant Professor · pbala@iiitkottayam.ac.in · office BD 408
- Research: Machine Learning; Deep Learning; Natural Language Processing; Social Network Analysis

None of them have office hours on file, so I can't confirm when they're free. Their teaching slots above are when they're busy — email is the best way to set up a meeting.

*Source: faculty directory; your live timetable*

### Recommend a faculty member for machine learning research.
`hybrid` · `faculty_research` · 130 ms · composer
*Expected:* ranked faculty

39 faculty list **machine learning** among their research interests — here are the 5 for whom it's most central:

**Dr. Balasubramanian P** — Assistant Professor · pbala@iiitkottayam.ac.in · office BD 408
- Research: Machine Learning; Deep Learning; Natural Language Processing; Social Network Analysis

**Dr. Cinu C Kiliroor** — Assistant Professor · cinu@iiitkottayam.ac.in · office AB 222
- Research: Machine Learning; Data Science; AI for Social Good- Agriculture; Image Processing

**Dr. Lidiya Lilly Thampi** — Assistant Professor · lidiya@iiitkottayam.ac.in · office AB 207
- Research: Machine Learning; Underwater Imaging; Medical Image Processing

**Dr. N.K Narayanan** — Adjunct Faculty
- Research: Machine Learning; Soft Computing; Computer Vision; Data Science; Computational Science & Engineering; Computer Speech & Natural Language Technology

**Dr. Sujamol S** — Adjunct Faculty · sujamol@iiitkottayam.ac.in
- Research: Machine Learning; Soft Computing; Computational Biology; Bioinformatics

*Source: faculty directory*

### Who researches computer vision?
`hybrid` · `faculty_research` · 128 ms · composer
*Expected:* matching faculty

13 faculty list **computer vision** among their research interests — here are the 5 for whom it's most central:

**Dr. Dhakshayani J** — Assistant Professor · dhakshayani@iiitkottayam.ac.in · office AB 209 F
- Research: Computer Vision; Machine Learning; Deep Learning; Image Processing; Precision Agriculture; High Throughput Phenotyping; Multimodal AI

**Dr. Jeena Thomas** — Assistant Professor · jeenathomas@iiitkottayam.ac.in · office BA 101 C
- Research: Computer Vision; Responsible Artificial Intelligence; Explainable AI (XAI); Vision Language Models; Deep Learning; AI for Social Good

**Dr. Sivaiah Bellamkonda** — Assistant Professor · sivaiah@iiitkottayam.ac.in · office AA 104
- Research: Computer Vision; Machine Learning; Image Processing

**Dr. Sreeja M U** — Assistant Professor · sreeja@iiitkottayam.ac.in · office AB 206
- Research: Computer Vision; Machine Learning; Deep learning; Explainable AI for healthcare; Video summarization

**Dr. Sreelakshmy I J** — Assistant Professor · sreelakshmy@iiitkottayam.ac.in · office CAB 202 G
- Research: Computer Vision; Machine Learning; Deep Learning; Image Processing

*Source: faculty directory*

### Who works on cyber security?
`hybrid` · `faculty_research` · 126 ms · composer
*Expected:* matching faculty

18 faculty list **cyber security** among their research interests — here are the 5 for whom it's most central:

**Dr. Arun Cyril Jose** — HOD (CSE-Cyber Security) · aruncyril@iiitkottayam.ac.in · office AA 122
- Research: Smart Home Security; Device Fingerprinting; Logical Sensing from a Security Point of View; Behaviour Prediction from a Security Point of View; Different Surveillance Techniques; Security Based Social Engineering; Completely Anonymous Communication Over the Internet

**Dr.S.Jai Ganesh** — Assistant Professor · jaiganesh@iiitkottayam.ac.in · office AC 304 A
- Research: Information Security; Artificial Intelligence for Cyber Security; Web Application Security

**Dr. Deepak Jose** — Assistant Professor · deepakjose@iiitkottayam.ac.in · office AB 209 B
- Research: Networking Security in IoT devices; Wireless mesh networking; Device fingerprinting for cyber security; Spatial Modulation; Detection and estimation problems in IRS-assisted wireless systems.; Orthogonal time frequency space (OTFS) modulation

**Dr. E. Silambarasan** — Assistant Professor · silambarasan@iiitkottayam.ac.in · office BB 211
- Research: Cloud Data Security; Security Protocols; Cryptography; Web Mining; AI based Malware analysis; Privacy preserving healthcare data using federated learning

**Dr. J. V. Bibal Benifa** — Associate Dean (Students Welfare & Career Development Services) · benifa@iiitkottayam.ac.in · office AA 113/AB 216
- Research: Cloud Computing and security; Big data analytics; Image Processing; Machine Learning

*Source: faculty directory*

### Who researches underwater sensor networks?
`hybrid` · `faculty_research` · 131 ms · composer
*Expected:* Dr. Jalaja M J (or honest no match)

1 faculty list **underwater sensor networks** among their research interests:

**Dr. JALAJA M J** — Adjunct Professor · jalaja@iiitkottayam.ac.in · office CAB 103 D
- Research: Wireless Sensor Networks and IoT; Underwater Communication; Underwater Sensor Networks; Indian Knowledge Systems; Educational Technology

*Source: faculty directory*

### Is anyone working on blockchain?
`hybrid` · `faculty_research` · 127 ms · composer
*Expected:* matches or honest no match

1 faculty list **blockchain** among their research interests:

**Dr. Lavanya Settipalli** — Assistant Professor · lavanya@iiitkottayam.ac.in · office AB 204
- Research: Big Data Analytics; Natural Language Processing; Image Processing; Block Chain Technologies

*Source: faculty directory*

### When can I meet Dr. Manu Madhavan?
`structured` · `faculty_lookup` · 230 ms · composer
*Expected:* teaching schedule, explicit that office hours aren't on file

ORION doesn't have office hours on file for **Dr. Manu Madhavan**, so I can't confirm when they're free. They teach at these times, so they'll be busy then:

- Monday 11:05 AM – 12:00 PM (ICS 211)
- Monday 2:00–2:55 PM (ICS 211)
- Tuesday 10:00–10:55 AM (ICS 211)
- Tuesday 12:05–1:00 PM (CSE 413)
- Tuesday 1:05–2:00 PM (CSE 413)
- Tuesday 3:00–3:55 PM (CSE 413)
- Wednesday 11:00–11:55 AM (CSE 413)
- Thursday 9:00–9:55 AM (ICS 211)
- Thursday 4:00–4:55 PM (CSE 413)

The reliable way is to email them to set a time: **manum@iiitkottayam.ac.in** (office: BC 307).

*Source: faculty directory; your live timetable*

## 5. Mess

### What is on the mess menu today?
`structured` · `mess_today` · 125 ms · composer
*Expected:* all meals, with staleness caveat if repeated cycle

**Tuesday, 22 September** (today)
- **Breakfast:** Vada Pav, Puttu, Channa Curry, Fried Chillies, Onions Green Chutney, Red Powdered Chutney, Bread (Normal/Brown) Jam, Butter, coffee, Milk, Banana
- **Lunch:** Tawa Pulao, Roti, ChettinadChicken, Chilli Paneer, Vegetable Raita, Salad Drink:Lemon juice/Litchi
- **Snacks:** Creambun, Bread, Jam, Butter, Tea, Milk
- **Dinner:** Rice, Roti, Chole curry, Onion Dal Tadka, Carrot Beans Thoran, Rasam, Chips Salad, Curd

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August). It may change.

*Source: mess menu*

### What's for lunch today?
`structured` · `mess_today` · 119 ms · composer
*Expected:* lunch only

Lunch on **Tuesday, 22 September** (today): Tawa Pulao, Roti, ChettinadChicken, Chilli Paneer, Vegetable Raita, Salad Drink:Lemon juice/Litchi.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August). It may change.

*Source: mess menu*

### What's for dinner tomorrow?
`structured` · `mess_on_day` · 117 ms · composer
*Expected:* dinner tomorrow

Dinner on **Wednesday, 23 September** (tomorrow): Vegetable Fried rice, Roti, Paneer Butter masala, Chilli chicken, Onionchilli Raita Drink: Passion Fruit drink.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (26 August). It may change.

*Source: mess menu*

### What is for breakfast on Monday?
`structured` · `mess_on_day` · 113 ms · composer
*Expected:* Monday breakfast

Breakfast on **Monday, 28 September**: Onion Uttapam, Medu vada, Sambar, Coconut Chutney, Bread (Normal/Brown) Jam, Butter, Tea, Milk, Corn Flakes.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (31 August). It may change.

*Source: mess menu*

### What is being served for dinner this week?
`structured` · `mess_week` · 118 ms · composer
*Expected:* dinner by day

**Monday, 21 September** (yesterday)
- **Dinner:** Rice, Roti, Egg roast, Beetroot thoran, Vegetable Kurma, Papad, curd, Salad

**Tuesday, 22 September** (today)
- **Dinner:** Rice, Roti, Chole curry, Onion Dal Tadka, Carrot Beans Thoran, Rasam, Chips Salad, Curd

**Wednesday, 23 September** (tomorrow)
- **Dinner:** Vegetable Fried rice, Roti, Paneer Butter masala, Chilli chicken, Onionchilli Raita Drink: Passion Fruit drink

**Thursday, 24 September**
- **Dinner:** Roti, Rice, Sambar, Potato fry, Kanji, Chammanthi, curd, Brinjal Curry, Salad Sweet: Rava Kesari

**Friday, 25 September**
- **Dinner:** Rice, Roti, Rajma curry, Spicy Dal Tadka, Rasam, Ivy Gourd Fry, Pulisherry, Salad, Sweet: Ada Payasam

**Saturday, 26 September**
- **Dinner:** Jeera Rice, Rice, Roti, Small Soya curry, Sambar, Puliseery, Chips, Curd, Salad Sweet: Vermicelli Payasam

**Sunday, 27 September**
- **Dinner:** Hyderabadi/Malabar Chicken Biryani, Paneer Biryani, Veg Gravy, Chicken Gravy, Onion Chilli Raita, Papad, Salad, Drink: Tang

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August, 26 August…). It may change.

*Source: mess menu*

### What are the snacks today?
`structured` · `mess_today` · 123 ms · composer
*Expected:* snacks

Snacks on **Tuesday, 22 September** (today): Creambun, Bread, Jam, Butter, Tea, Milk.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August). It may change.

*Source: mess menu*

### What did we have for dinner yesterday?
`structured` · `mess_on_day` · 116 ms · composer
*Expected:* yesterday dinner

Dinner on **Monday, 21 September** (yesterday): Rice, Roti, Egg roast, Beetroot thoran, Vegetable Kurma, Papad, curd, Salad.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (31 August). It may change.

*Source: mess menu*

## 6. Academic calendar and exams

### When do the end semester exams start?
`structured` · `academic_calendar` · 122 ms · composer
*Expected:* 2026-10-28

The **End Semester Examination** runs from **Wednesday, 28 October** to **Friday, 13 November** — it starts in 36 days.

*Source: academic calendar, Odd semester 2026-27*

### When do mid semester exams start?
`structured` · `academic_calendar` · 120 ms · composer
*Expected:* 2026-09-02 (already past — say so)

**Mid Semester Examination Starts** was on **Wednesday, 2 September** — that was 20 days ago, so it has already passed.

*Source: academic calendar, Odd semester 2026-27*

### When does the semester end?
`structured` · `academic_calendar` · 118 ms · composer
*Expected:* 2026-11-13

**End semester exams end and the semester ends** is on **Friday, 13 November** (in 52 days). The End Semester Examination starts on Wednesday, 28 October.

*Source: academic calendar, Odd semester 2026-27*

### When is the last instructional day?
`structured` · `academic_calendar` · 368 ms · composer
*Expected:* Class Ends 2026-10-26

**Last instructional day (classes end)** is on **Monday, 26 October** (in 34 days).

*Source: academic calendar, Odd semester 2026-27*

### What is the last date for course drop?
`structured` · `academic_calendar` · 126 ms · composer
*Expected:* 2026-07-30 (past)

**Last day for course drop** was on **Thursday, 30 July** — that was 54 days ago, so it has already passed.

*Source: academic calendar, Odd semester 2026-27*

### What are the upcoming deadlines?
`structured` · `academic_calendar` · 118 ms · composer
*Expected:* next deadlines from today

Here are the upcoming deadlines:

- **Wednesday, 21 October** — Submission of final attendance list to HoD · in 29 days
- **Wednesday, 25 November** — Last day for submission of grades · in 64 days
- **Sunday, 20 December** — Last date of fee payment without fine for Even Sem · in 89 days

*Source: academic calendar, Odd semester 2026-27*

### What's coming up on the academic calendar?
`structured` · `academic_calendar` · 115 ms · composer
*Expected:* next events

Coming up on the academic calendar:

- **Wednesday, 23 September** — Second Class Committee Meeting (S3, S5 & S7) · tomorrow
- **Thursday, 24 September** — Second Class Committee Meeting (S3, S5 & S7) · in 2 days
- **Friday, 25 September** — Sports Meet Starts · in 3 days
- **Sunday, 27 September** — Sports Meet Ends · in 5 days
- **Monday, 19 October** — B.Tech BTP / Honours / MS project final review · in 27 days
- **Wednesday, 21 October** — Submission of final attendance list to HoD · in 29 days

*Source: academic calendar, Odd semester 2026-27*

### When is the sports meet?
`structured` · `academic_calendar` · 155 ms · composer
*Expected:* 2026-09-25 to 2026-09-27

The **Sports Meet** runs from **Friday, 25 September** to **Sunday, 27 September** — it starts in 3 days.

*Source: academic calendar, Odd semester 2026-27*

### When will results be published?
`structured` · `academic_calendar` · 124 ms · composer
*Expected:* 2026-12-03

**Result Publication** is on **Thursday, 3 December** (in 72 days).

*Source: academic calendar, Odd semester 2026-27*

### When does the even semester start?
`structured` · `academic_calendar` · 117 ms · composer
*Expected:* 2026-12-21

**Even Semester 2026–27 Classes Begin** is on **Monday, 21 December** (in 90 days).

*Source: academic calendar, Odd semester 2026-27*

### When is the next class committee meeting?
`structured` · `academic_calendar` · 119 ms · composer
*Expected:* next meeting date

**Second Class Committee Meeting (S3, S5 & S7)** is on Wednesday, 23 September and Thursday, 24 September (tomorrow).

*Source: academic calendar, Odd semester 2026-27*

### When is registration for the even semester?
`structured` · `academic_calendar` · 123 ms · composer
*Expected:* 2026-12-14

**Registration starts online for Even Sem 2026-27** is on **Monday, 14 December** (in 83 days).

*Source: academic calendar, Odd semester 2026-27*

### When is my ICS 213 exam?
`structured` · `exam_schedule` · 188 ms · composer
*Expected:* per-course schedule not published; end-sem window

The exam timetable for **Database Management Systems** (ICS 213) hasn't been published in ORION yet. From the academic calendar, the end semester exams run from **Wednesday, 28 October** to **Friday, 13 November**, so it will fall in that window.

Other exam dates:

- **Thursday, 17 December** — Repeat Examination Starts · in 86 days
- **Monday, 28 December** — Last day for submission of grades for repeat exam. · in 97 days

*Source: academic calendar, Odd semester 2026-27*

### Are there any holidays this month?
`structured` · `academic_calendar` · 116 ms · composer · ⚠️ review
*Expected:* honest: calendar has no holiday entries

The academic calendar in ORION doesn't list any holidays for this semester. Coming up next:

- **Wednesday, 23 September** — Second Class Committee Meeting (S3, S5 & S7) · tomorrow
- **Thursday, 24 September** — Second Class Committee Meeting (S3, S5 & S7) · in 2 days
- **Friday, 25 September** — Sports Meet Starts · in 3 days

*Source: academic calendar, Odd semester 2026-27*

## 7. Regulations (answered for the student's cohort)

### What is the attendance requirement?
`semantic` · `none` · 248 ms · composer
*Expected:* 80%, cited to the 2021-25 regulations

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.5.2 The incomplete grade I is a transitional grade which will be given to the students who miss the end semester examinations under exceptional circumstances (eg. serious medical reasons) as determined by the course instructor/faculty advisor/Head of the department and approved by the Dean(Academics). Make up examination will be given to the students provided they meet the attendance requirements as per

*Source: UG Regulations (2021-25 batch), R.5.2, p. 7*

### What happens if my attendance is below 80%?
`semantic` · `none` · 198 ms · composer
*Expected:* consequence per regulations

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.5.3 Students having an attendance percentage between 65% to 80%, with valid/genuine reasons may be permitted to continue the course by paying a nominal penalty amount as decided by the competent authority. Students having an attendance percentage less than 65 will be awarded L grade.

*Source: UG Regulations (2021-25 batch), R.5.3, p. 7*

### Is there attendance condonation?
`semantic` · `none` · 194 ms · composer
*Expected:* condonation rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> Those students who have more than 80% attendance for the period other than their medical leave can be considered for condonation of attendance provided their overall attendance in a course including the period of illness does not fall below 50%. 14.12(5)/July2025 - 7/22

*Source: UG Regulations (2021-25 batch), p. 7*

### How is CGPA calculated?
`semantic` · `none` · 205 ms · composer
*Expected:* grading/CGPA rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> The CGPA based on the successfully completed courses is calculated; deleting the ‘F’ or ‘W’ grades, and is also shown separately in the grade card.
>
> R.7.3 A student should have a minimum CGPA of 5.0 calculated for the courses successfully completed at the end of each year. Students with CGPA below 5.0 at the end of each year, may be permitted to the next semester if he/she has less than 2 or exactly 2 backlogs.

*Source: UG Regulations (2021-25 batch), R.6.10 Grade Card, p. 11*

### What is the grading system?
`semantic` · `none` · 215 ms · composer
*Expected:* grade points

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> The letter grades and the corresponding grade points are as follows: Letter Grade Grade Points Remarks A 10 Excellent A- 9 Very good B 8 Good B- 7 Fair C 6 Average C- 5 Poor D 4 Pass F 0 Failed L 0 Insufficient Attendance I - Incomplete (Subsequently to be changed into valid grade) W - Withdrawal due to special circumstances U - Audit Course
>
> R.6.7 A student is considered to have completed a course successfully and earned the credits if he secures a letter grade other than F or W or I or U in that course. However, at the end of the programme (when required total credits are earned), the minimum CGPA requirement of passing the course is less than 5.5, the student is allowed to improve only those courses whose GP is less than 6 by repeating the course until the student earns a CGPA of 5.5 (limited to 5.5 if it is more than 5.5) within the stipulated maximum period (12 semesters) of the…

*Source: UG Regulations (2021-25 batch), p. 10*

### How many credits do I need to graduate?
`semantic` · `none` · 231 ms · composer
*Expected:* degree credit requirement

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.10.0 Credit Requirement The following table describes the minimum credit requirement and CGPA needed for the graduation. Minimum Credits Requirement Sl. No.

*Source: UG Regulations (2021-25 batch), R.10.0, p. 14*

### What is the maximum duration to complete the B.Tech?
`semantic` · `none` · 211 ms · composer
*Expected:* 12 semesters

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.7.4 Maximum Duration of the Programme A student is ordinarily expected to complete the B.Tech programme in eight semesters, and the dual degree programme in 10 semesters. However, a student may complete the B.Tech programme at a slower pace by taking more time, but in any case not more than 12 semesters excluding semesters withdrawn or medical grounds etc. as per R.7.5. However, the students have to satisfy

*Source: UG Regulations (2021-25 batch), R.7.4, p. 12*

### Can I take a summer term?
`semantic` · `none` · 207 ms · composer
*Expected:* summer term rule or honest

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.9.1 A summer term course (STC) maybe offered with the approval of the Director/ Deputy Director, if there are at least 5 students to take up the course. No student should register for more than two courses during a summer term, including contact course during summer.
>
> R.9.4 A Contact course may be offered during the regular semester or summer term ONLY to a final year student who has obtained F grade in a CORE course. The course will be offered ONLY on the recommendation of the department with the mutual agreement of the teacher and the student.

*Source: UG Regulations (2021-25 batch), R.9.1, p. 13*

### How do I drop a course?
`semantic` · `none` · 238 ms · composer
*Expected:* drop/withdrawal rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> If a student finds their load heavy in any semester, or for any other valid reason, the student may drop courses within three weeks of the commencement of the semester but before commencement of first test/ quiz with the written approval of his/her Faculty Adviser.

*Source: UG Regulations (2021-25 batch), p. 6*

### What happens if I fail a course?
`semantic` · `none` · 236 ms · composer
*Expected:* backlog/repeat rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> In cases where the student does not attend the end semester examination, he/she will be considered to have failed in the course and will be counted as a backlog.

*Source: UG Regulations (2021-25 batch), R.5.0 Attendance and Course Feedback, p. 7*

### What is an incomplete grade?
`semantic` · `none` · 195 ms · composer
*Expected:* I grade rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> The letter grades and the corresponding grade points are as follows: Letter Grade Grade Points Remarks A 10 Excellent A- 9 Very good B 8 Good B- 7 Fair C 6 Average C- 5 Poor D 4 Pass F 0 Failed L 0 Insufficient Attendance I - Incomplete (Subsequently to be changed into valid grade) W - Withdrawal due to special circumstances U - Audit Course
>
> R.6.7 A student is considered to have completed a course successfully and earned the credits if he secures a letter grade other than F or W or I or U in that course. However, at the end of the programme (when required total credits are earned), the minimum CGPA requirement of passing the course is less than 5.5, the student is allowed to improve only those courses whose GP is less than 6 by repeating the course until the student earns a CGPA of 5.5 (limited to 5.5 if it is more than 5.5) within the stipulated maximum period (12 semesters) of the…

*Source: UG Regulations (2021-25 batch), p. 10*

### Can I write a make-up exam if I miss the end semester exam?
`semantic` · `none` · 228 ms · composer
*Expected:* make-up rule

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.5.2 The incomplete grade I is a transitional grade which will be given to the students who miss the end semester examinations under exceptional circumstances (eg. serious medical reasons) as determined by the course instructor/faculty advisor/Head of the department and approved by the Dean(Academics). Make up examination will be given to the students provided they meet the attendance requirements as per R.5.3 and other academic requirement as per the rules and regulation of the institute. Actual grade after the make-up examination will be taken and will reflect in the transcript replacing the I grade. In case the student obtains F grade in the make-up examination, the student will be eligible to write the repeat end semester exam.

*Source: UG Regulations (2021-25 batch), R.5.2, p. 7*

### What is required for the B.Tech-MS dual degree?
`semantic` · `none` · 227 ms · composer
*Expected:* eligibility

From the **B.Tech Cyber Security Curriculum (2021-25 batch)**:

> B.TECH./B.TECH (HON)/DUAL DEGREE (B.TECH - MS) PROGRAMME Minimum Credits Requirement Sl. No. Course Description Period B.Tech B.Tech(Hon) B.Tech-MS 1 Institute Core/Foundation Courses 94 94 94 Semester I to IV 2 Bouquet Core Courses 24 24 24 Semester V to VIII 3 Stream Electives 18 18 18 Semester V to VIII 4 Institute Open Electives 9 9 9 Semester V to VIII 5 Humanities Electives 3 3 3 Semester V to VIII 6 Science Electives 3 3 3 Semester V to VIII 7 Maths Elective 3 3 3 Semester V to VIII 8 Engineering Elective 4 4 4 Semester V to VIII 9 Any other Electives/Industrial Training 4 4 4 Semester V to VIII 10 B.Tech Projects 12 12 12 Semester VII to VIII 11 Honours Project - 12 12 Semester VI to VIII 12 Research Courses - - 8 Semester VI to VIII 13 Research Project - - 24 Semester IX to X Total Credits required for Successful Completion 174 186 218 Minimum CGPA required for Successful…

*Source: B.Tech Cyber Security Curriculum (2021-25 batch), p. 6*

### What is the minimum CGPA to get the degree?
`semantic` · `none` · 256 ms · composer
*Expected:* minimum CGPA

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.2.7 The curriculum of any branch of the B.Tech programme is designed to have a total of 174 credits (minimum) for the award of the B.Tech degree with minimum CGPA of 5.5. For B.Tech Honours and dual degrees, the minimum credits are 186 and 218 respectively with minimum CGPA as 8.0.

*Source: UG Regulations (2021-25 batch), R.2.7, p. 5*

## 8. Hostel

### What are the hostel curfew rules?
`semantic` · `none` · 232 ms · composer
*Expected:* in-time / gate timings from hostel rules

From the **Hostel Rules and Regulations (July 2026)**:

> 30. Hostel Timings
>
> Outpass/Gate In: 9:00 PM
>
> Move to hostel from academic/hostel premises: 9:30 PM
>
> Move to hostel from classrooms: 10:30 PM
>
> Hostel main door closes: 11:00 PM

*Source: Hostel Rules and Regulations (July 2026), rule 30, p. 5*

### What time should I be back in the hostel?
`semantic` · `none` · 236 ms · composer
*Expected:* in-time

From the **Hostel Rules and Regulations (July 2026)**:

> 30. Hostel Timings
>
> Outpass/Gate In: 9:00 PM
>
> Move to hostel from academic/hostel premises: 9:30 PM
>
> Move to hostel from classrooms: 10:30 PM
>
> Hostel main door closes: 11:00 PM

*Source: Hostel Rules and Regulations (July 2026), rule 30, p. 5*

### How does the outpass process work?
`semantic` · `none` · 228 ms · composer
*Expected:* leave/outpass rule

From the **Hostel Rules and Regulations (July 2026)**:

> 3.1 Students must obtain permission through the Flee Outpass portal (https://outpass.iiitkottayam.ac.in/) or the Biometric Outpass system (https://gatepassstud.iiitkottayam.ac.in/) before leaving campus during weekends or nonacademic hours, provided the duration of absence does not exceed one day.

*Source: Hostel Rules and Regulations (July 2026), rule 3.1, p. 1*

### Can visitors come to the hostel?
`semantic` · `none` · 193 ms · composer
*Expected:* visitor rule

From the **Hostel Rules and Regulations (July 2026)**:

> Guests Guests are strictly prohibited from entering hostels rooms. Visiting hours are permitted only until 7:00 PM, and all guest meetings shall be restricted to the designated area at the main entrance, adjacent to the security guard's post. No guest shall be permitted beyond this point under any circumstances.

*Source: Hostel Rules and Regulations (July 2026), p. 4*

### Can I cook in my hostel room?
`semantic` · `none` · 197 ms · composer
*Expected:* electrical appliance / cooking rule

From the **Hostel Rules and Regulations (July 2026)**:

> Cooking and Electrical Appliances Cooking inside the rooms is strictly prohibited. Students are not permitted to use heaters, electric irons, or similar appliances of any kind consuming electricity in the rooms. Close water taps after use.

*Source: Hostel Rules and Regulations (July 2026), p. 3*

### Who is the warden of Sahyadri hostel?
`structured` · `hostel_wardens` · 127 ms · composer
*Expected:* warden(s) with phone/email

**Sahyadri Hostel (Girls)**
- Warden: **Dr. Kanchan Lata Kashyap** · 0482-2202272, 9826733258 · kanchanlata@iiitkottayam.ac.in
- Assistant warden: **Dr Suriyapriya** · 0482-2202254, 8610135747 · suriyapriya@iiitkottayam.ac.in
- Assistant warden: **Dr Dakshayani** · 0482-2202275, 9578359880 · dhakshayani@iiitkottayam.ac.in
- Assistant warden: **Dr Anu Maria Sebastian** · 0482-2202228, 8089706065 · anumaria@iiitkottayam.ac.in
- Assistant warden: **Dr Gayathri GR** · 0482-2202184, 8547344787 · gayathri@iiitkottayam.ac.in
- Assistant warden: **Dr Jeena Thomas** · 0482-2202278, 9495662514 · jeenathomas@iiitkottayam.ac.in
- Standby warden: **Dr Asha Sebastian** · 0482-2202248, 9495393573 · asha@iiitkottayam.ac.in

*Source: Wardens Team, July 2026*

### Who are the wardens for Anamudi hostel?
`structured` · `hostel_wardens` · 117 ms · composer
*Expected:* wardens

**Anamudi Hostel (Girls)**
- Warden: **Dr. Kanchan Lata Kashyap** · 0482-2202272, 9826733258 · kanchanlata@iiitkottayam.ac.in
- Assistant warden: **Dr Suriyapriya** · 0482-2202254, 8610135747 · suriyapriya@iiitkottayam.ac.in
- Assistant warden: **Dr Dakshayani** · 0482-2202275, 9578359880 · dhakshayani@iiitkottayam.ac.in
- Assistant warden: **Dr Anu Maria Sebastian** · 0482-2202228, 8089706065 · anumaria@iiitkottayam.ac.in
- Assistant warden: **Dr Gayathri GR** · 0482-2202184, 8547344787 · gayathri@iiitkottayam.ac.in
- Assistant warden: **Dr Jeena Thomas** · 0482-2202278, 9495662514 · jeenathomas@iiitkottayam.ac.in
- Standby warden: **Dr Asha Sebastian** · 0482-2202248, 9495393573 · asha@iiitkottayam.ac.in

*Source: Wardens Team, July 2026*

### How do I contact my hostel warden?
`structured` · `hostel_wardens` · 114 ms · composer
*Expected:* warden contacts (asks which hostel if unknown)

Which hostel are you in? Here are the wardens for each hall:

- **Anamudi Hostel (Girls)** — Dr. Kanchan Lata Kashyap · 0482-2202272, 9826733258 · kanchanlata@iiitkottayam.ac.in
- **Kalapurackal Apartment (Boys)** — Dr Jayakrushna Sahoo · 0482-2202164, 7872456553 · jsahoo@iiitkottayam.ac.in
- **Anna Residency (Boys)** — Dr Susheel Kumar Joshi · 0482-2202185, 9540766915 · joshi@iiitkottayam.ac.in
- **Maryland Panackal Residency(boys)** — Dr Susheel Kumar Joshi · 0482-2202185, 9540766915 · joshi@iiitkottayam.ac.in
- **Court Complex (Boys)** — Dr Susheel Kumar Joshi · 0482-2202185, 9540766915 · joshi@iiitkottayam.ac.in
- **MJ Apartment (Boys)** — Dr Sivaiah Bellamkonda · 0482-2202170, 8142274581 · sivaiah@iiitkottayam.ac.in
- **Sunshine Apartment (Boys)** — Dr Jayakrushna Sahoo · 0482-2202164, 7872456553 · jsahoo@iiitkottayam.ac.in
- **KTM Building (Boys)** — Dr Susheel Kumar Joshi · 0482-2202185, 9540766915 · joshi@iiitkottayam.ac.in
- **Sahyadri Hostel (Girls)** — Dr. Kanchan Lata Kashyap · 0482-2202272, 9826733258 · kanchanlata@iiitkottayam.ac.in
- **Manimala Hostel (Boys)** — Dr Sivaiah Bellamkonda · 0482-2202170, 8142274581 · sivaiah@iiitkottayam.ac.in
- **Meenachil Hostel (Boys)** — Dr Ananth · 0482-2202176, 9443318734 · ananth@iiitkottayam.ac.in
- **Chitar Hostel (Boys)** — Dr Ananth · 0482-2202176, 9443318734 · ananth@iiitkottayam.ac.in
- **Agasthya Apartment (Boys)** — Dr Santos Kumar A · 0482-2202177, 8349529678, 8821833569 · santos@iiitkottayam.ac.in
- **Coptyre Arcade (Boys)** — Dr Jayakrushna Sahoo · 0482-2202164, 7872456553 · jsahoo@iiitkottayam.ac.in
- **Nila Hostel (Boys)** — Dr Santos Kumar A · 0482-2202177, 8349529678, 8821833569 · santos@iiitkottayam.ac.in
- **Kalapurackal Hostel (Boys)** — Dr Jayakrushna Sahoo · 0482-2202164, 7872456553 · jsahoo@iiitkottayam.ac.in

Institute-wide:

- Associate Dean (Hostel Affairs & Student Events): **Dr. Bakkyaraj T** · 0482-2202160 · bakkyaraj@iiitkottayam.ac.in
- Chief Warden: **Dr Victer Paul** · 0482-2202165, 9944913170 · victerpaul@iiitkottayam.ac.in
- Hostel Manager: **Padma Kumar TV** · 0482-2202148, Mobile 6295662931 · hostel_manager@iiitkottayam.ac.in
- Security Officer: **Aravindan M** · 0482-2202110, Mobile 7012897764 · so@iiitkottayam.ac.in

Ask me about a specific hostel (e.g. "wardens of Sahyadri hostel") for its assistant wardens too.

*Source: Wardens Team, July 2026*

## 9. Anti-ragging

### What are the anti-ragging rules?
`semantic` · `none` · 724 ms · composer
*Expected:* summary from UGC regulations / memo

Here are the key anti-ragging rules:

**What counts as ragging** — What constitutes Ragging.- Ragging constitutes one or more of any of the following acts: a. any coriduct by any student or students whether by words spoken or written or by an ‘act which has the effect of teasing, treating or handling with rudeness a fresher or any other student; indulging in rowdy or indisciplined activities by any student or students…

**Punishments** — b) The Anti-Ragging Conimittee may, depending on the nature and gravity of the rquilt established by the Anti-Raggirig Squad, award, to those found guilty, one or “nore of the following punishments, namely; j, Suspension from attendirig classes and academic privileges. 7. Withholding/ withdrawing scholarship/ fellowship and other benefits. ii.

**Getting help** — Students in distress due to ragging related incidents can call the National Anti-Ragging Helpline 1800-180-5522 (24x7 Toll Free) or e-mail the Anti-Ragging Helpline at helpline@antiragging.in.

Ask me about any one of these for the full rule.

*Source: UGC Anti-Ragging Regulations (2009), p. 32; UGC Anti-Ragging Regulations (2009), p. 49; UGC Anti-Ragging Circular Letter, p. 1*

### What counts as ragging?
`semantic` · `none` · 353 ms · composer
*Expected:* definition

From the **UGC Anti-Ragging Regulations (2009)**:

> What constitutes Ragging.- Ragging constitutes one or more of any of the following acts: a. any coriduct by any student or students whether by words spoken or written or by an ‘act which has the effect of teasing, treating or handling with rudeness a fresher or any other student; indulging in rowdy or indisciplined activities by any student or students which causes or is likely to cause: annoyance, hardship, physical or psychological harm or to raise fear or apprehension thereof in any fresher or any other student; asking any student to do any act which such student wii not in the ordinary course do and which has, the effect of causing or generating a sense of sharne, or torment or embarrassment so as to adversely affect the physique or psyche of such fresher or any other student; any act by a senior student that prevents, disrupts or disturbs the regular academic activity of any other…

*Source: UGC Anti-Ragging Regulations (2009), p. 32*

### What is the punishment for ragging?
`semantic` · `none` · 268 ms · composer
*Expected:* punishments

From the **UGC Anti-Ragging Regulations (2009)**:

> b) The Anti-Ragging Conimittee may, depending on the nature and gravity of the rquilt established by the Anti-Raggirig Squad, award, to those found guilty, one or “nore of the following punishments, namely; j, Suspension from attendirig classes and academic privileges. 7. Withholding/ withdrawing scholarship/ fellowship and other benefits. ii. Debarring from appearing In any test/ examination or other evaluation process. iv. Withholding resuits, vy. Debarring from representing the institution in any regional, national or internationa: maet, tournament, youth festival, etc. vi Suspension/ expulsion from the hostel. vil. Cancellation of admission. wii. Rustication from the institution for period ranging from one to four semesters. ix. Expulsion from the institution and consequent debarring from admission to any other institution for a specified period. Provided that where the persons…

*Source: UGC Anti-Ragging Regulations (2009), p. 49*

### How do I report ragging?
`semantic` · `none` · 205 ms · composer
*Expected:* reporting / helpline

From the **UGC Anti-Ragging Circular Letter**:

> Students in distress due to ragging related incidents can call the National Anti-Ragging Helpline 1800-180-5522 (24x7 Toll Free) or e-mail the Anti-Ragging Helpline at helpline@antiragging.in.

*Source: UGC Anti-Ragging Circular Letter, p. 1*

### Who is on the anti-ragging squad?
`semantic` · `none` · 259 ms · composer
*Expected:* members from the office memorandum

From the **Office Memorandum: Anti-Ragging Committee & Squad (Jan 2024)**:

> IIITK/01/09/2024/ 4 Subject: Date : January 31, 2024 OFFICE MEMORANDUM Students Grievance & Anti Ragging Committee and Anti Ragging Squad-reg. The Competent Authority has reconstituted the Students Grievance & Anti Ragging Committee and Anti Ragging Squad as given below with immediate effect. Students Grievance & Anti Ragging Committee Anti-Ragging Squad Dr. Bakkyaraj T Dr. Panchami V Dr. Jayakrushna Sahoo Dr. Rubell Marion Lincy G Dr. Amit Kumar Koy Dr. Riyasudheen T kK Dr. Susheel Kumar Joshi Dr. Vengadeswaran Dr. AnanthA Mrs. Sumangali Student Representative, (B.Tech. & Ph.D all batches) Dr.

*Source: Office Memorandum: Anti-Ragging Committee & Squad (Jan 2024), p. 1*

## 10. Procedures

### How do I request transcript verification?
`semantic` · `none` · 270 ms · composer
*Expected:* steps

From the **Transcript Verification Procedure**:

> The procedure for obtaining PG/UG transcripts is detailed below: - Request may be submitted to: - Officer-In-Charge Academic Office, Indian Institute of Information Technology, Kottayam (IIITK), Valavoor P.O., Pin-686 635, Kottayam, Kerala. The processing of requests may require a maximum of 7 working days. A fee of Rs. 750/- to be remitted for obtaining transcript and payment receipt/details must be attached along with the request. The fee can be paid through the Online SBI Collect Portal under the title “Fee for Document Verification”.

*Source: Transcript Verification Procedure, p. 1*

### What is the transcript verification fee?
`semantic` · `none` · 198 ms · composer
*Expected:* fee from the procedure

From the **Transcript Verification Procedure**:

> The procedure for obtaining PG/UG transcripts is detailed below: - Request may be submitted to: - Officer-In-Charge Academic Office, Indian Institute of Information Technology, Kottayam (IIITK), Valavoor P.O., Pin-686 635, Kottayam, Kerala. The processing of requests may require a maximum of 7 working days. A fee of Rs. 750/- to be remitted for obtaining transcript and payment receipt/details must be attached along with the request. The fee can be paid through the Online SBI Collect Portal under the title “Fee for Document Verification”.

*Source: Transcript Verification Procedure, p. 1*

### How does educational certificate verification work?
`semantic` · `none` · 201 ms · composer
*Expected:* steps

From the **Educational Certificate Verification Procedure**:

> The request must include copies of the following documents: o Degree Certificate o Consolidated Grade Card o Applicant details including address, contact numbers and email addresses o In the case of an agent requesting for verification, an authorization letter signed by the student
>
> In cases where the certificate verification with Institute seal and signature of the concerned authority is required, the request must be submitted as hard copies to the following address: Officer-In-Charge Academic Office Indian Institute of Information Technology Kottayam (IIITK) Valavoor P.O. 686 635, Kottayam, Kerala The hard copy request must contain copies of the following .  Copy of Degree Certificate  Copy of Consolidated Grade Card  In the case of an agent requesting for verification, an authorization letter signed by the student A fee of Rs. 750/- to be remitted for verification and payment…

*Source: Educational Certificate Verification Procedure, p. 1*

## 11. Announcements

### Are there any current announcements?
`structured` · `announcements` · 130 ms · composer
*Expected:* current approved announcements or "none right now"

There are no current announcements right now. New ones show up here once an admin approves them.

### Any new notices?
`structured` · `announcements` · 115 ms · composer
*Expected:* same

There are no current announcements right now. New ones show up here once an admin approves them.

### What's the latest news on campus?
`structured` · `announcements` · 130 ms · composer
*Expected:* same

There are no current announcements right now. New ones show up here once an admin approves them.

## 12. About me

### What semester am I in?
`structured` · `my_profile` · 58 ms · composer
*Expected:* 3

You're in **semester 3**.

*Source: your profile*

### Which section am I in?
`structured` · `my_profile` · 56 ms · composer
*Expected:* I

You're in section **I**.

*Source: your profile*

### What is my department?
`structured` · `my_profile` · 58 ms · composer
*Expected:* CSE

Your department is **Computer Science and Engineering**.

*Source: your profile*

### Which regulations apply to me?
`structured` · `my_profile` · 57 ms · composer
*Expected:* UG Regulations 2021-25 batch

The **UG Regulations (2021-25 batch)** apply to you.

*Source: your profile*

## 13. Follow-up conversations

### Tell me about ICS 211
`structured` · `course_info` · 286 ms · composer

**Design and Analysis of Algorithms** (ICS 211) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 3-1-0).

Taught by Dr. Priyadharshini S, Dr. Jisha Mariyam John, Dr. Manu Madhavan and Dr. Nandini J. Warrier.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 2*

### ↳ Who teaches it?
`structured` · `faculty_for_course` · 231 ms · composer · resolved as “Who teaches ICS 211?”

**Design and Analysis of Algorithms** (ICS 211) is taught by Dr. Priyadharshini S, Dr. Jisha Mariyam John, Dr. Manu Madhavan and Dr. Nandini J. Warrier. Different sections may have different teachers.

- Dr.Priyadharshini S — priyadharshini@iiitkottayam.ac.in
- Dr. Jisha Mariyam John — jishamj@iiitkottayam.ac.in
- Dr. Manu Madhavan — manum@iiitkottayam.ac.in
- Dr. Nandini J. Warrier — nandinijw@iiitkottayam.ac.in

*Source: your live timetable; faculty directory*

### ↳ What credits does it have?
`structured` · `course_info` · 300 ms · composer · resolved as “What credits does ICS 211 have?”

**Design and Analysis of Algorithms** (ICS 211) is a semester 3 B.Tech course. It carries **4 credits** (lecture-tutorial-practical: 3-1-0).

Taught by Dr. Priyadharshini S, Dr. Jisha Mariyam John, Dr. Manu Madhavan and Dr. Nandini J. Warrier.

A syllabus summary isn't in ORION yet — the full syllabus is in your programme's curriculum document.

*Source: course catalog; B.Tech CSE Curriculum (2021-25 batch), p. 2*

### What is my next class?
`structured` · `next_class` · 111 ms · composer

Your next class is **IT Workshop III (ICS 214)** — tomorrow (Wednesday), 10:00–10:55 AM — Dr. Deepak Jose · lab. You have no more classes today.

*Source: your live timetable*

### ↳ Who teaches it?
`structured` · `faculty_for_course` · 232 ms · composer · resolved as “Who teaches ICS 214?”

**IT Workshop III** (ICS 214) is taught by Dr. Deepak Jose, Dr. P. Victer Paul, Dr. R Tharaniya Sairaj and Dr. Alkha Mohan. Different sections may have different teachers.

- Dr. Deepak Jose — deepakjose@iiitkottayam.ac.in
- Dr. P. Victer Paul — victerpaul@iiitkottayam.ac.in
- Dr. R Tharaniya Sairaj — sairaj@iiitkottayam.ac.in
- Dr. Alkha Mohan — alkha@iiitkottayam.ac.in

*Source: your live timetable; faculty directory*

### What is Dr. Manu Madhavan's email?
`structured` · `faculty_lookup` · 125 ms · composer

Dr. Manu Madhavan's email is **manum@iiitkottayam.ac.in**.

*Source: faculty directory*

### ↳ What does he research?
`structured` · `faculty_lookup` · 118 ms · composer · resolved as “What does Dr. Manu Madhavan research?”

Dr. Manu Madhavan's research interests: Natural Language Processing; Bioinformatics; Machine Learning; Computational Linguistics; Deep Learning, Graph Neural Networks.

*Source: faculty directory*

### What's for lunch today?
`structured` · `mess_today` · 121 ms · composer

Lunch on **Tuesday, 22 September** (today): Tawa Pulao, Roti, ChettinadChicken, Chilli Paneer, Vegetable Raita, Salad Drink:Lemon juice/Litchi.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August). It may change.

*Source: mess menu*

### ↳ And dinner?
`structured` · `mess_today` · 115 ms · composer · resolved as “What's for dinner today?”

Dinner on **Tuesday, 22 September** (today): Rice, Roti, Chole curry, Onion Dal Tadka, Carrot Beans Thoran, Rasam, Chips Salad, Curd.

Note: a menu hasn't been published for these dates yet, so this is the regular weekly menu from the most recent week on file (25 August). It may change.

*Source: mess menu*

### What is the attendance requirement?
`semantic` · `none` · 193 ms · composer

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.5.2 The incomplete grade I is a transitional grade which will be given to the students who miss the end semester examinations under exceptional circumstances (eg. serious medical reasons) as determined by the course instructor/faculty advisor/Head of the department and approved by the Dean(Academics). Make up examination will be given to the students provided they meet the attendance requirements as per

*Source: UG Regulations (2021-25 batch), R.5.2, p. 7*

### ↳ What if I don't meet it?
`semantic` · `none` · 220 ms · composer · resolved as “What if I don't meet it? (What is the attendance requirement)”

Under the **UG Regulations (2021-25 batch)**, which apply to you:

> R.5.2 The incomplete grade I is a transitional grade which will be given to the students who miss the end semester examinations under exceptional circumstances (eg. serious medical reasons) as determined by the course instructor/faculty advisor/Head of the department and approved by the Dean(Academics). Make up examination will be given to the students provided they meet the attendance requirements as per
>
> R.5.3 Students having an attendance percentage between 65% to 80%, with valid/genuine reasons may be permitted to continue the course by paying a nominal penalty amount as decided by the competent authority. Students having an attendance percentage less than 65 will be awarded L grade.

*Source: UG Regulations (2021-25 batch), R.5.2, p. 7*

## 14. Out of scope — must not invent anything

### What are my exam grades this semester?
`unsupported` · `out_of_scope` · 56 ms · composer
*Expected:* ORION doesn't hold grades; where to check

I can't see grades, marks or CGPA — ORION doesn't store personal academic records. Your results are on the institute's academic portal, or ask your faculty advisor. I can explain how CGPA is calculated or tell you when results are published.

### What is my CGPA?
`unsupported` · `out_of_scope` · 55 ms · composer
*Expected:* same

I can't see grades, marks or CGPA — ORION doesn't store personal academic records. Your results are on the institute's academic portal, or ask your faculty advisor. I can explain how CGPA is calculated or tell you when results are published.

### What is my attendance percentage?
`unsupported` · `out_of_scope` · 53 ms · composer
*Expected:* not held; ask faculty / portal

ORION doesn't track your attendance — your course faculty maintain it, and you can check it with them. I can tell you the attendance rules if that helps ("What is the attendance requirement?").

### How do I pay my fees?
`unsupported` · `out_of_scope` · 55 ms · composer
*Expected:* fee payment not in ORION; fee deadlines from calendar if relevant

ORION doesn't handle fee payments or balances — use the institute's official payment channels or the Accounts section. I can tell you fee payment deadlines from the academic calendar.

### What is the weather today?
`unsupported` · `out_of_scope` · 55 ms · composer
*Expected:* out of scope

I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations.

### What is the capital of France?
`unsupported` · `out_of_scope` · 54 ms · composer
*Expected:* out of scope, campus assistant

I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations.

### Write a Python program to sort a list
`unsupported` · `out_of_scope` · 56 ms · composer
*Expected:* out of scope

I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations.

### What is the meaning of life?
`unsupported` · `out_of_scope` · 60 ms · composer
*Expected:* out of scope, friendly

I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations.

### asdkfj qwer nonsense query
`unsupported` · `none` · 56 ms · composer · ⚠️ review
*Expected:* didn't understand + examples

I'm not sure what you mean. You can ask me things like:

- What is my next class?
- What's for lunch today?
- When do the end semester exams start?
- What is the attendance requirement?
- Who is the warden of Sahyadri hostel?

### Who will win the IPL this year?
`unsupported` · `out_of_scope` · 55 ms · composer
*Expected:* out of scope

I'm ORION, IIIT Kottayam's campus assistant, so I stick to campus information — your classes, faculty, the mess menu, exams and deadlines, hostel rules and academic regulations.

