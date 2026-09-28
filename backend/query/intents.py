"""Semantic intent classification: "what is this question actually asking?"

The regex router (router.py) is precise but literal — it knows "faculty",
not "teachers", "lecturers", "teaching staff" or "academic employees"; it
knows "mess menu", not "what's cooking" or "what is the dining hall
serving". Every such paraphrase used to fall through to document search and
come back quoting an unrelated regulation (AI-Tests/, 2026-09-25).

This module answers the routing question by *meaning*: each question is
turned into concept tokens (lexicon.concept_tokens: teachers/professors/
lecturers -> @faculty, serving/dishes/dining -> @food, ...) plus its content
words, and compared with a bank of labelled example questions using TF-IDF
cosine similarity. The nearest examples vote for an intent.

Deliberately a local model, not an LLM or embedding call: it costs nothing,
has no quota, answers in about a millisecond, is deterministic (so it can be
tested), and cannot invent facts — it only decides *where* to look. Adding a
new phrasing is adding one example sentence below.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from . import lexicon

# label -> example questions. Labels map to QueryPlans in router._plan_for_label.
EXAMPLES: dict[str, list[str]] = {
    "faculty_directory": [
        "Who are the faculty here?", "Who are the teachers here?", "Who are the professors here?",
        "Which lecturers work here?", "Who are the academic staff?", "Who are the teaching staff?",
        "Who are the academic employees?", "Who are the faculty people?", "Show me members of the teaching team.",
        "List all the faculty members", "Give me the faculty list", "Show the faculty directory",
        "How many faculty are there?", "How many professors does the institute have?",
        "Which faculty members are assistant professors?", "Who works as an assistant professor?",
        "How many assistant professors are there?", "Who are the adjunct professors?",
        "Are adjunct faculty included in the faculty list?", "List the adjunct faculty",
        "Which people are lab faculty?", "Who are the lab teaching staff?", "Who are the lab instructors?",
        "Who holds an associate professor-type role?", "Are there any associate professors?",
        "Who are the visiting faculty?", "Who are the administrative faculty?",
        "Which faculty members also hold administrative positions?",
        "Who has both an academic and an administrative role?", "Who are the people in academic administration?",
        "Which faculty have administrative duties?", "Who teaches at IIIT Kottayam?",
        "Which teachers are in the CSE department?", "Who are the faculty in ECE?",
        "List the professors of the electronics department", "Who teaches here?", "Staff list",
        "Which professors work here?", "Who are the profs in this college?",
    ],
    "faculty_role": [
        "Who is the HOD of CSE?", "Who heads ECE?", "Who is heading Computer Science and Engineering?",
        "Who are the HODs in the institute?", "List all heads of department", "Who is the head of electronics?",
        "Who is the HOD of Electrical Engineering?", "Who leads the cyber security department?",
        "Who is in charge of the humanities department?", "Who is the registrar?", "Who is the director?",
        "Who is the dean of academics?", "Who handles student welfare?", "Who handles academic affairs?",
        "Who is in charge of hostel affairs?", "Who looks after alumni relations?",
        "Who is responsible for placements and career development?", "Who manages industrial relations?",
        "Who is the associate dean?", "Who is the medical officer?", "Is there a counsellor on campus?",
        "Who is the chief vigilance officer?", "Who is the nodal officer for the SC/ST cell?",
        "Who is the physical education instructor?", "Is there a doctor on campus?",
        "Who takes care of student welfare?", "Who is the dean of students?",
    ],
    "faculty_lookup": [
        "Tell me about Dr. Manu Madhavan", "What is Dr. Manu Madhavan's email?", "Where is Dr. Anish's cabin?",
        "Who is Prof. Jobin Jose?", "Search faculty named Christina", "Find the professor called John",
        "What position does Dr. Jobin Jose hold?", "What is Dr. Christina Joseph's research area?",
        "Contact details of Dr. Amit Kumar Roy", "Phone number of Dr. Ananth", "Where can I find Dr. Kala?",
        "Where does Amit Kumar Roy fit in the faculty list?", "What is the designation of Dr. Leena Mary?",
        "Is there a faculty member named Christy?", "Look up Dr. Sara Renjit",
    ],
    "faculty_research": [
        "Which faculty work on machine learning?", "Who researches natural language processing?",
        "Recommend a faculty member for computer vision", "Who specialises in VLSI design?",
        "Which professors work on cryptography?", "Is anyone researching IoT?", "Who is an expert in data science?",
        "Which faculty work in wireless communication?", "Suggest a guide for deep learning research",
        "Who works on underwater sensor networks?", "Faculty working in quantum computing",
        "Who researches blockchain?", "Professors specialising in signal processing",
        "Which faculty work on NLP and when can I meet them?",
    ],
    "faculty_for_course": [
        "Who teaches ICS 213?", "Who is teaching database management systems?", "Who takes the algorithms class?",
        "Faculty for theory of computation", "Instructor for data structures", "Who handles the ICS 211 course?",
        "Who teaches IT Workshop III?", "Which professor takes our DBMS lectures?",
        "Who takes the theory of computation course?", "Who is the instructor for the probability course?",
    ],
    "mess": [
        "What is on the mess menu today?", "What's for lunch?", "What's cooking today?",
        "What are they serving today?", "What dishes are planned?", "What is the dining hall serving?",
        "What are today's meal choices?", "What are we having Sunday?", "Is chicken there today?",
        "Is there paneer for dinner?", "What's for breakfast tomorrow?", "Mess menu this week",
        "What food is there today?", "What can I eat tonight?", "What's the dinner menu?",
        "Is there any non veg today?", "Is there biryani on Friday?", "What is served in the mess?",
        "What are the snacks today?", "What's for dinner on Monday?", "Weekly mess menu",
        "What is being served for lunch?", "Is there fish today?", "Any dessert tonight?",
    ],
    "calendar": [
        "When do classes end?", "When does the semester end?", "When are the end semester exams?",
        "When is the sports meet?", "What are the upcoming events?", "Which events are in the future?",
        "What events are coming up?", "What's on the academic calendar?", "What happened on September 24?",
        "What happens on January 4, 2027?", "What is the next event after the Sports Meet?",
        "How many days before exams start do classes end?",
        "How many days are there between class end and end-sem exam start?", "Show all exams",
        "List the exam dates", "When is the mid semester exam?", "When will results be published?",
        "Last date for course drop", "When is the fee payment deadline?", "When does registration start?",
        "Important dates this month", "What's happening today?", "Are there any events today?",
        "Which events are already over?", "What events happened last month?", "Is there a holiday this week?",
        "When is the project final review?", "What is scheduled on October 26?", "Events in November",
        "What's next on the calendar?", "How many days until the end semester exams?",
        "When is the last instructional day?", "Course drop deadline", "When do classes start next semester?",
    ],
    "timetable": [
        "What is my next class?", "What classes do I have today?", "What is my timetable this week?",
        "Do I have a lab tomorrow?", "What class do I have at 3 pm?", "What's my first class tomorrow?",
        "When is my DBMS class?", "What lectures do I have on Monday?", "What's next?",
        "Do I have classes on Saturday?", "What's my schedule today?", "Which class is now?",
        "What lecture do I have after lunch?",
    ],
    "free_time": [
        "When am I free today?", "Do I have a free period tomorrow?", "Is there any free lecture?",
        "Free slots on Monday", "Gaps between my classes today", "Am I free after 2 pm?",
        "Do I have any free hours tomorrow?",
    ],
    "documents": [
        "What is the attendance requirement?", "What are the rules for course withdrawal?",
        "How is CGPA calculated?", "What are the hostel curfew rules?", "How does the outpass process work?",
        "What are the anti-ragging rules?", "How do I report ragging?", "What is the transcript verification fee?",
        "What are the examination hall rules?", "What are the disciplinary rules?",
        "What happens if I fail a course?", "Can I take a summer term?", "Is cooking allowed in hostel rooms?",
        "Can visitors stay in the hostel?", "What are the project or BTP rules?", "What are the make-up exam rules?",
        "What is the grading system?", "How many credits are required to graduate?",
        "What does the conduct and discipline section say?", "What is the punishment for malpractice in exams?",
        "What do the academic regulations say about the end of the semester?", "What is the library timing?",
        "Can I drop a course?", "What is condonation of attendance?", "Rules for leaving the campus at night",
        "What is the minimum CGPA for a dual degree?", "What are the library rules?",
        "How are grade points calculated?", "What is the attendance rule?", "Rules for backlogs",
        "What happens if my attendance is low?", "Can I withdraw from a course?",
    ],
    "announcements": [
        "Any announcements?", "What are the latest notices?", "What's new on campus?", "Show the notice board",
        "Are there any circulars?", "Any updates today?",
    ],
    "wardens": [
        "Who is the warden of Sahyadri hostel?", "Hostel warden contact number", "Who is the chief warden?",
        "Who are the assistant wardens?", "Who is the hostel manager?",
    ],
    "profile": [
        "Which semester am I in?", "What is my section?", "Show my profile", "Which regulations apply to me?",
        "What is my department?", "Who am I?", "What batch am I in?", "Which cohort am I?",
    ],
    "my_courses": [
        "What courses am I taking?", "What are my subjects this semester?", "List my courses",
        "Which papers do I have this semester?", "How many courses do I have?", "My enrolled courses",
    ],
    "meta_source": [
        "Which source did you use?", "Where did you get that?", "What's your source?", "Cite the source",
        "Where is this from?", "Which document says that?", "What is the reference for that answer?",
    ],
    "meta_history": [
        "What was the first question I asked?", "What did I ask before?", "What was my last question?",
        "Repeat my previous question", "What did I say earlier?",
    ],
    "out_of_scope": [
        "What is my CGPA?", "What's the weather today?", "Write me a poem", "Who won the cricket match?",
        "Tell me a joke", "What is the capital of France?", "How do I pay my fees?", "What are my marks?",
        "What is my attendance percentage?", "Show my grades", "Book a movie ticket",
    ],
}

# Weights: a concept token says far more about intent than an ordinary word.
_CONCEPT_WEIGHT = 2.0
_QWORD_WEIGHT = 1.2
_WORD_WEIGHT = 1.0
_BIGRAM_WEIGHT = 0.6


def features(text: str) -> Counter:
    toks = lexicon.concept_tokens(text)
    feats: Counter = Counter()
    for t in toks:
        w = _CONCEPT_WEIGHT if t.startswith("@") else _QWORD_WEIGHT if t.startswith("?") else _WORD_WEIGHT
        feats[t] += w
    for a, b in zip(toks, toks[1:]):
        feats[f"{a}_{b}"] += _BIGRAM_WEIGHT
    return feats


@dataclass(frozen=True)
class Prediction:
    label: str
    score: float  # cosine similarity to the closest examples, 0..1
    margin: float  # lead over the best other label
    runner_up: str

    @property
    def confident(self) -> bool:
        return self.score >= 0.45 and self.margin >= 0.08


class IntentModel:
    def __init__(self, examples: dict[str, list[str]]):
        docs = [(label, features(q)) for label, qs in examples.items() for q in qs]
        df: Counter = Counter()
        for _, f in docs:
            df.update(f.keys())
        n = len(docs)
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self._docs = [(label, self._vector(f)) for label, f in docs]

    def _vector(self, feats: Counter) -> dict[str, float]:
        vec = {t: w * self._idf.get(t, math.log(1 + len(self._idf)) + 1.0) for t, w in feats.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def rank(self, text: str) -> list[tuple[str, float]]:
        q = self._vector(features(text))
        per_label: dict[str, list[float]] = {}
        for label, vec in self._docs:
            sim = sum(v * vec.get(t, 0.0) for t, v in q.items())
            per_label.setdefault(label, []).append(sim)
        scored = []
        for label, sims in per_label.items():
            top = sorted(sims, reverse=True)
            # Best match, lightly supported by the second best: one lucky
            # example shouldn't outvote a label several examples agree on.
            scored.append((label, top[0] * 0.8 + (top[1] if len(top) > 1 else 0.0) * 0.2))
        scored.sort(key=lambda x: -x[1])
        return scored

    def predict(self, text: str) -> Prediction:
        ranked = self.rank(text)
        (label, score), (runner, second) = ranked[0], ranked[1]
        return Prediction(label=label, score=round(score, 3), margin=round(score - second, 3), runner_up=runner)


@lru_cache(maxsize=1)
def model() -> IntentModel:
    return IntentModel(EXAMPLES)


def predict(text: str) -> Prediction:
    return model().predict(text)
