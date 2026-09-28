"""Campus vocabulary: spelling correction and concept normalisation.

Two jobs, both pure (no I/O, no model, no quota):

1. `correct_spelling` fixes typos in the words ORION actually needs to
   understand — "tommorow", "teching", "facluty", "hostl", "lerning" — by
   snapping them to the closest word in the campus vocabulary. It never
   touches names (capitalised words mid-sentence), course codes, numbers, or
   real English words: a real word near a campus term ("hostile" / "hostel")
   is protected by `data/protected_words.txt`, generated from the system
   dictionary by `scripts/build_lexicon_data.py` so the result is identical on
   every machine. Names are matched fuzzily later, against the faculty
   directory itself (campus.link_entities / retrieval.fuzzy_faculty_names).

2. `concept_tokens` maps the many ways students say the same thing onto one
   token — teachers / professors / lecturers / teaching staff → `@faculty`;
   what's cooking / serving / dining hall / meal choices → `@food` — so the
   intent classifier (intents.py) compares meanings, not surface words.

Edit distance is optimal-string-alignment with a half-cost transposition:
swapped letters ("Jhon", "facluty", "Chirstina") are the most common typo and
should count as closer than two unrelated substitutions.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

# --------------------------------------------------------------- vocabulary

_DOMAIN_TEXT = """
timetable schedule class classes lecture lectures lab labs practical practicals tutorial tutorials period periods
slot slots free today tomorrow yesterday tonight morning afternoon evening week weekly weekend monday tuesday
wednesday thursday friday saturday sunday next first last upcoming future past previous
faculty faculties professor professors teacher teachers lecturer lecturers instructor instructors staff teaching
academic academics administrative administration adjunct assistant associate visiting department departments
head heads heading headed hod hods dean deans registrar director warden wardens hostel hostels chief manager
security nurse doctor medical psychologist counsellor counselor officer member members people employees
mess menu food breakfast lunch dinner snacks snack canteen cafeteria dining meal meals serving served dishes dish
cooking chicken paneer mutton fish egg eggs biryani vegetarian veg rice roti chapati curry dessert sweet payasam
exam exams examination examinations semester midsem endsem results result grade grades marks attendance
regulation regulations rules rule policy policies curriculum syllabus credits credit prerequisite prerequisites
course courses subject subjects elective electives registration register fee fees deadline deadlines calendar
holiday holidays vacation event events sports meet meeting committee review project projects internship
placement placements transcript transcripts certificate certificates verification procedure procedures process
ragging antiragging discipline disciplinary conduct library curfew outpass visitors guests gate
research researches researching interest interests expertise specialise specialize specialization machine
learning natural language processing vision network networks wireless electronics electrical science
engineering mathematics humanities cyber data artificial intelligence
announcement announcements notice notices circular circulars news update updates
email office cabin phone contact number location room building block floor
happening happened happens planned choices source sources document documents question questions
welfare affairs alumni international industrial relations continuing education career development
condonation withdrawal withdraw summer backlog repeat makeup supplementary eligibility graduation degree
honours minor dual cgpa sgpa percentage minimum maximum required requirement requirements
"""

# Words from the live course catalogue (courses.course_name, 2026-09-28).
_COURSE_TEXT = """
accounting algorithms analog analysis analytics applications architecture artificial bioinformatics chain circuits
coding cognitive communication computation computer computing crime cryptography data database design devices
digital distributed electronics engineering engineers financial fundamentals human information integrated
intelligence internet introduction language large linear management mathematical microcontrollers microprocessors
microwave motivations natural network number operations optimization parallel physical practices principles
probability process processes processing quantum random resource scale science security signal soft software solid
speech state statistics streaming structures supply system systems techniques theory things training typologies
vision vlsi workshop
"""

DOMAIN_WORDS: frozenset[str] = frozenset(re.findall(r"[a-z]+", _DOMAIN_TEXT + _COURSE_TEXT))

# Chat shorthand that is not a typo of anything, but means something.
SHORTHAND = {
    "wat": "what", "wht": "what", "wot": "what", "r": "are", "u": "you", "ur": "your", "pls": "please",
    "plz": "please", "tmrw": "tomorrow", "tmr": "tomorrow", "tmrrw": "tomorrow", "tom": "tomorrow",
    "2day": "today", "2moro": "tomorrow", "2morrow": "tomorrow", "yday": "yesterday", "wk": "week",
    "whos": "who is", "whats": "what is", "wheres": "where is", "whens": "when is", "hows": "how is",
    "dept": "department", "depts": "departments", "prof": "professor", "profs": "professors",
    "sem": "semester", "sems": "semesters", "exm": "exam", "hstl": "hostel", "clg": "college",
    "abt": "about", "b4": "before", "info": "information", "tt": "timetable", "nxt": "next",
    "wen": "when", "whr": "where", "frm": "from", "lec": "lecture", "lecs": "lectures", "thru": "through",
    "hed": "head", "hal": "hall", "incharge": "in charge", "datastructures": "data structures",
}

# Modern/chat words the 1934-era system dictionary doesn't know, plus the
# question words that must never be "corrected".
_COMMON_EXTRA = {
    "email", "emails", "online", "website", "portal", "okay", "cant", "dont", "wont", "isnt", "arent", "didnt",
    "doesnt", "gonna", "wanna", "gotta", "whats", "thats", "theres", "lets", "youre", "their", "there", "where",
    "which", "whose", "what", "when", "have", "having", "does", "doing", "done", "will", "would", "could",
    "should", "about", "with", "from", "that", "this", "these", "those", "them", "they", "your", "yours",
    "here", "also", "only", "just", "some", "many", "much", "more", "most", "very", "into", "onto", "been",
    "were", "want", "need", "know", "tell", "show", "give", "list", "find", "search", "named", "called",
    "iiit", "kottayam", "btech", "mtech", "phd", "ms", "hod", "hods", "cse", "ece", "csy", "aids",
}

# Hostel names (hostel_wardens.hall_name, Wardens Team July 2026).
_HALL_WORDS = {"anamudi", "sahyadri", "manimala", "meenachil", "chitar", "agasthya", "coptyre", "nila",
               "kalapurackal", "maryland", "panackal", "sunshine", "ktm", "anna"}

_DATA_DIR = Path(__file__).resolve().parent / "data"


@lru_cache(maxsize=1)
def protected_words() -> frozenset[str]:
    """Real English words that sit within edit distance 2 of a campus word.
    Without this list, "hostile" would be "corrected" to "hostel"."""
    words: list[str] = []
    # protected_words.txt: English neighbours of campus words.
    # name_words.txt: every word of every name in the institute directory —
    # "Manu sir email" must not become "menu sir email".
    for name in ("protected_words.txt", "name_words.txt"):
        try:
            words += (_DATA_DIR / name).read_text().split()
        except OSError:
            pass
    return frozenset(words) | _COMMON_EXTRA | _HALL_WORDS


# --------------------------------------------------------------- distance

def edit_distance(a: str, b: str) -> float:
    """Optimal string alignment distance; adjacent transposition costs 0.5."""
    if a == b:
        return 0.0
    la, lb = len(a), len(b)
    if not la or not lb:
        return float(max(la, lb))
    prev2: list[float] = []
    prev = [float(j) for j in range(lb + 1)]
    for i in range(1, la + 1):
        cur = [float(i)] + [0.0] * lb
        for j in range(1, lb + 1):
            cost = 0.0 if a[i - 1] == b[j - 1] else 1.0
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 0.5)
        prev2, prev = prev, cur
    return prev[lb]


def similarity(a: str, b: str) -> float:
    """1.0 = identical; "jhon"/"john" = 0.875; "hostl"/"hostel" = 0.83."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0.0
    return 1.0 - edit_distance(a, b) / max(len(a), len(b))


def _allowed_distance(length: int) -> float:
    if length <= 3:
        return 0.0
    if length <= 5:
        return 1.0
    return 2.0


def _is_known(w: str) -> bool:
    """A real word, including inflections of one. The dictionary stores
    base forms ("hold"), so "holds" must be recognised through its stem —
    otherwise it gets "corrected" to "hods" (found in testing)."""
    known = protected_words()
    if w in DOMAIN_WORDS or w in known:
        return True
    stems = []
    if w.endswith("ies"):
        stems.append(w[:-3] + "y")
    if w.endswith("es"):
        stems.append(w[:-2])
    if w.endswith("s") and not w.endswith("ss"):
        stems.append(w[:-1])
    if w.endswith("ed"):
        stems += [w[:-2], w[:-1]]
    if w.endswith("ing"):
        stems += [w[:-3], w[:-3] + "e"]
    if w.endswith("er") or w.endswith("ly"):
        stems.append(w[:-2])
    return any(s in known or s in DOMAIN_WORDS for s in stems if len(s) >= 3)


@lru_cache(maxsize=4096)
def correct_word(word: str) -> str | None:
    """The campus word `word` is a typo of, or None. Unique best only: a tie
    between two candidates is a guess, and ORION doesn't guess — unless one
    of them clearly shares more of the word's letters in order ("registar":
    registrar 0.94 vs register 0.88)."""
    w = word.lower()
    if not w.isalpha() or _is_known(w):
        return None
    limit = _allowed_distance(len(w))
    if not limit:
        return None
    best_d, bests = limit + 1, []
    for cand in DOMAIN_WORDS:
        if abs(len(cand) - len(w)) > limit:
            continue
        d = edit_distance(w, cand)
        # A different first letter is a much rarer typo; only accept it for
        # a single edit ("ecture" -> "lecture" stays out, "eaxm" is fine).
        if cand[0] != w[0] and d > 0.5:
            continue
        if d < best_d:
            best_d, bests = d, [cand]
        elif d == best_d:
            bests.append(cand)
    if not bests or best_d > limit:
        return None
    if len(bests) == 1:
        return bests[0]
    ranked = sorted(((SequenceMatcher(None, w, c).ratio(), c) for c in bests), reverse=True)
    return ranked[0][1] if ranked[0][0] - ranked[1][0] >= 0.04 else None


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z']*|\d+[a-z]*|\S")


def correct_spelling(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(corrected text, [(original, replacement), ...]).

    Capitalised words after the first are left alone — they're usually
    names, and names are resolved against the directory, not a dictionary.
    Course codes ("ICS 213") and anything with a digit are never touched."""
    if not text:
        return text, []
    out: list[str] = []
    changes: list[tuple[str, str]] = []
    pos = 0
    first_word = True
    for m in re.finditer(r"[A-Za-z][A-Za-z']*|\d\w*", text):
        out.append(text[pos:m.start()])
        token = m.group(0)
        pos = m.end()
        bare = token.rstrip("'")
        lower = bare.lower()
        replacement = None
        if lower in SHORTHAND and (bare.islower() or first_word):
            replacement = SHORTHAND[lower]
        elif bare.isalpha() and (bare.islower() or first_word) and not bare.isupper():
            fixed = correct_word(lower)
            if fixed:
                replacement = fixed.capitalize() if bare[0].isupper() else fixed
        if replacement and replacement.lower() != lower:
            changes.append((token, replacement))
            out.append(replacement)
        else:
            out.append(token)
        if token[:1].isalpha():
            first_word = False
    out.append(text[pos:])
    return "".join(out), changes


# --------------------------------------------------------------- concepts

# (phrase pattern, concept token). Order matters: longer phrases first, so
# "assistant professor" becomes @designation before "professor" becomes
# @faculty.
CONCEPTS: list[tuple[re.Pattern[str], str]] = [(re.compile(p, re.I), tag) for p, tag in [
    (r"\b(assistant|associate|adjunct|visiting|guest)\s+(professors?|profs?|faculty|lecturers?)\b", "@designation"),
    (r"\blab(oratory)?\s+(faculty|teaching\s+staff|staff|instructors?|teachers?)\b", "@designation"),
    (r"\badjunct\b", "@designation"),
    (r"\b(teaching|academic)\s+(staff|team|employees|members|people)\b", "@faculty"),
    (r"\bfaculty\s+(members?|people|list|directory)\b", "@faculty"),
    (r"\b(teachers?|professors?|profs?|lecturers?|instructors?|faculty|faculties|tutors?)\b", "@faculty"),
    (r"\badministrat\w*\b|\badmin\b", "@admin"),
    (r"\b(hods?|h\.o\.d)\b|\bheads?\s+of\s+(the\s+)?(department|dept)s?\b", "@head"),
    (r"\b(heads?|heading|headed|in[\s-]charge|leads?|leading|chairs?)\b", "@head"),
    (r"\b(handles?|handling|responsible\s+for|looks?\s+after|manages?|managing|oversees?|in\s+charge\s+of)\b", "@handle"),
    (r"\b(students?\s+welfare|academic\s+affairs|hostel\s+affairs|alumni|international\s+affairs|"
     r"industrial\s+relations|continuing\s+education|career\s+development|placements?)\b", "@office_area"),
    (r"\b(chief\s+warden|assistant\s+wardens?|wardens?|hostel\s+manager|security\s+officer)\b", "@warden"),
    (r"\b(dean|registrar|director|medical\s+officer|doctor|physician|counsell?or|psychologist|nurse|"
     r"vigilance\s+officer|cvo|nodal\s+officer|physical\s+education)s?\b", "@role"),
    (r"\b(cgpa|sgpa|gpa|grading|grade\s+points?|credits?|summer\s+term|drop(ping)?\s+(a\s+)?courses?|"
     r"withdraw\w*|fail\w*|backlogs?|malpractice|dual\s+degree|condonation|attendance|make[\s-]?up|"
     r"graduat\w*|degree)\b", "@acad"),
    (r"\b(cse|ece|computer\s+science(\s+and\s+engineering)?|electronics(\s+(and|&)\s+communication)?|"
     r"electrical(\s+engineering)?|cyber\s*security|humanities|mathematics|computational\s+science)\b", "@dept"),
    (r"\b(department|dept)s?\b", "@dept"),
    (r"\bwhat'?s\s+cooking\b|\bcooking\s+(today|tonight|tomorrow)\b", "@food"),
    (r"\b(what\s+are\s+we\s+having|we'?re\s+having|to\s+eat|eat(ing)?|serv(e|es|ed|ing)|dish(es)?|meals?|"
     r"dining(\s+hall)?|mess|menu|food|canteen|cafeteria)\b", "@food"),
    (r"\b(breakfast|lunch|dinner|snacks?|supper)\b", "@meal"),
    (r"\b(chicken|paneer|mutton|beef|fish|eggs?|biryani|non[\s-]?veg|veg(etarian)?|dessert|sweet|payasam|"
     r"ice\s*cream|dosa|idli|poori|puri|chapati|roti|pulao|fried\s+rice)\b", "@dish"),
    (r"\b(mid|end)[\s-]?sem(ester)?\s+(exams?|examinations?)\b|\b(mid|end)[\s-]?sems?\b", "@exam"),
    (r"\b(exams?|examinations?|tests?|finals?|quiz(zes)?)\b", "@exam"),
    (r"\b(events?|happening|happened|happens|occasions?|fest|functions?|sports\s+meet|celebrations?)\b", "@event"),
    (r"\b(academic\s+calendar|calendar|deadlines?|holidays?|vacations?|important\s+dates)\b", "@calendar"),
    (r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|"
     r"nov(ember)?|dec(ember)?)\b\.?\s*\d{1,2}\b|\b\d{1,2}(st|nd|rd|th)?\s+(of\s+)?(jan|feb|mar|apr|may|jun|"
     r"jul|aug|sep|oct|nov|dec)[a-z]*\b|\b\d{4}-\d{2}-\d{2}\b", "@date"),
    (r"\b(how\s+many\s+days|days\s+(between|before|after|until|till|left)|gap\s+between|difference\s+between)\b", "@days_between"),
    (r"\b[a-z]{3}\s?\d{3}\b|\b(courses?|subjects?|papers?|dbms|algorithms|database|data\s+structures|"
     r"theory\s+of\s+computation|workshop|microprocessors?|probability|statistics|signals?\s+and\s+systems|"
     r"operating\s+systems?|compilers?)\b", "@course"),
    (r"\b(free|gaps?|breaks?|idle|off)\b", "@free"),
    (r"\b(timetable|time\s+table|classes|class|lectures?|periods?|schedule)\b", "@class"),
    (r"\b(today|tonight|now)\b", "@today"),
    (r"\b(tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "@day"),
    (r"\b(this\s+week|weekly|next\s+week)\b", "@week"),
    (r"\b(next|upcoming|coming\s+up|future|after)\b", "@next"),
    (r"\b(rules?|regulations?|polic(y|ies)|guidelines?|norms?|allowed|permitted|penalt(y|ies)|fines?|"
     r"procedures?|requirements?|eligib\w*|conduct|disciplin\w*)\b", "@rule"),
    (r"\b(hostels?|curfew|out[\s-]?pass|gate\s+pass|visitors?|guests?)\b", "@hostel"),
    (r"\bragg(ing|ed)?\b|\banti[\s-]?ragging\b", "@ragging"),
    (r"\b(research\w*|speciali[sz]\w*|expertise|expert|interests?|(works?|working)\s+(on|in)\s+(?!the\s+|this\s+|here))\b", "@research"),
    (r"\b(e-?mail|phone|office|cabin|contact|number|position|designation)\b", "@contact"),
    (r"\b(dr|prof|professor|mr|mrs|ms|sir|madam|ma'?am)\b\.?", "@title"),
    (r"\b(named|called|by\s+the\s+name)\b", "@named"),
    (r"\b(sources?|references?|cite|citation|where\s+did\s+you\s+get|which\s+document|where\s+is\s+(this|that)\s+from)\b", "@source"),
    (r"\b(first|previous|last|earlier)\s+(question|thing|message)\b|\bwhat\s+did\s+i\s+(ask|say)\b", "@history"),
    (r"\b(announcements?|notices?|circulars?|news|updates?)\b", "@notice"),
    (r"\b(how\s+many|number\s+of|count)\b", "@count"),
    (r"\b(my|mine|i\s+am|am\s+i)\b", "@me"),
]]

_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "am", "be", "been", "do", "does", "did", "of", "in", "on", "at",
    "to", "for", "and", "or", "with", "by", "about", "any", "some", "all", "there", "here", "this", "that", "these",
    "those", "it", "its", "me", "i", "you", "we", "they", "them", "can", "could", "would", "should", "will", "please",
    "tell", "show", "give", "list", "know", "want", "need", "also", "which", "what", "who", "whom", "when", "where",
    "how", "why", "s", "have", "has", "had", "get", "got", "one", "ones",
}
# Question words carry intent ("who" -> a person, "when" -> a date) — kept as
# their own features rather than dropped with the stop words.
_KEEP_QWORDS = {"who": "?who", "when": "?when", "where": "?where", "how": "?how", "which": "?which"}


def _stem(w: str) -> str:
    for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)] + repl
    return w


def concept_tokens(text: str) -> list[str]:
    """Concept tokens + remaining content-word stems, in order."""
    t = f" {text.lower()} "
    tags: list[tuple[int, str]] = []
    for pattern, tag in CONCEPTS:
        for m in pattern.finditer(t):
            tags.append((m.start(), tag))
        t = pattern.sub(lambda m: " " * len(m.group(0)), t)
    words = [(m.start(), m.group(0)) for m in re.finditer(r"[a-z]+", t)]
    out: list[tuple[int, str]] = list(tags)
    for pos, w in words:
        if w in _KEEP_QWORDS:
            out.append((pos, _KEEP_QWORDS[w]))
        elif w not in _STOP and len(w) > 1:
            out.append((pos, _stem(w)))
    # Question words were removed by the concept pass only if part of a
    # phrase; restore their order-independent presence from the raw text.
    low = text.lower()
    for qw, tag in _KEEP_QWORDS.items():
        if re.search(rf"\b{qw}\b", low) and not any(tok == tag for _, tok in out):
            out.append((0, tag))
    out.sort(key=lambda x: x[0])
    return [tok for _, tok in out]
