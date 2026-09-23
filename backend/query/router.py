"""Deterministic query classification (README §8, AGENTS.md §4).

No LLM call here by design — this stage is independently testable and the
router must "not blindly send every question to vector search" (AGENTS.md
§4). Rule-based intent classification is cheap, auditable, and — unlike an
LLM classifier — never costs a token or a quota unit. An LLM-backed
classifier can be added later as a fallback for genuinely ambiguous queries
without changing this module's contract (it still returns a QueryPlan).
"""

from __future__ import annotations

import random
import re
from datetime import datetime

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
    r"\bwho\s+teaches\b|\bfaculty\s+(for|teaching)\b|\binstructor\s+for\b", re.IGNORECASE
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
_FACULTY_ATTR_WORDS = r"email|e-mail|office\s+hours|office\s+location|office|cabin|room"
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
_MESS_WORD_RE = re.compile(
    r"\b(mess|canteen|cafeteria|food|menu|breakfast|lunch|dinner|snacks?)\b", re.IGNORECASE
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
    r"\bhostel\b[^?]*\b(contact|phone|number|in[\s-]?charge|call)\b",
    re.IGNORECASE,
)

# Institutional roles held in faculty.designation.
_ROLE_TERMS: list[tuple[str, str]] = [
    (r"\b(hod|h\.o\.d|head\s+of\s+(the\s+)?(department|dept))\b", "hod"),
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
_MY_TIMETABLE_CONTEXT_RE = re.compile(
    r"\b(today|tomorrow|tonight|my\s+(first|last|next)\s+class|right\s+now)\b", re.IGNORECASE
)

_MY_COURSES_RE = re.compile(
    r"\b(my|i)\b[^?]*\b(courses|subjects|papers)\b|\bwhat\s+(courses|subjects)\s+(am\s+i|do\s+i)\b",
    re.IGNORECASE,
)
_FREE_TIME_RE = re.compile(
    r"\bwhen\s+am\s+i\s+free\b|\b(free\s+(time|slots?|periods?)|gaps?\s+between|breaks?\s+between)\b|"
    r"\bam\s+i\s+free\b",
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
    r"\s+(?:in|on|with|about|for)?\s*|\b(?:recommend|suggest)\w*\s+(?:a\s+|some\s+)?(?:faculty|professor|guide|mentor|supervisor)\w*\s+(?:member\s+)?(?:for|in|on)\s+)"
    r"(?P<topic>[a-z0-9][a-z0-9 ,&/+\-]{1,80})",
    re.IGNORECASE,
)
_RESEARCH_TRIGGER_RE = re.compile(
    r"\b(who|which|any|anyone|anybody|faculty|professors?|recommend|suggest|guide|supervisor|mentor)\b",
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
    r"summer\s+term|registration\s+requirement|continuation|debarred|detained|eligib\w*|end[\s-]?sem\w*\s+exam\w*\s+eligib\w*)\b",
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
    if _YESTERDAY_RE.search(q):
        return "yesterday"
    if _TOMORROW_RE.search(q):
        return "tomorrow"
    weekday_m = _WEEKDAY_RE.search(q)
    return weekday_m.group(1).capitalize() if weekday_m else None


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


def _research_topic(q: str) -> str | None:
    m = _RESEARCH_RE.search(q)
    if not m:
        return None
    topic = m.group("topic")
    topic = re.split(r"\s+(?:and|&)\s+(?:when|where|how|can|could)\b|[?.!]", topic, maxsplit=1)[0]
    topic = re.sub(r"\b(research|researches|area|areas|field|fields|topics?|domain)\s*$", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"^(the|a|an)\s+", "", topic.strip(), flags=re.IGNORECASE).strip(" ,")
    return topic or None


def _role_key(q: str) -> str | None:
    for pattern, key in _ROLE_TERMS:
        if re.search(pattern, q, re.IGNORECASE):
            return key
    return None


def classify(query: str) -> QueryPlan:
    """Classify a raw user query into a QueryPlan. Pure function, no I/O."""
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

    course_code = _course_code(q)
    timed = bool(_TIMING_WORD_RE.search(q))

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
    if _MESS_WORD_RE.search(q):
        meal_m = _MEAL_RE.search(q)
        meal = None
        if meal_m:
            raw_meal = meal_m.group(1).lower()
            meal = "snacks" if raw_meal.startswith("snack") else raw_meal
        if _WEEK_WORD_RE.search(q):
            return plan(RouteType.STRUCTURED, StructuredIntent.MESS_WEEK, meal=meal,
                        reasoning="matched mess/food + week pattern -> mess_week (live mess_menus)")
        day_ref = _day_reference(q)
        if day_ref:
            return plan(RouteType.STRUCTURED, StructuredIntent.MESS_ON_DAY, topic_text=day_ref, meal=meal,
                        reasoning=f"matched mess/food + day reference ({day_ref}) -> mess_on_day (live mess_menus)")
        return plan(RouteType.STRUCTURED, StructuredIntent.MESS_TODAY, meal=meal,
                    reasoning="matched mess/food pattern -> mess_today (live mess_menus)")

    # --- my courses / free time / classroom -----------------------------------------
    if _MY_COURSES_RE.search(q) and not course_code and not _WHO_TEACHES_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.MY_COURSES,
                    reasoning="asks for the caller's courses -> distinct courses in their live timetable")
    if _FREE_TIME_RE.search(q):
        return plan(RouteType.STRUCTURED, StructuredIntent.FREE_TIME, topic_text=_day_reference(q) or "today",
                    reasoning="free time -> gaps in the caller's day timetable")
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
                    reasoning="matched today-timetable pattern -> orion_day_timetable")
    day_ref = _day_reference(q)
    if day_ref and (_TIMETABLE_WORD_RE.search(q) or _DID_I_HAVE_RE.search(q) or _LAB_RE.search(q)):
        return plan(RouteType.STRUCTURED, StructuredIntent.DAY_OF_WEEK_TIMETABLE, topic_text=day_ref, hints=hints,
                    reasoning=f"matched a day reference ({day_ref}) + class/timetable word -> orion_day_timetable for that date")
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

    # --- nothing specific matched --------------------------------------------------
    # A real question still gets a real attempt: the service first tries to
    # recognise a course or faculty name in it, then searches the documents.
    # Statements and gibberish stay UNSUPPORTED (nothing to search for).
    if _looks_like_question(q) and len(_WORD_RE.findall(q)) >= 2:
        return plan(RouteType.SEMANTIC, topic_text=q, hints={"fallback": "yes", **cohort_hint},
                    reasoning="no specific pattern; question-shaped -> entity linking, then document search")

    return plan(RouteType.UNSUPPORTED,
                reasoning="no structured/semantic/hybrid pattern matched — ambiguous or out of scope")


_STOPWORDS = {
    "which", "who", "what", "faculty", "professor", "instructor", "work", "works",
    "working", "on", "in", "and", "when", "can", "i", "meet", "them", "is", "the",
    "a", "an", "recommend", "for", "of", "to", "with", "research", "interests",
}


def _extract_topic(query: str) -> str:
    """Best-effort topic phrase for faculty-matching (e.g. "NLP" from "Which
    faculty work in NLP and when can I meet them?"). Falls back to the full
    query if nothing better is found — matching against research_interests
    text is tolerant of extra words."""
    words = re.findall(r"[A-Za-z][A-Za-z.+-]*", query)
    kept = [w for w in words if w.lower() not in _STOPWORDS]
    return " ".join(kept) if kept else query
