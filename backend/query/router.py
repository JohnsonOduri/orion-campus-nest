"""Deterministic query classification (README §8, AGENTS.md §4).

2026-09-28: understanding happens in three passes, all local and
deterministic (no LLM, no quota):

1. lexicon.correct_spelling — "tommorow"/"teching"/"facluty" are fixed
   before anything reads the question (names are left to fuzzy entity
   linking against the directory itself);
2. the regex rules below — precise, and the only place slots (meal, day,
   role, course code, name, date) are extracted;
3. intents.predict — a semantic nearest-neighbour classifier over concept
   tokens, consulted when no rule recognised the question, so a paraphrase
   ("who are the teachers here?", "what's the dining hall serving?") reaches
   the right data instead of falling through to document search.

No LLM call here by design — this stage is independently testable and the
router must "not blindly send every question to vector search" (AGENTS.md
§4). Rule-based intent classification is cheap, auditable, and — unlike an
LLM classifier — never costs a token or a quota unit. An LLM-backed
classifier can be added later as a fallback for genuinely ambiguous queries
without changing this module's contract (it still returns a QueryPlan).
"""

from __future__ import annotations

import dataclasses
import random
import re
from datetime import datetime

from datetime import date

from . import intents, lexicon, tempo
from .types import QueryPlan, RouteType, StructuredIntent

# ------------------------------------------------------------- structured

_NEXT_CLASS_RE = re.compile(
    r"\b(next class|where.*(is|s)\s+my\s+next\s+class|what.*(class|lecture).*(now|currently|right now))\b",
    re.IGNORECASE,
)
_TODAY_TIMETABLE_RE = re.compile(
    r"\btoday\b.*\b(class|classes|timetable|schedule)\b|\b(class|classes|timetable|schedule)\b.*\btoday\b",
    re.IGNORECASE,
)
_WEEK_WORD_RE = re.compile(r"\b(this week|weekly|week.s)\b", re.IGNORECASE)
_TIMETABLE_WORD_RE = re.compile(r"\b(class|classes|timetable|schedule)\b", re.IGNORECASE)
_WEEKDAY_RE = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE)
_WHO_TEACHES_RE = re.compile(
    r"\bwho\s+(is\s+|'s\s+)?(teach(es|ing)?|tak(es|ing)|handl(es|ing))\b|\bfaculty\s+(for|teaching)\b|"
    r"\binstructor\s+for\b", re.IGNORECASE
)
_COURSE_CODE_RE = re.compile(r"\b([IUE][A-Z]{2}\s?\d{3}|[A-Z]{2,4}\s?\d{3})\b")
_COURSE_INFO_WORD_RE = re.compile(
    r"\b(about|info|information|credits?|syllabus|prerequisites?)\b", re.IGNORECASE
)
_COURSE_ABOUT_LEAD_RE = re.compile(r"^\s*(what\s+is|tell\s+me\s+about|about)\s+", re.IGNORECASE)
# "Tell me about Dr. X" / "Who is Dr. X" — the title is REQUIRED, not
# optional: without it, "tell me about the campus regulations" would be
# swallowed as if "the campus regulations" were a faculty name.
_FACULTY_ABOUT_RE = re.compile(
    r"\b(?:tell\s+me\s+about|who\s+is)\s+(dr\.?|prof\.?|professor|mr\.?|ms\.?|mrs\.?)\s+"
    r"([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)
# "<Name>'s email/office/office hours" — the capitalized-words structure
# itself (a proper-noun heuristic) is distinctive enough that a title isn't
# required here; case-sensitive on purpose so a lowercase sentence doesn't
# accidentally look like a name. The name class deliberately excludes "."
# (no initials support) — with "." allowed, "Dr." itself also matches the
# name pattern, and the optional title group loses the race to the name
# group swallowing "Dr." whole; excluding "." forces "Dr" (no trailing
# period consumed) to fail the immediately-following-'s check, so the
# engine backtracks into the title branch instead, correctly excluding it.
# "office"/"office hours"/"office location" plus the common institute
# synonyms "cabin"/"room" — found live: "Where is cabin of Dr. X?" fell
# through everything since "cabin" wasn't recognized as meaning "office".
_FACULTY_ATTR_WORDS = (r"email|e-mail|office\s+hours|office\s+location|office|cabin|room|"
                       r"research(?:\s+(?:area|areas|interests?|field|topics?|work))?|position|designation|role|"
                       r"department|phone(?:\s+number)?|contact(?:\s+details)?|details|profile|expertise|specialization")
_FACULTY_POSSESSIVE_RE = re.compile(
    r"\b(?:(?i:dr|prof|professor|mr|ms|mrs)\.?\s+)?"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})'s\s+"
    rf"(?i:{_FACULTY_ATTR_WORDS})\b"
)
# The other common word order: "where is the cabin of Dr. X", "what is
# the email of Dr. X" — attribute word first, name after "of"/"for",
# anchored to end-of-string (mirrors _FACULTY_ABOUT_RE's approach) so the
# name capture can't run past a trailing "?" or swallow a wrong prefix.
_FACULTY_ATTR_OF_RE = re.compile(
    rf"\b(?:{_FACULTY_ATTR_WORDS})\b.*?\b(?:of|for)\s+"
    r"(dr\.?|prof\.?|professor|mr\.?|ms\.?|mrs\.?)?\s*([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)
# The third word order, with no possessive apostrophe and no "of": "Where
# is Dr. Anisth S cabin?", "Dr Kala S email". A title is REQUIRED here —
# without one, "where is my class room" would look like a name followed by
# an attribute word. The name capture is non-greedy and must be followed
# immediately by the attribute word, so it can't run away across a
# sentence; it accepts bare initials ("Anisth S", "Kala S"), which the
# possessive pattern's [A-Z][a-z]+ name class cannot match at all — the
# reason "Where is Dr. Anisth S cabin?" reached document search and came
# back with an anti-ragging committee memo.
# The optional possessive is spelled `(?:'s|')?`, not `'?s?` — under
# IGNORECASE the latter's `s?` happily eats the trailing initial of a name
# like "Anisth S", capturing "Anisth" and losing the initial.
_FACULTY_ATTR_AFTER_NAME_RE = re.compile(
    r"\b(?:dr|prof|professor|mr|ms|mrs)\.?\s+"
    r"([A-Za-z][A-Za-z.\s]{1,40}?)(?:'s|')?\s+"
    rf"(?:{_FACULTY_ATTR_WORDS})\b",
    re.IGNORECASE,
)
# "Where is Dr X?" with no attribute word at all — asking where to find a
# person is asking for their office. A title is required (so "where is my
# next class" can't match), and the name runs to the end of the question.
_FACULTY_WHERE_RE = re.compile(
    r"\bwhere\s+(?:is|are|can\s+i\s+find)\s+(?:dr|prof|professor|mr|ms|mrs)\.?\s+"
    r"([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$",
    re.IGNORECASE,
)
_MESS_WORD_RE = re.compile(
    r"\b(mess|canteen|cafeteria|food|menu|breakfast|lunch|dinner|snacks?|dining\s+hall|meal\s+choices|meals?|"
    r"dish(es)?)\b"
    # "what's cooking today" is the mess; "is cooking allowed in the hostel" is a hostel rule.
    r"|\bwhat'?s\s+cooking\b|\bcooking\s+(today|tonight|tomorrow)\b"
    r"|\bwhat\s+(are|r|is)\s+(we|they)\s+(having|eating|serving|getting)\b|\b(they|mess|dining\s+hall|canteen)\s+serv\w*"
    r"|\bwhat\s+(can|do|will|shall)\s+(i|we)\s+eat\b",
    re.IGNORECASE,
)
# A dish asked about by name: "is chicken there today?", "any paneer for dinner?".
_DISH_RE = re.compile(
    r"\b(chicken|paneer|mutton|beef|fish|eggs?|egg\s+curry|biryani|non[\s-]?veg|dessert|sweets?|payasam|"
    r"ice\s*cream|dosa|idli|poori|puri|chapati|pulao|fried\s+rice|noodles|pasta|kheer)\b",
    re.IGNORECASE,
)
_MEAL_RE = re.compile(r"\b(breakfast|lunch|dinner|snacks?)\b", re.IGNORECASE)
_YESTERDAY_RE = re.compile(r"\byesterday\b", re.IGNORECASE)
_TOMORROW_RE = re.compile(r"\btomorrow\b", re.IGNORECASE)
# A specific clock time — "class from 10:30", "class at 3pm" — requires
# either a colon (10:30) or an am/pm suffix, never a bare number, so this
# never matches an unrelated number (a course code digit, a count, etc.).
_TIME_RE = re.compile(
    r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(am|pm)?\b|\b(1[0-2]|0?[1-9])\s*(am|pm)\b",
    re.IGNORECASE,
)

# -------------------------------------------------------------- small talk

# Whole-message only — "hi what is my next class" must still route to a real
# intent below, so these are anchored, not just word-boundary matches.
_GREETING_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|good\s*(morning|afternoon|evening)|yo|sup|greetings)\s*[!.]*\s*$",
    re.IGNORECASE,
)
_THANKS_RE = re.compile(r"^\s*(thanks?|thank\s*you|thx|ty|cheers)\s*[!.]*\s*$", re.IGNORECASE)
_BYE_RE = re.compile(r"^\s*(bye|goodbye|see\s*you|later|cya)\s*[!.]*\s*$", re.IGNORECASE)
# "what can you do", "help", "who are you" — extremely common first
# messages to any chatbot; found live these all fell through to the same
# generic UNSUPPORTED response as a nonsense query.
_CAPABILITIES_RE = re.compile(
    r"^\s*(what\s+can\s+you\s+do\??|help\??|who\s+are\s+you\??|what\s+is\s+orion\??|"
    r"what\s+can\s+you\s+help\s+(?:me\s+)?with\??)\s*$",
    re.IGNORECASE,
)
_HOW_ARE_YOU_RE = re.compile(
    r"^\s*(how\s+are\s+you|how'?s\s+it\s+going|what'?s\s+up|how'?s\s+things)\s*\??\s*$",
    re.IGNORECASE,
)

# Reply variety so repeated small talk doesn't read as 3 hardcoded strings
# (the routing decision itself stays fully deterministic — same input
# always -> same RouteType/StructuredIntent — only the reply text varies).
_THANKS_REPLIES = [
    "You're welcome! Let me know if you need anything else.",
    "Anytime! Happy to help.",
    "No problem at all — ask away if you need anything else.",
]
_BYE_REPLIES = [
    "See you! Come back anytime you need campus info.",
    "Bye! I'm here whenever you need something.",
    "Take care! Come back if you have more questions.",
]
_HOW_ARE_YOU_REPLIES = [
    "Doing well, thanks for asking! What can I help you with?",
    "All good here! What do you need help with today?",
]
_CAPABILITIES_REPLY = (
    "I'm RION, ORION's AI assistant. I can help with: your timetable (today, "
    "a specific day, a specific time, tomorrow/yesterday), the mess menu "
    "(today, this week, a specific meal or day), course info (credits, "
    "syllabus, prerequisites), faculty details (email, office, office hours), "
    "who teaches a course, faculty who work in a research area, and campus "
    "regulations/policies. Just ask in your own words!"
)


def _greeting_reply() -> str:
    """Time-of-day aware rather than one fixed string — a real assistant
    behavior, and still fully deterministic/testable (always one of three
    known variants for a given server clock hour)."""
    hour = datetime.now().hour
    if hour < 12:
        salutation = "Good morning!"
    elif hour < 17:
        salutation = "Good afternoon!"
    else:
        salutation = "Good evening!"
    return f"{salutation} I'm RION — ask me about your timetable, mess menu, courses, faculty, or campus regulations."

# ---------------------------------------------------------------- semantic

# Topics that live in the document corpus (regulations/policies/procedures/
# curriculum), never in a relational table — README §7/§9, AGENTS.md §5.
# Plural forms use an optional trailing "s" (e.g. regulations?) rather than
# a separate alternative — \bregulation\b alone never matches inside
# "regulations" since \b requires a boundary right after "n", and the "s"
# is a word character too, so there's no boundary there. Found live: "Tell
# me about the campus regulations" fell through to UNSUPPORTED.
_SEMANTIC_TOPIC_RE = re.compile(
    r"\b(attendance|regulations?|rules?|polic(?:y|ies)|cgpa|sgpa|grading|grades?|credits?|"
    r"prerequisites?|curriculum|syllabus|hostel|ragging|transcripts?|verification|"
    r"procedures?|condonation|registration requirement|degree requirement|"
    r"summer term|continuation requirement)\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------------ hybrid

# Faculty + a topic + (implicitly or explicitly) wanting to know when/where
# to reach them — README §8 hybrid example, AGENTS.md §5.
_FACULTY_MENTION_RE = re.compile(
    r"\b(faculty|professor|instructor)\b.*\b(work|works|working|research|specializ|"
    r"interest)\w*\b|\bwho\s+(works|is\s+working)\s+(on|in)\b|\brecommend\s+a\s+faculty\b",
    re.IGNORECASE,
)
_MEET_AVAILABILITY_RE = re.compile(
    r"\b(meet|available|availability|office hours|when can i|when.s a good time)\b",
    re.IGNORECASE,
)


# ------------------------------------------------- added 2026-09-22 (AI-task.md)

_COURSE_CODE_ANYCASE_RE = re.compile(r"\b(I[A-Z]{2})\s?(\d{3})\b", re.IGNORECASE)
_GREETING_LOOSE_RE = re.compile(
    r"^\s*(hi+|hello+|hey+|hiya|namaste|good\s*(morning|afternoon|evening))[\s,!.]*"
    r"(there|orion|buddy|friend|all|everyone)?\s*[!.]*\s*$",
    re.IGNORECASE,
)

# Personal records ORION does not hold (CLAUDE.md §3: not an ERP).
_MY_RECORDS_RE = re.compile(
    r"\bmy\b[^?]*\b(grades?|marks|cgpa|sgpa|gpa|scores?|results?|attendance(\s+(percentage|%|status|record))?|"
    r"fee\s*(balance|dues|receipt|status)|backlogs?)\b",
    re.IGNORECASE,
)
_FEE_PAYMENT_RE = re.compile(
    r"\b(how\s+(do|can)\s+i\s+pay|pay(ing)?\s+(my\s+)?(the\s+)?fees?|fee\s+(structure|amount|receipt)|"
    r"how\s+much\s+(is|are)\s+the\s+(tuition|hostel|semester)?\s*fees?)\b",
    re.IGNORECASE,
)
_GENERAL_KNOWLEDGE_RE = re.compile(
    r"\b(weather|temperature\s+(today|outside)|capital\s+of|prime\s+minister|president\s+of|"
    r"ipl|world\s+cup|cricket\s+(match|score)|football\s+match|stock\s+price|bitcoin|share\s+price|"
    r"meaning\s+of\s+life|tell\s+me\s+a\s+joke|joke|movie|song|recipe|"
    r"write\s+(me\s+)?(a|an|the)?\s*(python|java|c\+\+|javascript|program|code|script|essay|poem|story|letter))\b",
    re.IGNORECASE,
)

_PROFILE_RE = re.compile(
    r"\b(what|which)\b[^?]*\b(semester|section|batch|department|branch|cohort|year|programme|program)\b[^?]*"
    r"\b(am\s+i|i\s+am|i'm|im|my)\b|\bwhich\s+regulations?\s+(apply|applies)\s+to\s+me\b|"
    r"\bmy\s+(semester|section|batch|department|branch|cohort|profile|details)\b\s*\??\s*$|\bwho\s+am\s+i\b",
    re.IGNORECASE,
)

_ANNOUNCEMENT_RE = re.compile(
    r"\b(announcements?|notices?|notice\s*board|news|latest\s+updates?|what'?s\s+new|any\s+updates?)\b",
    re.IGNORECASE,
)

_WARDEN_RE = re.compile(
    r"\b(wardens?|chief\s+warden|hostel\s+manager|security\s+officer)\b|"
    r"\bhostel\b[^?]*\b(contact|phone|number|in[\s-]?charge|call)\b"
    r"|\b(in[\s-]?charge|head|responsible)\s+(of|for)\s+(the\s+)?hostels?\b",
    re.IGNORECASE,
)

# Institutional roles held in faculty.designation.
_DEPT_WORDS = (r"cse|ece|eee|csy|computer\s+science(?:\s+(?:and|&)\s+engineering)?|electronics|electrical|"
               r"communication|cyber\s*security|cyber|humanities|mathematics|maths|computational\s+science|department|dept")
# "handles/looks after/in charge of <office>" -> the associate dean for it.
_OFFICE_AREA_RE = re.compile(
    r"\b(students?\s+welfare|academic\s+affairs|academics|hostel\s+affairs|student\s+events|alumni|"
    r"international\s+(affairs|relations)|industrial\s+relations|industry\s+relations|funding|"
    r"continuing\s+education|consultancy|career(\s+development)?|placements?)\b",
    re.IGNORECASE,
)
_HANDLES_RE = re.compile(
    r"\b(handles?|handling|in[\s-]charge\s+of|responsible\s+for|looks?\s+after|takes?\s+care\s+of|manages?|"
    r"oversees?|heads?|leads?|runs?)\b",
    re.IGNORECASE,
)
_ROLE_TERMS: list[tuple[str, str]] = [
    (r"\b(hods?|h\.o\.d|heads?\s+of\s+(the\s+)?(department|dept)s?)\b", "hod"),
    (rf"\b(heads?|heading|headed|leads?|leading|in[\s-]charge\s+of|chairs?|runs?|running|manages?|managing)\b"
     rf"[^?]{{0,30}}\b({_DEPT_WORDS})\b", "hod"),
    (rf"\bhead\s+of\s+(the\s+)?({_DEPT_WORDS})\b", "hod"),
    (r"\bregistrar\b", "registrar"),
    (r"\bdirector\b", "director"),
    (r"\b(associate\s+)?dean\b", "dean"),
    (r"\b(medical\s+officer|doctor|physician|medical\s+help|medical\s+emergency)\b", "medical"),
    (r"\b(staff\s+)?nurse\b", "nurse"),
    (r"\b(psychologist|counsell?or|counsell?ing|mental\s+health)\b", "psychologist"),
    (r"\b(physical\s+education|pe\s+instructor|sports\s+(instructor|teacher|coach))\b", "physical_education"),
    (r"\b(cvo|chief\s+vigilance)\b", "cvo"),
    (r"\b(nodal|liaison|liason)\s+officer|sc/?st\s+cell\b", "nodal"),
]
_ROLE_QUESTION_RE = re.compile(
    r"\b(who|whom|contact|email|phone|number|is\s+there|any|where|name\s+of)\b", re.IGNORECASE
)

# Deliberately excludes bare "end"/"start": "if I miss the END semester exam"
# is a regulation question, not a date question.
_TIMING_WORD_RE = re.compile(
    r"\b(when|what\s+date|which\s+date|date|dates|schedule|scheduled|timetable|how\s+long|until|till|"
    r"deadline|last\s+(date|day)|(start|starts|starting|begin|begins)(?!\s*[-\s]?sem))\b",
    re.IGNORECASE,
)
# "What happens if my attendance is below 80%?" asks about a RULE, not the
# caller's own record.
_HYPOTHETICAL_RE = re.compile(
    r"\b(what\s+happens|what\s+if|if\s+(my|i)|below|less\s+than|short(age)?|minimum|required|requirement)\b",
    re.IGNORECASE,
)
_EXAM_WORD_RE = re.compile(
    r"\b(exams?|examinations?|mid[\s-]?sems?|end[\s-]?sems?|midterms?|finals?|repeat\s+exams?|supplementary)\b",
    re.IGNORECASE,
)
_CALENDAR_ONLY_RE = re.compile(
    r"\b(academic\s+calendar|calendar|holidays?|vacation|sports\s+meet|upcoming|deadlines?|"
    r"class\s+committee|committee\s+meeting|result\s+publication|results?\s+(be\s+)?(published|declared|out|announced)|"
    r"registration|instructional\s+day|events?\s+(this|next)\s+(month|week)|what'?s\s+coming\s+up|"
    r"project\s+review|btp\s+review|course\s+evaluation)\b",
    re.IGNORECASE,
)
_CALENDAR_TIMED_RE = re.compile(
    r"\b(semester|classes|course\s+drop|drop\s+a\s+course|fee\s+payment|fees?|results?|reporting|review)\b",
    re.IGNORECASE,
)
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
           "nov": 11, "dec": 12}
_MONTH_WORD = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_EXPLICIT_DATE_RE = re.compile(
    rf"\b{_MONTH_WORD}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b"
    rf"|\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_WORD}\.?(?:,?\s+(\d{{4}}))?\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b",
    re.IGNORECASE,
)
_ON_DATE_RE = re.compile(
    r"\b(happen\w*|going\s+on|scheduled|planned|events?|anything|what'?s\s+on|what\s+is\s+on|on\s+the\s+calendar|"
    r"special|occasion|deadline|what\s+was\s+on)\b", re.IGNORECASE)
_CAL_GAP_RE = re.compile(
    r"\bhow\s+many\s+days\b|\b(gap|difference|days)\s+(between|from)\b|\bdays\s+(left|remaining)\b|"
    r"\bhow\s+long\s+(until|till|before|after|between)\b", re.IGNORECASE)
_CAL_AFTER_RE = re.compile(
    r"\b(next|first)\s+(event|thing|deadline|exam)\s+(after|following)\s+(?P<anchor>.+?)\s*\??$|"
    r"\bwhat\s+(comes|happens|is)\s+(next\s+)?after\s+(?P<anchor2>.+?)\s*\??$", re.IGNORECASE)
_CAL_EXAMS_RE = re.compile(
    r"^\s*(show|list|give\s+me|tell\s+me|what\s+are)?\s*(me\s+)?(all\s+)?(the\s+)?(exams|examinations|exam\s+(dates|schedule|list|calendar))\s*[?.!]*\s*$|"
    r"\b(all|list\s+(of\s+)?(the\s+)?|show\s+(me\s+)?(all\s+)?(the\s+)?)(exams|examinations)\b|\bexam\s+(dates|calendar|list)\b",
    re.IGNORECASE)
_CAL_LIST_RE = re.compile(
    r"\b(events?|occasions?|functions?|happenings?)\b[^?]*\b(future|upcoming|coming(\s+up)?|next|later|ahead)\b|"
    r"\b(future|upcoming|coming)\s+(events?|dates|deadlines)\b|"
    r"\b(events?|occasions?)\b[^?]*\b(past|over|done|completed|finished|happened|already)\b|"
    r"\b(past|previous|completed|earlier)\s+events?\b|\bwhich\s+events?\b|\blist\s+(all\s+)?(the\s+)?events\b|"
    r"\ball\s+(the\s+)?events\b", re.IGNORECASE)
_CAL_PAST_RE = re.compile(r"\b(past|over|done|completed|finished|happened|already|previous|earlier)\b", re.IGNORECASE)
_TODAY_OVERVIEW_RE = re.compile(
    r"^\s*(what'?s|what\s+is|anything|is\s+there\s+anything|any\s*thing)\s+(happening|going\s+on|on|special|planned)"
    r"(\s+(on\s+)?(campus|here))?\s+(today|tonight)\s*[?.!]*\s*$|^\s*(any\s+)?events?\s+today\s*[?.!]*\s*$",
    re.IGNORECASE)
_WHATS_NEXT_RE = re.compile(r"^\s*(so\s+)?(what'?s|what\s+is|whats)\s+(next|up\s+next|coming\s+up)\s*[?.!]*\s*$", re.IGNORECASE)

# ---- faculty directory: the faculty as a group, not one person
_FACULTY_GROUP_RE = re.compile(
    r"\b(teachers|professors|profs|lecturers|instructors|faculty|faculties|teaching\s+(staff|team)|"
    r"academic\s+(staff|employees|administration)|faculty\s+(members|people|list|directory)|staff\s+members|"
    r"lab\s+(faculty|teaching\s+staff|instructors|staff)|adjuncts?(\s+(faculty|professors?))?|"
    r"assistant\s+professors?|associate\s+professors?|visiting\s+(faculty|professors?)|"
    r"administrative\s+(positions?|roles?|faculty|duties|posts?|staff))\b",
    re.IGNORECASE,
)
_DIRECTORY_ASK_RE = re.compile(
    r"^\s*(who|which|list|show|name|how\s+many|are\s+there|is\s+there|give|tell|find|all|any|what)\b|"
    r"\b(who\s+(are|r|works?|holds?|has)|members\s+of|people\s+(in|are)|included|part\s+of)\b",
    re.IGNORECASE,
)
_NAMED_RE = re.compile(
    r"\b(?:named|called|by\s+the\s+name(?:\s+of)?)\s+(?:dr\.?\s*|prof\.?\s*)?(?P<name>[A-Za-z][A-Za-z.\s]{1,40}?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)

# ---- conversation and manipulation
_META_SOURCE_RE = re.compile(
    r"\b(which|what)\s+(source|sources|document|documents|reference)\b|\bwhat'?s\s+(your|the)\s+source\b|"
    r"\bwhere\s+did\s+(you|that|this|it)\s+(get|come|came)\b|\bwhere\s+(is|was|does)\s+(this|that|it)\s+(from|come\s+from)\b|"
    r"^\s*(source|sources|cite|citation|reference)s?\s*(please|pls)?\s*[?.!]*\s*$|\bcite\s+(the\s+|your\s+)?source\b",
    re.IGNORECASE,
)
_META_HISTORY_RE = re.compile(
    r"\b(first|previous|last|earlier|initial)\s+(question|message|thing)\s+(i|that\s+i)\s+(asked|said|sent|typed)\b|"
    r"\bwhat\s+did\s+i\s+(just\s+)?(ask|say)\b|\bwhat\s+was\s+my\s+(first|previous|last|earlier)\s+(question|message)\b|"
    r"\brepeat\s+my\s+(previous|last|first)\s+question\b",
    re.IGNORECASE,
)
# Requests to invent or override campus facts. The question underneath is
# still answered — from the real data — with a line saying ORION won't make
# things up. "make up" needs a determiner after it: "make-up exam rules" is
# a real regulation question, "make up an attendance policy" is not.
_GUARD_RE = re.compile(
    r"\bignore\s+(all|any|the|your|previous|every)?\s*(of\s+the\s+)?(college|campus|institute|previous|prior)?\s*"
    r"(rules|instructions|regulations|guidelines|policies)\s*(and|,)?\s*|"
    r"\bmake\s+up\s+(a|an|some|the|new|your\s+own|fake)\b\s*|\b(invent|fabricate)\s+(a|an|some|the|new)?\s*|"
    r"\bpretend\s+(that\s+)?|\bact\s+as\s+if\s+",
    re.IGNORECASE,
)

_MY_TIMETABLE_CONTEXT_RE = re.compile(
    r"\b(today|tomorrow|tonight|my\s+(first|last|next)\s+class|right\s+now)\b", re.IGNORECASE
)

_MY_COURSES_RE = re.compile(
    r"\b(my|i)\b[^?]*\b(courses|subjects|papers)\b|\bwhat\s+(courses|subjects)\s+(am\s+i|do\s+i)\b",
    re.IGNORECASE,
)
# "free time/slot/period" plus the phrasings students actually use for the
# same question — "any free classes tomorrow?", "is there any free lecture",
# "do I have a free hour". Found live: "Is there any free class Tomorrow?"
# and "Is there any Free lectures?" matched none of the original three
# phrases, fell through the whole router to the document-search fallback,
# and came back with curriculum text that happened to contain the word
# "Lectures" — the single worst failure mode in the pipeline, because the
# answer looks sourced but is unrelated to the question.
_FREE_TIME_RE = re.compile(
    r"\bwhen\s+am\s+i\s+free\b|\b(free\s+(time|slots?|periods?|classe?s?|lectures?|hours?|days?)"
    r"|gaps?\s+between|breaks?\s+between)\b|"
    r"\bam\s+i\s+free\b|\b(free|off|no\s+class(es)?)\s+(periods?|slots?)\b",
    re.IGNORECASE,
)
_CLASSROOM_RE = re.compile(
    r"\bwhere\b[^?]*\b(class|classes|lecture|classroom)\b|\b(which|what)\s+(room|classroom|hall)\b|"
    r"\bmy\s+classroom\b|\broom\s+(number|no)\b",
    re.IGNORECASE,
)
_DID_I_HAVE_RE = re.compile(r"\b(did|do|will)\s+i\s+have\b", re.IGNORECASE)
_FOCUS_FIRST_RE = re.compile(r"\bfirst\s+(class|lecture|period)\b", re.IGNORECASE)
_FOCUS_LAST_RE = re.compile(r"\blast\s+(class|lecture|period)\b|\b(finish|end)\s+(today|for\s+the\s+day)\b", re.IGNORECASE)
_FOCUS_COUNT_RE = re.compile(r"\bhow\s+many\s+(classes|lectures|periods)\b", re.IGNORECASE)
_LAB_RE = re.compile(r"\blabs?\b|\bpracticals?\b", re.IGNORECASE)
_WHEN_IS_MY_X_RE = re.compile(
    r"\bwhen\s+(is|are|do\s+i\s+have)\s+(my\s+)?(?P<name>[a-z][a-z0-9 &+\-]{2,60}?)\s+(class|classes|lecture|lab)\b",
    re.IGNORECASE,
)
_WHO_TEACHES_NAME_RE = re.compile(
    r"\bwho\s+(teaches|takes|handles|is\s+teaching|is\s+taking)\s+(the\s+)?(?P<name>[a-z][a-z0-9 &+\-]{2,80}?)"
    r"(\s+(course|class|subject|this\s+semester))?\s*\??\s*$",
    re.IGNORECASE,
)

# "who researches X", "anyone working on X", "recommend a faculty for X".
_RESEARCH_RE = re.compile(
    r"(?:\b(?:research(?:es|ing)?|stud(?:y|ies|ying)|specializ\w*|specialis\w*|expert\w*|interested|works?|working|guide|supervis\w*|mentor\w*)"
    r"\s+(?:in|on|with|about|for)?\s*|\b(?:recommend|suggest)\w*\s+(?:a\s+|an\s+|some\s+)?"
    r"(?:faculty|professor|guide|mentor|supervisor|someone|somebody|anyone|anybody)\w*\s+(?:member\s+)?(?:for|in|on)\s+)"
    r"(?P<topic>[a-z0-9][a-z0-9 ,&/+\-]{1,80})",
    re.IGNORECASE,
)
_RESEARCH_TRIGGER_RE = re.compile(
    r"\b(who|which|any|anyone|anybody|someone|somebody|faculty|professors?|recommend|suggest|guide|supervisor|mentor)\b",
    re.IGNORECASE,
)
_RESEARCH_VERB_RE = re.compile(
    r"\b(research\w*|stud(y|ies|ying)|specializ\w*|specialis\w*|expert\w*|interested|works?\s+(on|in)|"
    r"working\s+(on|in)|recommend\w*|suggest\w*)\b",
    re.IGNORECASE,
)

# Extra document topics beyond _SEMANTIC_TOPIC_RE, with a preferred source.
_HOSTEL_TOPIC_RE = re.compile(
    r"\b(hostel|curfew|in[\s-]?time|gate|outpass|out[\s-]?pass|gate\s*pass|leave\s+(form|campus)|night|"
    r"visitors?|guests?|cook(ing)?|appliances?|heater|iron|room\s+swap|swap\s+rooms?|vacation\s+stay|"
    r"silence\s+hours?|birthday|pets?|smoking|alcohol|intoxicants?|in/out\s+register|biometric)\b",
    re.IGNORECASE,
)
_RAGGING_TOPIC_RE = re.compile(r"\bragg(ing|ed)?\b|\banti[\s-]?ragging\b", re.IGNORECASE)
_PROCEDURE_TOPIC_RE = re.compile(
    r"\b(transcripts?|certificate\s+verification|document\s+verification|verification\s+(fee|procedure|process))\b",
    re.IGNORECASE,
)
_REGULATION_TOPIC_RE = re.compile(
    r"\b(attendance|condonation|cgpa|sgpa|grade\s*points?|grading|grades?\s+system|credits?|graduat\w*|degree|"
    r"drop(ping)?\s+(a\s+)?course|withdraw\w*|backlogs?|fail\w*|repeat\w*|make[\s-]?up|supplementary|incomplete|"
    r"dual\s+degree|b\.?tech[\s-]*ms|honou?rs|minor|probation|terminat\w*|maximum\s+duration|duration|"
    r"summer\s+term|registration\s+requirement|continuation|debarred|detained|eligib\w*|end[\s-]?sem\w*\s+exam\w*\s+eligib\w*|"
    r"exam(ination)?\s+hall|malpractice|unfair\s+means|invigilat\w*|disciplin\w*|misconduct|conduct|dress\s+code|"
    r"library|btp|b\.?\s?tech\s+project|major\s+project|project\s+(rules|guidelines|evaluation))\b",
    re.IGNORECASE,
)

# An explicit admission-year/cohort mention in the question text itself —
# e.g. "the 2026 admission batch", "students admitted in 2021", "26-onwards
# regulations". Deliberately narrow (a trigger word near the year, not just
# the bare year) so an unrelated "2026-27" academic-calendar mention doesn't
# misfire: only regulation/curriculum-shaped questions call this at all
# (see classify()), and even then only an explicit admission/batch/cohort/
# regulations word next to the year counts. CLAUDE.md §20: cohort isolation
# must not be defeated by a spelling difference or silently ignored when the
# question names a cohort other than the caller's own.
_COHORT_TRIGGER = r"admissions?|admitted|batch|onwards?|cohort|regulations?|joined|joining|curriculum|curricula|syllabus|syllabi"
_COHORT_26_RE = re.compile(
    rf"\b(?:{_COHORT_TRIGGER})\b[^.?!]{{0,25}}\b(?:20)?26\b"
    rf"|\b(?:20)?26\b[^.?!]{{0,25}}\b(?:{_COHORT_TRIGGER})\b"
    r"|\b26[\s-]?onwards?\b",
    re.IGNORECASE,
)
_COHORT_21_RE = re.compile(
    rf"\b(?:{_COHORT_TRIGGER})\b[^.?!]{{0,25}}\b(?:20)?21\b"
    rf"|\b(?:20)?21\b[^.?!]{{0,25}}\b(?:{_COHORT_TRIGGER})\b"
    r"|\b(?:20)?21[\s\-–]*(?:to\s+)?(?:20)?25\b",
    re.IGNORECASE,
)


def detect_cohort_reference(query: str) -> str | None:
    """"21-25" / "26-onwards" if the question explicitly names that cohort,
    else None — never inferred from anything but the text itself. The
    caller's OWN cohort (campus.cohort_family) is a completely separate,
    profile-derived value; this only catches a question asking about a
    *different* one."""
    q = query or ""
    if _COHORT_21_RE.search(q):
        return "21-25"
    if _COHORT_26_RE.search(q):
        return "26-onwards"
    return None


# "is it different for 2026 students", "how does that compare to mine",
# "...vs the 2021 batch" — the question wants BOTH cohorts' rules shown side
# by side, not just the named one substituted for the caller's own.
_COHORT_COMPARE_RE = re.compile(
    r"\b(different|differs?|compare[sd]?|vs\.?|versus|compared\s+to|than\s+mine|than\s+my|same\s+as\s+mine)\b",
    re.IGNORECASE,
)


def strip_cohort_noise(query: str) -> str:
    """The actual topic underneath a cohort-comparison question ("is the
    attendance rule different for the 2026 admission batch compared to
    mine?") — with the comparison/cohort scaffolding removed, so a passage
    scorer like documents.best_passages() judges the query on its real
    subject ("attendance") instead of on words like "2026"/"batch"/
    "compared"/"mine" that never appear verbatim in the regulation text and
    would otherwise tank its confidence score for a perfectly good match."""
    q = _COHORT_COMPARE_RE.sub(" ", query)
    q = _COHORT_21_RE.sub(" ", q)
    q = _COHORT_26_RE.sub(" ", q)
    q = re.sub(r"\bmine\b|\bmy\b", " ", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    return q or query

_OVERVIEW_RE = re.compile(
    r"^\s*(what\s+are|what'?s|tell\s+me(\s+about)?|list|explain|summari[sz]e|give\s+me|show\s+me)\s+(the\s+|all\s+the\s+)?"
    r"(main\s+|key\s+|important\s+|basic\s+|general\s+)?(?P<topic>anti[\s-]?ragging|ragging|hostel)\s+"
    r"(rules|regulations|policy|policies|guidelines)\s*\??\s*$",
    re.IGNORECASE,
)
_QUESTION_START_RE = re.compile(
    r"^\s*(what|what's|whats|who|whom|whose|when|where|which|why|how|can|could|may|is|are|am|do|does|did|"
    r"should|shall|will|would|tell|explain|list|show|give|find|any|i\s+want|i\s+need|please)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z]{3,}", re.IGNORECASE)


def _looks_like_question(q: str) -> bool:
    return q.rstrip().endswith("?") or bool(_QUESTION_START_RE.match(q))


def _course_code(q: str) -> str | None:
    m = _COURSE_CODE_ANYCASE_RE.search(q)
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    m = _COURSE_CODE_RE.search(q)
    return m.group(1).upper() if m else None


def _day_reference(q: str) -> str | None:
    """The day a question refers to, as a normalised phrase. Delegates to
    tempo.day_reference() so the router, retrieval and the answer writer
    all recognise the same vocabulary ("tomorrow", "the next day", "day
    after tomorrow", "next Friday", "tonight")."""
    return tempo.day_reference(q)


def _resolved_date(day_ref: str | None) -> str | None:
    """The ISO date a day reference resolves to, for QueryPlan.
    resolved_date — resolved once, here, so no layer below has to re-parse
    the phrase or invent its own "today" (tempo.py explains the bug)."""
    target = tempo.resolve_to_date(day_ref)
    return target.isoformat() if target else None


def _timetable_hints(q: str) -> dict[str, str]:
    hints: dict[str, str] = {}
    if _FOCUS_FIRST_RE.search(q):
        hints["focus"] = "first"
    elif _FOCUS_LAST_RE.search(q):
        hints["focus"] = "last"
    elif _FOCUS_COUNT_RE.search(q):
        hints["focus"] = "count"
    if _LAB_RE.search(q):
        hints["entry_type"] = "lab"
    m = _WHEN_IS_MY_X_RE.search(q)
    if m:
        name = m.group("name").strip()
        if name.lower() not in {"next", "first", "last", "the", "my", "a"}:
            hints["course_filter"] = name
    return hints


# Tails that say nothing about the research topic itself and only ever
# hurt the match: "...on campus", "...here at IIIT", "...who is teaching
# soon". Found live: "Who researches computer vision on campus?" searched
# for the literal phrase "computer vision on campus" and matched nobody,
# while "Who researches computer vision?" matched 13 people.
_TOPIC_TAIL_RE = re.compile(
    r"\s+(?:on|at|in|around|across)\s+(?:the\s+)?(?:campus|college|institute|university|iiit\w*|here)\b.*$"
    r"|\s+(?:who|whose|that|which)\b.*$"
    r"|\s+(?:here|currently|right\s+now|nowadays)\b.*$",
    re.IGNORECASE,
)


def _research_topic(q: str) -> str | None:
    m = _RESEARCH_RE.search(q)
    if not m:
        return None
    topic = m.group("topic")
    topic = re.split(r"\s+(?:and|&)\s+(?:when|where|how|can|could)\b|[?.!]", topic, maxsplit=1)[0]
    topic = _TOPIC_TAIL_RE.sub("", topic)
    topic = re.sub(r"\b(research|researches|area|areas|field|fields|topics?|domain)\s*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^(the|a|an)\s+", "", topic.strip(), flags=re.IGNORECASE).strip(" ,")
    return topic or None


def _role_key(q: str) -> str | None:
    for pattern, key in _ROLE_TERMS:
        if re.search(pattern, q, re.IGNORECASE):
            return key
    # "Who handles student welfare?", "who looks after academic affairs?" —
    # an office, not a course: the associate dean for it.
    if _OFFICE_AREA_RE.search(q) and (_HANDLES_RE.search(q) or re.search(r"\bwho\b", q, re.IGNORECASE)):
        return "dean"
    return None


def classify(query: str) -> QueryPlan:
    """Classify a raw user query into a QueryPlan. Pure function, no I/O.

    The returned plan's `raw_query` is the spelling-corrected question (and,
    for "pretend/make up ..." requests, the real question underneath), so
    every later stage reads the same text the router understood."""
    q = (query or "").strip()
    if not q:
        return QueryPlan(raw_query=query, route=RouteType.UNSUPPORTED, reasoning="empty query")
    corrected, fixes = lexicon.correct_spelling(q)
    core = corrected
    guarded = bool(_GUARD_RE.search(corrected))
    if guarded:
        core = re.sub(r"\s+", " ", _GUARD_RE.sub(" ", corrected)).strip(" ,.;:") or corrected
    plan = _classify(core)
    hints = dict(plan.hints)
    if fixes:
        hints["spelling"] = ", ".join(f"{a}->{b}" for a, b in fixes)
    if guarded:
        hints["guard"] = "yes"
    reasoning = plan.reasoning
    if fixes:
        reasoning = f"[spelling: {hints['spelling']}] {reasoning}"
    return dataclasses.replace(plan, raw_query=core, hints=hints, reasoning=reasoning)


def _classify(query: str) -> QueryPlan:
    q = (query or "").strip()
    if not q:
        return QueryPlan(raw_query=query, route=RouteType.UNSUPPORTED, reasoning="empty query")

    def plan(route: RouteType, intent: StructuredIntent = StructuredIntent.NONE, reasoning: str = "", **kw) -> QueryPlan:
        return QueryPlan(raw_query=query, route=route, structured_intent=intent, reasoning=reasoning, **kw)

    # --- small talk: answered directly, never reaches retrieval or the LLM ------
    if _GREETING_RE.match(q) or _GREETING_LOOSE_RE.match(q):
        return plan(RouteType.SMALL_TALK, topic_text=_greeting_reply(),
                    reasoning="matched a greeting -> time-of-day canned reply, no retrieval or LLM call")
    if _THANKS_RE.match(q):
        return plan(RouteType.SMALL_TALK, topic_text=random.choice(_THANKS_REPLIES),
                    reasoning="matched thanks -> canned reply, no retrieval or LLM call")
    if _BYE_RE.match(q):
        return plan(RouteType.SMALL_TALK, topic_text=random.choice(_BYE_REPLIES),
                    reasoning="matched a farewell -> canned reply, no retrieval or LLM call")
    if _CAPABILITIES_RE.match(q):
        return plan(RouteType.SMALL_TALK, topic_text=_CAPABILITIES_REPLY,
                    reasoning="matched a capabilities/help question -> canned reply, no retrieval or LLM call")
    if _HOW_ARE_YOU_RE.match(q):
        return plan(RouteType.SMALL_TALK, topic_text=random.choice(_HOW_ARE_YOU_REPLIES),
                    reasoning="matched 'how are you' -> canned reply, no retrieval or LLM call")

    # --- about this conversation: answered from the history, never from campus data -------
    if _META_SOURCE_RE.search(q) and len(q.split()) <= 12:
        return plan(RouteType.STRUCTURED, StructuredIntent.CONVERSATION, hints={"meta": "source"},
                    reasoning="asks where the previous answer came from -> its source line")
    if _META_HISTORY_RE.search(q):
        which = "first" if re.search(r"\bfirst|initial\b", q, re.IGNORECASE) else "previous"
        return plan(RouteType.STRUCTURED, StructuredIntent.CONVERSATION, hints={"meta": "history", "which": which},
                    reasoning=f"asks about the {which} question in this conversation")

    if _WHATS_NEXT_RE.match(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.NEXT_CLASS, hints={"with_event": "yes"},
                    reasoning="bare 'what's next' -> next class, plus the next calendar event")
    if _TODAY_OVERVIEW_RE.match(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.ACADEMIC_CALENDAR, topic_text=q,
                    hints={"cal_mode": "today"}, resolved_date=_resolved_date("today"),
                    reasoning="what's happening today -> today's calendar events + classes")

    course_code = _course_code(q)
    timed = bool(_TIMING_WORD_RE.search(q))

    # --- the academic calendar as something to reason over ------------------------
    cal = _calendar_plan(q, plan, course_code)
    if cal is not None:
        return cal

    # --- academic calendar / exam dates (before "my records": "when will results be published") ----
    exam_word = bool(_EXAM_WORD_RE.search(q))
    if exam_word and timed and (course_code or re.search(r"\bmy\s+[a-z].*\bexam", q, re.IGNORECASE)):
        return plan(RouteType.STRUCTURED, StructuredIntent.EXAM_SCHEDULE, topic_text=q,
                    course_code=course_code,
                    reasoning="exam + timing + a specific course -> exams table, falling back to calendar exam window")
    if (exam_word and timed) or _CALENDAR_ONLY_RE.search(q) or (
        timed and _CALENDAR_TIMED_RE.search(q) and not _MY_TIMETABLE_CONTEXT_RE.search(q)
        and not _REGULATION_TOPIC_RE.search(q) and re.search(r"\b(when|date|last\s+(date|day)|deadline)\b", q, re.IGNORECASE)
    ):
        return plan(RouteType.STRUCTURED, StructuredIntent.ACADEMIC_CALENDAR, topic_text=q,
                    reasoning="date/event question -> academic_calendar (live)")

    # --- out of scope: personal records ORION doesn't hold, or not campus related ----
    if _MY_RECORDS_RE.search(q) and not _HYPOTHETICAL_RE.search(q):
        kind = "attendance" if re.search(r"attendance", q, re.IGNORECASE) else (
            "fees" if re.search(r"fee", q, re.IGNORECASE) else "grades")
        return plan(RouteType.UNSUPPORTED, StructuredIntent.OUT_OF_SCOPE, hints={"kind": kind},
                    reasoning=f"asks for a personal {kind} record -> ORION doesn't store these")
    if _FEE_PAYMENT_RE.search(q):
        return plan(RouteType.UNSUPPORTED, StructuredIntent.OUT_OF_SCOPE, hints={"kind": "fees"},
                    reasoning="fee payment -> not handled by ORION")
    if _GENERAL_KNOWLEDGE_RE.search(q):
        return plan(RouteType.UNSUPPORTED, StructuredIntent.OUT_OF_SCOPE, hints={"kind": "general"},
                    reasoning="general-knowledge / non-campus request -> out of scope")

    # --- about me ----------------------------------------------------------------
    if _PROFILE_RE.search(q) and not course_code:
        return plan(RouteType.STRUCTURED, StructuredIntent.MY_PROFILE, topic_text=q,
                    reasoning="asks about the caller's own academic context -> orion_student_context")

    # --- announcements -------------------------------------------------------------
    if _ANNOUNCEMENT_RE.search(q) and not _RAGGING_TOPIC_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.ANNOUNCEMENTS,
                    reasoning="announcements/notices -> approved, current announcements")

    # --- hostel wardens / contacts ----------------------------------------------------
    if _WARDEN_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.HOSTEL_WARDENS, topic_text=q,
                    reasoning="warden/hostel contact -> hostel_wardens (live)")

    # --- institutional roles (HOD, registrar, dean, medical officer...) ----------------
    role = _role_key(q)
    if role and (_ROLE_QUESTION_RE.search(q) or _looks_like_question(q)):
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_ROLE, topic_text=q, hints={"role": role},
                    reasoning=f"institutional role ({role}) -> faculty.designation")

    # --- structured: mess menu ---------------------------------------------------
    dish_m = _DISH_RE.search(q)
    dish_question = bool(dish_m) and not _HOSTEL_TOPIC_RE.search(q) and not re.search(
        r"\b(allowed|permitted|rules?|policy|banned|prohibited)\b", q, re.IGNORECASE)
    if _MESS_WORD_RE.search(q) or dish_question:
        return _mess_plan(q, plan)

    # --- faculty by name, when the question says "named"/"called" --------------------
    named_m = _NAMED_RE.search(q)
    if named_m and not course_code:
        name = named_m.group("name").strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"'faculty named <name>' ({name}) -> faculty lookup")

    # --- the faculty directory as a whole -----------------------------------------------
    if _is_directory_question(q, course_code):
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_DIRECTORY, topic_text=q,
                    reasoning="asks about the faculty as a group -> faculty directory (by designation/category)")

    # --- my courses / free time / classroom -----------------------------------------
    if _MY_COURSES_RE.search(q) and not course_code and not _WHO_TEACHES_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.MY_COURSES,
                    reasoning="asks for the caller's courses -> distinct courses in their live timetable")
    if _FREE_TIME_RE.search(q):
        free_day = _day_reference(q) or "today"
        return plan(RouteType.STRUCTURED, StructuredIntent.FREE_TIME, topic_text=free_day,
                    resolved_date=_resolved_date(free_day),
                    reasoning=f"free period/class question -> gaps in the caller's timetable for {free_day} ({_resolved_date(free_day)})")
    if _CLASSROOM_RE.search(q) and not course_code:
        return plan(RouteType.STRUCTURED, StructuredIntent.CLASSROOM, topic_text=q,
                    reasoning="where is my class -> next class + section room allocation")

    # --- structured: timetable -------------------------------------------------
    hints = _timetable_hints(q)
    if _NEXT_CLASS_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.NEXT_CLASS, hints=hints,
                    reasoning="matched next-class pattern -> orion_next_class (live timetable)")
    if _WEEK_WORD_RE.search(q) and (_TIMETABLE_WORD_RE.search(q) or _LAB_RE.search(q)):
        return plan(RouteType.STRUCTURED, StructuredIntent.WEEK_TIMETABLE, hints=hints,
                    reasoning="matched week-timetable pattern -> orion_week_timetable")
    if _TODAY_TIMETABLE_RE.search(q) or (_DID_I_HAVE_RE.search(q) and re.search(r"\btoday\b", q, re.IGNORECASE)):
        return plan(RouteType.STRUCTURED, StructuredIntent.DAY_TIMETABLE, hints=hints,
                    resolved_date=_resolved_date("today"),
                    reasoning="matched today-timetable pattern -> orion_day_timetable")
    day_ref = _day_reference(q)
    if day_ref and (_TIMETABLE_WORD_RE.search(q) or _DID_I_HAVE_RE.search(q) or _LAB_RE.search(q)):
        return plan(RouteType.STRUCTURED, StructuredIntent.DAY_OF_WEEK_TIMETABLE, topic_text=day_ref, hints=hints,
                    resolved_date=_resolved_date(day_ref),
                    reasoning=f"matched a day reference ({day_ref} = {_resolved_date(day_ref)}) + class/timetable word -> orion_day_timetable for that date")
    time_m = _TIME_RE.search(q)
    if time_m and _TIMETABLE_WORD_RE.search(q):
        time_text = time_m.group(0).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.CLASS_AT_TIME, topic_text=time_text,
                    reasoning=f"matched a specific time ({time_text}) + class/timetable word -> orion_next_class as of that time")
    if hints.get("course_filter"):
        return plan(RouteType.STRUCTURED, StructuredIntent.WEEK_TIMETABLE, hints=hints,
                    reasoning="'when is my <course> class' -> week timetable filtered to that course")

    # --- courses ---------------------------------------------------------------------
    if _WHO_TEACHES_RE.search(q) and course_code:
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_FOR_COURSE, course_code=course_code,
                    reasoning="matched 'who teaches <course code>' -> timetable/course join")
    name_m = _WHO_TEACHES_NAME_RE.search(q)
    if name_m and not course_code:
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_FOR_COURSE, topic_text=name_m.group("name").strip(),
                    hints={"course_name": name_m.group("name").strip()},
                    reasoning="matched 'who teaches <course name>' -> course resolved by name")
    if course_code and (_COURSE_INFO_WORD_RE.search(q) or _COURSE_ABOUT_LEAD_RE.match(q)
                        or re.search(r"\b(semester|what\s+is|tell\s+me)\b", q, re.IGNORECASE)):
        return plan(RouteType.STRUCTURED, StructuredIntent.COURSE_INFO, course_code=course_code,
                    reasoning="matched course-info pattern -> courses table (+ curriculum for credits)")

    # --- structured: faculty lookup by name -------------------------------------
    about_m = _FACULTY_ABOUT_RE.search(q)
    if about_m:
        name = about_m.group(2).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"matched 'tell me about/who is <title> <name>' ({name}) -> faculty table lookup")
    possessive_m = _FACULTY_POSSESSIVE_RE.search(q)
    if possessive_m:
        name = possessive_m.group(1).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"matched '<name>'s email/office/office hours' ({name}) -> faculty table lookup")
    attr_of_m = _FACULTY_ATTR_OF_RE.search(q)
    if attr_of_m:
        name = attr_of_m.group(2).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"matched 'email/office/cabin of/for <name>' ({name}) -> faculty table lookup")
    attr_after_m = _FACULTY_ATTR_AFTER_NAME_RE.search(q)
    if attr_after_m:
        name = attr_after_m.group(1).strip().rstrip("'").strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"matched '<title> <name> email/office/cabin' ({name}) -> faculty table lookup")
    where_m = _FACULTY_WHERE_RE.search(q)
    if where_m:
        name = where_m.group(1).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name,
                    reasoning=f"matched 'where is <title> <name>' ({name}) -> faculty table lookup (office)")
    meet_m = re.search(r"\b(?:meet|reach|find|contact)\s+(dr\.?|prof\.?|professor)\s+([A-Za-z][A-Za-z.\s]{1,40}?)\s*\??$", q, re.IGNORECASE)
    if meet_m:
        name = meet_m.group(2).strip()
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_LOOKUP, topic_text=name, hints={"focus": "meet"},
                    reasoning=f"'when can I meet <title> <name>' ({name}) -> faculty + teaching schedule")

    # --- faculty by research topic (lexical match; no embeddings needed) --------------
    topic = _research_topic(q)
    if topic and _RESEARCH_TRIGGER_RE.search(q) and _RESEARCH_VERB_RE.search(q) and not _REGULATION_TOPIC_RE.fullmatch(topic):
        meet = bool(_MEET_AVAILABILITY_RE.search(q))
        return plan(RouteType.HYBRID, StructuredIntent.FACULTY_RESEARCH, topic_text=topic,
                    hints={"meet": "yes"} if meet else {},
                    reasoning="faculty + research topic -> faculty.research_interests match (+ schedule if asked)")
    if _FACULTY_MENTION_RE.search(q) or ("faculty" in q.lower() and _MEET_AVAILABILITY_RE.search(q)):
        return plan(RouteType.HYBRID, StructuredIntent.FACULTY_RESEARCH, topic_text=_extract_topic(q),
                    hints={"meet": "yes"} if _MEET_AVAILABILITY_RE.search(q) else {},
                    reasoning="faculty + topic/meet pattern -> faculty.research_interests match + schedule")

    # --- semantic: document corpus -----------------------------------------------
    overview_m = _OVERVIEW_RE.match(q)
    if overview_m:
        topic = "hostel" if "hostel" in overview_m.group("topic").lower() else "anti-ragging"
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"overview": topic},
                    reasoning=f"broad '{topic} rules' question -> overview of the key rules")
    if _HOSTEL_TOPIC_RE.search(q):
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"category": "hostel"},
                    reasoning="hostel topic -> hostel rules first, then the rest of the corpus")
    if _RAGGING_TOPIC_RE.search(q):
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"category": "anti-ragging"},
                    reasoning="ragging topic -> anti-ragging documents first")
    if _PROCEDURE_TOPIC_RE.search(q):
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"category": "academics"},
                    reasoning="transcript/certificate topic -> procedures first")

    # A regulation/curriculum question may explicitly name a cohort other
    # than the caller's own ("the 2026 admission batch", "under the 26
    # onwards regulations") — CLAUDE.md §20 forbids silently answering that
    # with the caller's own-cohort rule instead. detect_cohort_reference()
    # only fires on an explicit mention, never inferred from context, so an
    # ordinary "what is the attendance requirement?" still defaults to the
    # caller's own cohort (service.py's cohort_family(profile)) untouched.
    cohort_ref = detect_cohort_reference(q)
    cohort_hint: dict[str, str] = {}
    if cohort_ref:
        cohort_hint["cohort_ref"] = cohort_ref
        if _COHORT_COMPARE_RE.search(q):
            cohort_hint["cohort_compare"] = "yes"
    if _REGULATION_TOPIC_RE.search(q):
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"document_type": "regulations", **cohort_hint},
                    reasoning="academic rule topic -> the student's UG regulations first"
                               + (f" (question names the {cohort_ref} cohort)" if cohort_ref else ""))
    if _SEMANTIC_TOPIC_RE.search(q):
        return plan(RouteType.SEMANTIC, topic_text=q, hints=cohort_hint,
                    reasoning="matched a regulations/policy/procedure topic -> document_chunks")

    # --- nothing specific matched: ask what it MEANS --------------------------------
    # No rule recognised the wording, so compare the question's meaning with
    # the example bank (intents.py) before giving up on structured data —
    # "what's the dining hall serving?" is a mess question whatever its words.
    semantic = _semantic_plan(q, plan, course_code, cohort_hint)
    if semantic is not None:
        # Marked so a terse follow-up ("what about the next day?") can still
        # prefer the conversation's context over a meaning-based guess
        # (backend/app/api/ai.py, _is_unresolved).
        return dataclasses.replace(semantic, hints={**semantic.hints, "via": "semantic"})

    # A real question still gets a real attempt: the service first tries to
    # recognise a course or faculty name in it, then searches the documents.
    # Statements and gibberish stay UNSUPPORTED (nothing to search for).
    if _looks_like_question(q) and len(_WORD_RE.findall(q)) >= 2:
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"fallback": "yes", **cohort_hint},
                    reasoning="no specific pattern; question-shaped -> entity linking, then document search")

    return plan(RouteType.UNSUPPORTED,
                reasoning="no structured/semantic/hybrid pattern matched — ambiguous or out of scope")


# ------------------------------------------------------------------- builders

def _mess_plan(q: str, plan) -> QueryPlan:
    meal_m = _MEAL_RE.search(q)
    meal = None
    if meal_m:
        raw_meal = meal_m.group(1).lower()
        meal = "snacks" if raw_meal.startswith("snack") else raw_meal
    dish_m = _DISH_RE.search(q)
    hints = {"dish": dish_m.group(1).lower()} if dish_m else {}
    if _WEEK_WORD_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.MESS_WEEK, meal=meal, hints=hints,
                    reasoning="matched mess/food + week pattern -> mess_week (live mess_menus)")
    day_ref = _day_reference(q)
    if day_ref and day_ref != "today":
        return plan(RouteType.STRUCTURED, StructuredIntent.MESS_ON_DAY, topic_text=day_ref, meal=meal, hints=hints,
                    resolved_date=_resolved_date(day_ref),
                    reasoning=f"matched mess/food + day reference ({day_ref} = {_resolved_date(day_ref)}) -> mess_on_day (live mess_menus)")
    return plan(RouteType.STRUCTURED, StructuredIntent.MESS_TODAY, meal=meal, hints=hints,
                resolved_date=_resolved_date("today"),
                reasoning="matched mess/food pattern -> mess_today (live mess_menus)"
                          + (f", looking for {hints['dish']}" if hints else ""))


def explicit_date(q: str, today: date | None = None) -> date | None:
    """"September 24", "24th Sept", "January 4, 2027", "2026-10-26" -> a date.
    With no year, the date inside the current academic year (July-June) is
    meant: in September 2026, "January 4" is January 2027."""
    m = _EXPLICIT_DATE_RE.search(q or "")
    if not m:
        return None
    today = today or tempo.today_ist()
    try:
        if m.group(1):
            month, day, year = _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), m.group(3)
        elif m.group(5):
            day, month, year = int(m.group(4)), _MONTHS[m.group(5)[:3].lower()], m.group(6)
        else:
            return date(int(m.group(7)), int(m.group(8)), int(m.group(9)))
        if year:
            return date(int(year), month, day)
        term_start = today.year if today.month >= 7 else today.year - 1
        return date(term_start if month >= 7 else term_start + 1, month, day)
    except (ValueError, KeyError):
        return None


# Words that mark a question as being about calendar events (not a rule).
_CAL_EVENT_WORDS_RE = re.compile(
    r"\b(exams?|examinations?|end[\s-]?sem\w*|mid[\s-]?sem\w*|class(es)?\s+(end|start|begin)\w*|classes|"
    r"semester|sports\s+meet|registration|results?|review|deadline|fee\s+payment|course\s+drop|"
    r"instructional\s+day|committee|evaluation|events?|holiday|vacation)\b", re.IGNORECASE)


def _calendar_plan(q: str, plan, course_code: str | None) -> QueryPlan | None:
    """Calendar questions that need reasoning over events, not one lookup:
    a specific date, the gap between two events, the event after another,
    all exams, upcoming/past events."""
    def cal(mode: str, reasoning: str, **hints: str) -> QueryPlan:
        return plan(RouteType.STRUCTURED, StructuredIntent.ACADEMIC_CALENDAR, topic_text=q,
                    hints={"cal_mode": mode, **hints}, reasoning=reasoning)

    food_or_class = _MESS_WORD_RE.search(q) or _DISH_RE.search(q) or (
        _TIMETABLE_WORD_RE.search(q) and not _CAL_EVENT_WORDS_RE.search(q))
    on = explicit_date(q)
    if on and not food_or_class and not course_code and (_ON_DATE_RE.search(q) or not _REGULATION_TOPIC_RE.search(q)):
        return cal("on_date", f"a specific date ({on}) -> academic calendar events on/around it", date=on.isoformat())
    if _CAL_GAP_RE.search(q) and _CAL_EVENT_WORDS_RE.search(q) and not re.search(
            r"\b(leave|attendance|condon\w*|absent|medical)\b", q, re.IGNORECASE):
        return cal("gap", "how many days between calendar events -> computed from the academic calendar")
    after_m = _CAL_AFTER_RE.search(q)
    if after_m and _CAL_EVENT_WORDS_RE.search(q + " event"):
        anchor = (after_m.group("anchor") or after_m.group("anchor2") or "").strip()
        return cal("after_event", f"the event after '{anchor}' -> academic calendar", anchor=anchor)
    if _CAL_EXAMS_RE.search(q) and not course_code:
        return cal("exams", "list the exams -> every exam on the academic calendar")
    if _CAL_LIST_RE.search(q) and not _MESS_WORD_RE.search(q):
        mode = "past" if _CAL_PAST_RE.search(q) else "upcoming"
        return cal(mode, f"{mode} events -> academic calendar")
    return None


# "Who are the X" is a directory question unless X is really a topic, a
# course, a person, or a rule.
_NOT_DIRECTORY_RE = re.compile(
    r"\b(advis[eo]r|rules?|regulations?|polic(y|ies)|guidelines?|allowed|attendance|feedback|evaluation|"
    r"meeting|office\s+hours|email|cabin|research\w*|speciali[sz]\w*|expert\w*|interested)\b", re.IGNORECASE)
_TITLED_NAME_RE = re.compile(r"\b(dr|prof|mr|mrs|ms)\.?\s*[A-Z][a-z]+", re.IGNORECASE)
_FILLER_TOPIC_RE = re.compile(
    r"^(here|there|now|today|campus|college|institute|iiit\w*|as\s+.*|at\s+.*|in\s+(this|the|our)\b.*)$", re.IGNORECASE)


def _is_directory_question(q: str, course_code: str | None) -> bool:
    if course_code or not _FACULTY_GROUP_RE.search(q) or not _DIRECTORY_ASK_RE.search(q):
        return False
    if _NOT_DIRECTORY_RE.search(q) or _TITLED_NAME_RE.search(q):
        return False
    topic = _research_topic(q)
    if topic and _RESEARCH_VERB_RE.search(q) and not _FILLER_TOPIC_RE.match(topic):
        return False
    # "who teaches <course>" is about a course, not the directory
    if _WHO_TEACHES_NAME_RE.search(q) and not re.search(r"\bwho\s+teach(es)?\s+(here|at\b|in\s+(this|the))", q, re.IGNORECASE):
        return False
    return True


def _semantic_plan(q: str, plan, course_code: str | None, cohort_hint: dict[str, str]) -> QueryPlan | None:
    """A plan chosen by meaning (intents.py), for a question no rule matched.
    Only a confident prediction is used; entity-bearing intents (a named
    person, a named course) stay on the entity-linking path, which checks
    the name against the real directory instead of trusting a guess."""
    pred = intents.predict(q)
    if not pred.confident:
        return None
    label = pred.label
    why = f"semantic match -> {label} (similarity {pred.score:.2f}, next best {pred.runner_up})"
    if label == "faculty_directory" and not course_code:
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_DIRECTORY, topic_text=q, reasoning=why)
    if label == "faculty_role":
        # A role answer needs a role, department or office actually named —
        # "who leads the lab sessions?" names none, and a list of deans
        # would be a confident answer to a question nobody asked.
        role = _role_key(q)
        if role is None and re.search(rf"\b({_DEPT_WORDS})\b", q, re.IGNORECASE) and re.search(
                r"\b(head|heads|heading|leads?|in[\s-]charge)\b", q, re.IGNORECASE):
            role = "hod"
        if role is None:
            return None
        return plan(RouteType.STRUCTURED, StructuredIntent.FACULTY_ROLE, topic_text=q, hints={"role": role}, reasoning=why)
    if label == "faculty_research":
        topic = _research_topic(q) or _extract_topic(q)
        return plan(RouteType.HYBRID, StructuredIntent.FACULTY_RESEARCH, topic_text=topic,
                    hints={"meet": "yes"} if _MEET_AVAILABILITY_RE.search(q) else {}, reasoning=why)
    if label == "mess":
        return dataclasses.replace(_mess_plan(q, plan), reasoning=why)
    if label == "calendar":
        return _calendar_plan(q, plan, course_code) or plan(
            RouteType.STRUCTURED, StructuredIntent.ACADEMIC_CALENDAR, topic_text=q, reasoning=why)
    if label == "timetable":
        day_ref = _day_reference(q)
        if day_ref and day_ref != "today":
            return plan(RouteType.STRUCTURED, StructuredIntent.DAY_OF_WEEK_TIMETABLE, topic_text=day_ref,
                        resolved_date=_resolved_date(day_ref), hints=_timetable_hints(q), reasoning=why)
        if re.search(r"\btoday\b", q, re.IGNORECASE):
            return plan(RouteType.STRUCTURED, StructuredIntent.DAY_TIMETABLE, resolved_date=_resolved_date("today"),
                        hints=_timetable_hints(q), reasoning=why)
        return plan(RouteType.STRUCTURED, StructuredIntent.NEXT_CLASS, hints=_timetable_hints(q), reasoning=why)
    if label == "free_time":
        free_day = _day_reference(q) or "today"
        return plan(RouteType.STRUCTURED, StructuredIntent.FREE_TIME, topic_text=free_day,
                    resolved_date=_resolved_date(free_day), reasoning=why)
    simple = {"announcements": StructuredIntent.ANNOUNCEMENTS, "wardens": StructuredIntent.HOSTEL_WARDENS,
              "profile": StructuredIntent.MY_PROFILE, "my_courses": StructuredIntent.MY_COURSES}
    if label in simple:
        return plan(RouteType.STRUCTURED, simple[label], topic_text=q, reasoning=why)
    if label in {"meta_source", "meta_history"}:
        meta = "source" if label == "meta_source" else "history"
        return plan(RouteType.STRUCTURED, StructuredIntent.CONVERSATION, hints={"meta": meta, "which": "previous"},
                    reasoning=why)
    if label == "out_of_scope":
        return plan(RouteType.UNSUPPORTED, StructuredIntent.OUT_OF_SCOPE, hints={"kind": "general"}, reasoning=why)
    if label == "documents":
        # Confirmed by meaning to be a rules/procedures question: search the
        # documents with the document-question relevance floor.
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"semantic": "documents", **cohort_hint}, reasoning=why)
    return None


_STOPWORDS = {
    "which", "who", "what", "faculty", "professor", "instructor", "work", "works",
    "working", "on", "in", "and", "when", "can", "i", "meet", "them", "is", "the",
    "a", "an", "recommend", "for", "of", "to", "with", "research", "interests",
    # Never part of a research area — these leaked into the search phrase
    # live ("NLP research who" matched nobody).
    "whose", "that", "teaching", "teaches", "soon", "available", "free",
    "someone", "somebody", "anyone", "anybody", "member", "campus", "here",
    "s", "any", "there",
}


def _extract_topic(query: str) -> str:
    """Best-effort topic phrase for faculty-matching (e.g. "NLP" from "Which
    faculty work in NLP and when can I meet them?"). Falls back to the full
    query if nothing better is found — matching against research_interests
    text is tolerant of extra words."""
    words = re.findall(r"[A-Za-z][A-Za-z.+-]*", query)
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept) if kept else query
