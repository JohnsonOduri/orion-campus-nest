"""Document answers, grounded in approved documents.

1. `search`: hybrid retrieval over document_chunks — Postgres full-text
   search (`search_document_chunks`, migration 20260922100000; no model, no
   quota) fused with semantic search over the Gemini vectors
   (`search_document_chunks_semantic`, migration 20260928120000), so a
   question is matched by meaning as well as by shared words ("examination
   hall rules" should not match a textbook by Prentice Hall). Cohort
   isolation (CLAUDE.md §20) happens in SQL, identically, in both. Vector
   search is optional: with no Gemini key, a quota error (circuit breaker)
   or ORION_VECTOR_SEARCH=off, full-text search answers on its own.
2. `best_passages`: picks the specific clauses inside the retrieved chunks
   that answer the question (chunks are ~2,200 characters; the answer is
   usually one numbered rule), so the reply can quote the rule itself.

Everything here is deterministic and grounded: passages are verbatim text
from approved documents, never paraphrased or invented.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

from . import embeddings
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
    (re.compile(r"\b(grading|grade\s+points?|grad(e|ing)\s+(system|scale)|letter\s+grades?)\b", re.I), "grade letter grade points"),
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
    (re.compile(r"\b(requirements?|required|need\s+to|have\s+to|minimum|at\s+least)\b", re.I), "minimum should must"),
    (re.compile(r"\b(dual\s+degree|b\.?tech[\s-]*ms)\b", re.I), "B.Tech-MS dual degree eligibility"),
    (re.compile(r"\bexam(ination)?\s+hall|\bexam(ination)?\s+(rules|conduct)|\bmalpractice|\bunfair\s+means|\binvigilat", re.I),
     "examination seating invigilator answer booklet malpractice hall ticket ID card"),
    (re.compile(r"\bbtp\b|\bb\.?\s?tech\s+project|\bmajor\s+project|\bproject\s+(rules|work|evaluation|guidelines)", re.I),
     "project B.Tech project BTP evaluation review credits"),
    (re.compile(r"\bdisciplin\w*|\bmisconduct|\bcode\s+of\s+conduct", re.I),
     "conduct discipline disciplinary code of conduct DWC action"),
    (re.compile(r"\btranscripts?\b", re.I), "transcript request fee academic office"),
    (re.compile(r"\bcertificates?\b", re.I), "certificate verification fee"),
]

_STOP = {
    "what", "whats", "which", "who", "whom", "when", "where", "why", "how", "is", "are", "am", "was", "were",
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "do", "does", "did", "can", "could", "i",
    "me", "my", "we", "our", "you", "your", "it", "its", "this", "that", "there", "be", "if", "at", "by",
    "with", "about", "any", "should", "would", "will", "tell", "please", "rule", "rules", "regarding",
    "happen", "happens", "get", "have", "has", "from", "as", "per", "much", "many",
    # Describe the kind of question, not its topic (the synonym table maps
    # them to what documents actually say: "minimum", "should", "must").
    "requirement", "requirements", "required",
    # "an attendance policy", "the hostel regulations": the kind of text
    # wanted, not its subject — like "rule"/"rules" above.
    "policy", "policies", "regulation", "regulations", "guideline", "guidelines", "say", "says",
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


# ------------------------------------------------------------ semantic side

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="orion-docsearch")
# embed (3 s timeout) + one vector query; past this, answer from full text.
_VECTOR_WAIT_S = 4.5
_VECTOR_CACHE: "OrderedDict[str, list[float]]" = OrderedDict()
_VECTOR_CACHE_SIZE = 512
_VECTOR_LOCK = threading.Lock()  # query_vector runs on _POOL threads
_vector_off_until = 0.0
_VECTOR_BREAKER_S = 600.0  # after a quota/API error, full-text only for 10 minutes
_VECTOR_BLIP_S = 60.0  # after a timeout / 5xx, just a minute


def vector_search_enabled() -> bool:
    return (os.environ.get("ORION_VECTOR_SEARCH", "on").strip().lower() not in {"off", "0", "false", "no"}
            and embeddings.is_configured() and time.monotonic() >= _vector_off_until)


def query_vector(text: str) -> Optional[list[float]]:
    """The question's Gemini vector — cached (students ask the same things),
    and never allowed to fail an answer: any embedding error trips a breaker
    and the question is answered from full-text search alone."""
    global _vector_off_until
    if not vector_search_enabled():
        return None
    key = re.sub(r"\s+", " ", text.strip().lower())
    with _VECTOR_LOCK:
        if key in _VECTOR_CACHE:
            _VECTOR_CACHE.move_to_end(key)
            return _VECTOR_CACHE[key]
    try:
        vec = embeddings.embed_query(text, timeout_s=3.0, max_attempts=1, max_wait_s=0.0)
    except embeddings.EmbeddingError as exc:
        pause = _VECTOR_BLIP_S if isinstance(exc, embeddings.EmbeddingUnavailable) else _VECTOR_BREAKER_S
        _vector_off_until = time.monotonic() + pause
        logger.warning("vector search off for %.0fs (%s: %s)", pause, exc.__class__.__name__, exc)
        return None
    with _VECTOR_LOCK:
        _VECTOR_CACHE[key] = vec
        if len(_VECTOR_CACHE) > _VECTOR_CACHE_SIZE:
            _VECTOR_CACHE.popitem(last=False)
    return vec


# Gemini cosine similarities on this corpus: unrelated text still scores
# ~0.55-0.63, real matches ~0.68+ (docs/embeddings.md). Normalised onto 0..1
# before fusing with the full-text rank.
_VEC_FLOOR, _VEC_SPAN = 0.55, 0.30
_W_LEXICAL, _W_VECTOR = 0.55, 0.45


def _vector_rows(client: Any, vec: list[float], cohort_family: Optional[str], cat: Optional[str],
                 dtype: Optional[str], k: int) -> Optional[list[dict]]:
    """None when the query failed or returned nothing — "no opinion", NOT
    "nothing is relevant": search() reads a missing chunk as evidence of
    irrelevance only when the vector search actually ran."""
    try:
        res = client.rpc(
            "search_document_chunks_semantic",
            {"query_embedding": vec, "match_count": k, "cohort_family": cohort_family,
             "filter_category": cat, "filter_document_type": dtype},
        ).execute()
    except Exception as exc:  # noqa: BLE001 - semantic search is an enhancement, never a failure
        logger.warning("semantic document search failed: %s: %s", exc.__class__.__name__, exc)
        return None
    return res.data or None


def search(
    client: Any,
    query: str,
    cohort_family: Optional[str],
    category: Optional[str] = None,
    document_type: Optional[str] = None,
    top_k: int = 6,
) -> list[SemanticSnippet]:
    """Hybrid search, preferring the source the router expects (hostel
    rules, the student's regulations, ...) but never limited to it."""
    text, _ = expand_query(query)

    # Semantic side: the same filters, ranked by meaning. The SQL itself is
    # ~15 ms; the cost is the Gemini call plus a round trip, so the whole
    # embed -> vector query chain runs alongside the full-text queries
    # instead of after them. One unfiltered query, with the source the
    # question is about preferred in Python below.
    def semantic_side() -> Optional[list[dict]]:
        vec = query_vector(query)
        return None if vec is None else _vector_rows(client, vec, cohort_family, None, None, top_k + 6)

    vec_future = _POOL.submit(semantic_side) if vector_search_enabled() else None

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
    focused = _POOL.submit(run, category, document_type, 5) if (category or document_type) else None
    broad = run(None, None, top_k)
    if focused is not None:
        for r in focused.result():
            r["rank"] = float(r["rank"]) * 1.6  # the source the question is about
            rows[r["chunk_id"]] = r
    for r in broad:
        rows.setdefault(r["chunk_id"], r)

    # A chunk found only by meaning still competes; a chunk found both ways
    # gets both signals.
    vec_rows = None
    if vec_future is not None:
        try:
            vec_rows = vec_future.result(timeout=_VECTOR_WAIT_S)
        except Exception as exc:  # noqa: BLE001 - full-text alone still answers
            logger.warning("semantic document search skipped: %s", exc.__class__.__name__)
    if vec_rows:
        max_lex = max((float(r["rank"]) for r in rows.values()), default=0.0) or 1.0
        sims: dict[int, float] = {}
        for r in vec_rows:
            sim = float(r["similarity"])
            if (category and r.get("category") == category) or (document_type and r.get("document_type") == document_type):
                sim += 0.02
            sims[r["chunk_id"]] = max(sims.get(r["chunk_id"], 0.0), sim)
            rows.setdefault(r["chunk_id"], {**r, "rank": 0.0})
        for cid, r in rows.items():
            lex = float(r.get("rank") or 0.0) / max_lex
            # 0.0 = "semantic search ran and did not return this chunk", which
            # is evidence it isn't about the question — distinct from None,
            # "semantic search didn't run" (no opinion).
            sim = sims.get(cid, 0.0)
            r["_vector_similarity"] = sim
            semantic = min(1.0, max(0.0, (sim - _VEC_FLOOR) / _VEC_SPAN))
            r["rank"] = _W_LEXICAL * min(lex, 1.6) + _W_VECTOR * semantic

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
            vector_similarity=r.get("_vector_similarity"),
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
    vector_similarity: Optional[float] = None


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
        # Meaning: a chunk the semantic side ranks close to the question is
        # preferred over one that merely shares its words (and vice versa).
        vs = snippets[si].vector_similarity
        if vs is not None:  # 0.0 = semantic search ran and didn't return this chunk
            s *= 0.6 if vs == 0.0 else 0.7 + 0.9 * min(1.0, max(0.0, (vs - 0.60) / 0.20))
        if len(unit) < 40:
            s *= 0.4  # a bare heading
        if re.search(r"\d", unit) and re.search(r"\d|%|\bpm\b|\bam\b|\bhow\s+(many|much|long)\b|\bwhen\b|\btime\b|\bfee\b", query, re.I):
            s *= 1.15
        # "What is the X requirement / minimum / limit?" is answered by the
        # clause that states the number, not one that merely mentions X.
        if re.search(r"\d+\s*%|\bminimum\s+(of\s+)?\d", unit, re.I) and re.search(
                r"\b(requirements?|required|minimum|maximum|limit|at\s+least|how\s+(many|much))\b", query, re.I):
            s *= 1.35
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
        vector_similarity=snip.vector_similarity,
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
