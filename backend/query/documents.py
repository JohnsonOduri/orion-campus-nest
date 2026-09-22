"""Document answers without an LLM or embeddings.

1. `search`: Postgres full-text search over document_chunks
   (`search_document_chunks` RPC, migration 20260922100000) — no model, no
   API key, no quota. Cohort isolation (CLAUDE.md §20) happens in SQL.
2. `best_passages`: picks the specific clauses inside the retrieved chunks
   that answer the question (chunks are ~2,200 characters; the answer is
   usually one numbered rule), so the reply can quote the rule itself.

Everything here is deterministic and grounded: passages are verbatim text
from approved documents, never paraphrased or invented.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from .types import SemanticSnippet

logger = logging.getLogger("orion.documents")

# Words students use that the documents phrase differently. Values are added
# to the search (lower weight than the student's own words when scoring).
_SYNONYMS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(curfew|in[\s-]?time|back\s+in|return|late|night|gate\s+clos\w*)\b", re.I),
     "return hostels 11:00 PM night timings roaming 9:30 main door closes"),
    (re.compile(r"\b(out[\s-]?pass|gate[\s-]?pass|leave\s+campus|leaving\s+campus|go\s+home|outing)\b", re.I),
     "outpass portal biometric leave permission weekends overnight form"),
    (re.compile(r"\b(visitors?|guests?|parents?\s+visit)\b", re.I), "guests visiting hours entrance"),
    (re.compile(r"\b(cook|cooking|kettle|heater|iron|appliances?)\b", re.I), "cooking electrical appliances heaters irons"),
    (re.compile(r"\b(counts?\s+as|definition|define|meaning|what\s+is)\b.*\bragg", re.I), "constitutes ragging following acts"),
    (re.compile(r"\b(punish\w*|penalt\w*|consequences?)\b.*\bragg|\bragg\w*\b.*\b(punish\w*|penalt\w*)", re.I),
     "punishments administrative action guilty award following namely"),
    (re.compile(r"\b(report|complain\w*|helpline|help)\b.*\bragg|\bragg\w*\b.*\b(report|complain\w*|helpline)", re.I),
     "helpline toll free distress call email"),
    (re.compile(r"\b(squad|committee|members?)\b.*\bragg|\bragg\w*\b.*\b(squad|committee|members?)\b", re.I),
     "anti ragging squad committee members office memorandum"),
    (re.compile(r"\b(cgpa|gpa|sgpa)\b", re.I), "cgpa grade point average credits weighted"),
    (re.compile(r"\bgrad(ing|es?)\b", re.I), "grade letter grade points"),
    (re.compile(r"\bdrop\w*\b", re.I), "drop courses faculty adviser approval weeks"),
    (re.compile(r"\bwithdraw\w*\b", re.I), "withdrawal withdraw semester"),
    (re.compile(r"\b(fail\w*|backlogs?|arrears?)\b", re.I), "fail F grade repeat backlog"),
    (re.compile(r"\b(graduat\w*|degree)\b", re.I), "award degree eligibility minimum credits CGPA"),
    (re.compile(r"\b(duration|how\s+long|maximum\s+time)\b", re.I), "maximum duration semesters programme"),
    (re.compile(r"\bmake[\s-]?up\b|\bmiss(ed)?\s+(the\s+)?(end[\s-]?sem\w*\s+)?exam", re.I),
     "make-up examination incomplete grade I"),
    (re.compile(r"\bcondon\w*\b", re.I), "condonation medical leave"),
    (re.compile(r"\b(below|less\s+than|short\w*|don'?t\s+meet|do\s+not\s+meet|not\s+meet)\b", re.I),
     "percentage less than penalty L grade insufficient repeat"),
    (re.compile(r"\bsummer\b", re.I), "summer term"),
    (re.compile(r"\b(dual\s+degree|b\.?tech[\s-]*ms)\b", re.I), "B.Tech-MS dual degree eligibility"),
    (re.compile(r"\btranscripts?\b", re.I), "transcript request fee academic office"),
    (re.compile(r"\bcertificates?\b", re.I), "certificate verification fee"),
]

_STOP = {
    "what", "whats", "which", "who", "whom", "when", "where", "why", "how", "is", "are", "am", "was", "were",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "do", "does", "did", "can", "could", "i",
    "me", "my", "we", "our", "you", "your", "it", "its", "this", "that", "there", "be", "if", "at", "by",
    "with", "about", "any", "should", "would", "will", "tell", "please", "rule", "rules", "regarding",
    "happen", "happens", "get", "have", "has", "from", "as", "per", "much", "many",
}


def _stem(word: str) -> str:
    w = word.lower()
    for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > 4 and w.endswith(suffix):
            return w[: -len(suffix)] + repl
    return w


def _terms(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9%]+", text.lower()) if w not in _STOP and len(w) > 1]


def expand_query(query: str) -> tuple[str, list[str]]:
    """(text to send to full-text search, extra synonym terms)."""
    extra: list[str] = []
    for pattern, words in _SYNONYMS:
        if pattern.search(query):
            extra.extend(words.split())
    return (f"{query} {' '.join(extra)}".strip(), extra)


def search(
    client: Any,
    query: str,
    cohort_family: Optional[str],
    category: Optional[str] = None,
    document_type: Optional[str] = None,
    top_k: int = 6,
) -> list[SemanticSnippet]:
    """Lexical search, preferring the source the router expects (hostel
    rules, the student's regulations, ...) but never limited to it."""
    text, _ = expand_query(query)

    def run(cat: Optional[str], dtype: Optional[str], k: int) -> list[dict]:
        res = client.rpc(
            "search_document_chunks",
            {
                "query_text": text,
                "match_count": k,
                "cohort_family": cohort_family,
                "filter_category": cat,
                "filter_document_type": dtype,
            },
        ).execute()
        return res.data or []

    rows: dict[int, dict] = {}
    if category or document_type:
        for r in run(category, document_type, 5):
            r["rank"] = float(r["rank"]) * 1.6  # the source the question is about
            rows[r["chunk_id"]] = r
    for r in run(None, None, top_k):
        rows.setdefault(r["chunk_id"], r)

    ordered = sorted(rows.values(), key=lambda r: -float(r["rank"]))[:top_k]
    for r in ordered[:3]:
        if _LIST_INTRO_RE.search(clean_text(r["content"])[-160:]):
            try:
                nxt = (client.table("document_chunks").select("content")
                       .eq("document_id", r["document_id"]).eq("chunk_index", r["chunk_index"] + 1)
                       .limit(1).execute().data or [])
            except Exception:  # noqa: BLE001 - continuation is best-effort
                nxt = []
            if nxt:
                r["content"] = f"{r['content']} {nxt[0]['content'][:1400]}"
    return [
        SemanticSnippet(
            content=r["content"],
            document_title=r["title"],
            section_title=r.get("section_title"),
            page_start=r.get("page_start"),
            page_end=r.get("page_end"),
            similarity=float(r["rank"]),
            cohort=r.get("cohort"),
            category=r.get("category"),
            document_type=r.get("document_type"),
            valid_from=str(r["valid_from"]) if r.get("valid_from") else None,
            valid_until=str(r["valid_until"]) if r.get("valid_until") else None,
        )
        for r in ordered
    ]


# A clause that only introduces what follows ("…the following punishments,
# namely;", "…the following acts: a.").
_LIST_INTRO_RE = re.compile(
    r"(namely|following(\s+\w+)?|as\s+follows|below)\s*[;:,.\-]?\s*(\(?[a-z0-9]{1,3}[.)])?\s*$|:\s*(\(?[a-z0-9]{1,3}[.)])?\s*$",
    re.IGNORECASE,
)
# Words that say nothing about WHICH rule is meant — ignored when judging
# whether a passage answers the question.
_GENERIC = {"process", "work", "come", "allow", "allowed", "possible", "way", "system", "detail", "information",
            "info", "need", "required", "require", "go", "know", "someone", "anyone", "student", "procedure",
            "policy", "can", "may", "happen", "take", "get", "give", "want", "one", "count", "mean", "exactly"}


# ------------------------------------------------------------ passages

@dataclass
class Passage:
    text: str
    document_title: str
    section_title: Optional[str]
    page: Optional[int]
    cohort: Optional[str]
    document_type: Optional[str]
    score: float


def clean_text(text: str) -> str:
    t = text.replace("\u00ad", "")  # soft hyphens
    t = re.sub(r"(\w)-\s+([a-z])", r"\1\2", t)  # "at- tendance" -> "attendance"
    t = t.replace("\uf0b7", " • ").replace("\u25cf", " • ")  # PDF bullet glyphs
    t = re.sub(r"\s+", " ", t)
    # Page furniture repeated in PDF footers/headers, and extraction debris.
    t = re.sub(r"Hostel Rules and Regulations – July 2026 Indian Institute of Information Technology Kottayam", " ", t)
    t = re.sub(r"IIIT Kottayam, Kerala IIITK/Acad/\S+(\s+-\s+\d+/\d+)?", " ", t)
    t = re.sub(r"\(cid:\d+\)", " ", t)
    t = re.sub(r"\d*\s*THE GAZETTE OF INDIA,[^\]]{0,80}\]?(\s*\d{3,4})?", " ", t)
    t = re.sub(r"(?:(?<=\s)[a-z](?=\s)\s){2,}", " ", t)  # "i i i" left by broken formulas
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# Split before numbered clauses ("R.6.1", "2.1 ", "3. Leave and"), bullets.
_UNIT_SPLIT_RE = re.compile(
    r"(?=\bR\.\d+(?:\.\d+)+\s)|(?<=\s)(?=\d{1,2}\.\d{1,2}(?:\.\d{1,2})?\s+(?!AM\b|PM\b)[A-Z])|"
    r"(?<=[.:;]\s)(?=\d{1,2}\.\s+[A-Z][a-z])|(?<=[;:.]\s)(?=[a-z]\)\s)"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z(•])")


def _units(text: str) -> list[str]:
    units: list[str] = []
    for part in _UNIT_SPLIT_RE.split(clean_text(text)):
        part = part.strip(" •")
        if not part:
            continue
        if len(part) <= 420:
            units.append(part)
            continue
        buf = ""
        for sentence in _SENTENCE_SPLIT_RE.split(part):
            if buf and len(buf) + len(sentence) > 320:
                units.append(buf.strip())
                buf = ""
            buf += " " + sentence
        if buf.strip():
            units.append(buf.strip())
    return units


def rule_id(text: str) -> Optional[str]:
    """"R.5.1" / "2.2" / "16." at the start of a clause, for citations."""
    m = re.match(r"\s*(R\.\d+(?:\.\d+)*|\d{1,2}(?:\.\d{1,2})+|\d{1,2}\.)\s", text)
    return m.group(1).rstrip(".") if m else None


def best_passages(query: str, snippets: list[SemanticSnippet], max_units: int = 2) -> tuple[list[Passage], float]:
    """Pick the clause(s) that answer `query`. Returns (passages from the
    best document, confidence 0..1 = share of the question's key terms the
    chosen text covers)."""
    if not snippets:
        return [], 0.0
    _, extra = expand_query(query)
    q_seq = _terms(query)
    q_terms = set(q_seq)
    syn_terms = set(_terms(" ".join(extra))) - q_terms
    if not q_terms:
        return [], 0.0
    q_bigrams = {(a, b) for a, b in zip(q_seq, q_seq[1:]) if a != b}

    candidates: list[tuple[int, int, str]] = []  # (snippet index, unit index, text)
    for si, snip in enumerate(snippets):
        for ui, unit in enumerate(_units(snip.content)):
            candidates.append((si, ui, unit))
    if not candidates:
        return [], 0.0

    unit_seqs = [_terms(u) for _, _, u in candidates]
    unit_terms = [set(seq) for seq in unit_seqs]
    n = len(candidates)
    df: dict[str, int] = {}
    for ts in unit_terms:
        for t in ts:
            df[t] = df.get(t, 0) + 1

    def idf(t: str) -> float:
        return math.log(1 + n / (1 + df.get(t, 0)))

    max_rank = max(s.similarity for s in snippets) or 1.0
    scored: list[tuple[float, int]] = []
    for idx, ((si, _ui, unit), ts, seq) in enumerate(zip(candidates, unit_terms, unit_seqs)):
        s = sum(idf(t) for t in q_terms & ts) + 0.5 * sum(idf(t) for t in syn_terms & ts)
        bigrams = set(zip(seq, seq[1:]))
        s += 0.6 * sum(idf(a) + idf(b) for a, b in q_bigrams & bigrams)  # the student's exact phrase
        s *= 0.75 + 0.5 * (snippets[si].similarity / max_rank)
        if len(unit) < 40:
            s *= 0.4  # a bare heading
        if re.search(r"\d", unit) and re.search(r"\d|%|\bpm\b|\bam\b|\bhow\s+(many|much|long)\b|\bwhen\b|\btime\b|\bfee\b", query, re.I):
            s *= 1.15
        scored.append((s, idx))
    scored.sort(reverse=True)
    best_score, best_idx = scored[0]
    if best_score <= 0:
        return [], 0.0

    best_si, best_ui, best_text = candidates[best_idx]
    chosen = [best_idx]
    by_pos = {(c[0], c[1]): i for i, c in enumerate(candidates)}
    # A heading, or a clause introducing a list ("namely;", ":"), is only
    # useful with what follows it.
    follow = len(best_text) < 60 or bool(_LIST_INTRO_RE.search(best_text)) or bool(
        re.search(r"(namely|following\s+\w+|as\s+follows)\s*[;:]", best_text, re.I))
    if follow:
        for k in range(1, 4):
            nxt = by_pos.get((best_si, best_ui + k))
            if nxt is None:
                break
            chosen.append(nxt)
    else:
        for s_, i in scored[1:]:
            if len(chosen) >= max_units:
                break
            if candidates[i][0] == best_si and s_ >= 0.6 * best_score:
                chosen.append(i)
    chosen.sort(key=lambda i: candidates[i][1])

    covered = set().union(*(unit_terms[i] for i in chosen))
    # A word that appears nowhere in the retrieved text but was bridged by a
    # synonym ("curfew" -> the 11:00 PM return rule) shouldn't count against
    # the answer; without synonyms it still does.
    counted = {t for t in q_terms if (df.get(t, 0) > 0 or not extra) and t not in _GENERIC}
    for pattern, words in _SYNONYMS:
        m = pattern.search(query)
        if m and set(_terms(words)) & covered:
            covered = covered | set(_terms(m.group(0)))
    weight = sum(idf(t) for t in counted)
    confidence = sum(idf(t) for t in counted & covered) / weight if weight else (0.6 if syn_terms & covered else 0.0)

    snip = snippets[best_si]
    wanted = q_terms | syn_terms

    def trim_lead(unit: str) -> str:
        """Drop leading sentences that mention nothing the student asked about."""
        sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", unit)
        while len(sentences) > 1 and not (set(_terms(sentences[0])) & wanted) and not rule_id(sentences[0]):
            sentences.pop(0)
        return " ".join(sentences)

    text = " ".join(trim_lead(candidates[i][2]) if n_ == 0 else candidates[i][2] for n_, i in enumerate(chosen))
    if len(text) > 900:
        text = text[:900].rsplit(" ", 1)[0] + "…"
    passage = Passage(
        text=text,
        document_title=snip.document_title,
        section_title=rule_id(text) or (None if rule_id(candidates[chosen[0]][2]) else snip.section_title),
        page=snip.page_start,
        cohort=snip.cohort,
        document_type=snip.document_type,
        score=best_score,
    )
    return [passage], round(confidence, 3)


# ------------------------------------------------------------ overviews
# "What are the hostel rules?" is too broad for one clause: answer with the
# few rules students ask about most, each quoted from the document.
OVERVIEW_TOPICS: dict[str, list[tuple[str, str, Optional[str]]]] = {
    "hostel": [
        ("Timings", "hostel timings main door closes gate in", "hostel"),
        ("Leaving campus", "outpass portal leave campus permission", "hostel"),
        ("Guests", "guests visiting hours entrance", "hostel"),
        ("Cooking and appliances", "cooking electrical appliances rooms", "hostel"),
        ("Silence hours", "silence hours noise", "hostel"),
    ],
    "anti-ragging": [
        ("What counts as ragging", "what constitutes ragging following acts", "anti-ragging"),
        ("Punishments", "ragging punishments administrative action guilty namely", "anti-ragging"),
        ("Getting help", "ragging helpline toll free distress", "anti-ragging"),
    ],
}


def _first_sentences(text: str, limit: int = 260) -> str:
    out = ""
    for sentence in re.split(r"(?<=[.;])\s+(?=[A-Z(])", text):
        if out and len(out) + len(sentence) > limit:
            break
        out = f"{out} {sentence}".strip()
    return out if len(out) <= limit + 80 else out[:limit].rsplit(" ", 1)[0] + "…"


def overview(client: Any, topic: str, cohort_family: Optional[str]) -> list[tuple[str, Passage]]:
    items: list[tuple[str, Passage]] = []
    for label, sub_query, category in OVERVIEW_TOPICS.get(topic, []):
        passages, confidence = best_passages(sub_query, search(client, sub_query, cohort_family, category=category, top_k=4))
        if passages and confidence >= 0.34:
            p = passages[0]
            p.text = _first_sentences(re.sub(r"^\s*(R\.\d+(\.\d+)*|\d{1,2}(\.\d{1,2})*\.?)\s+", "", p.text), 360)
            items.append((label, p))
    return items
