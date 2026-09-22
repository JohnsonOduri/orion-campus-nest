"""Gemini embeddings — the one place ORION turns text into vectors.

Used at query time by retrieval.py (one query embedding per semantic /
hybrid request) and at ingestion time by scripts/ingest_documents.py and
scripts/reembed_gemini.py. Nothing else should call the Gemini embedding
API directly: model, dimensionality, input formatting, retries and response
validation all live here so corpus vectors and query vectors can never
drift into different spaces.

Model: `gemini-embedding-2`, `output_dimensionality=768` (the API
auto-normalizes truncated outputs, verified: every returned vector has
L2 norm 1.0, so cosine distance in pgvector is well-defined).

Task semantics: gemini-embedding-2 does NOT accept `task_type`; per the
official docs, the task goes into the text itself —
    query:    "task: question answering | query: {text}"
    document: "title: {title} | text: {text}"   ("title: none" if unknown)
The formatting helpers below are the single definition of those strings.

Batching: passing a list of plain strings to embed_content makes
gemini-embedding-2 return ONE aggregated vector for the whole list. Every
text is therefore wrapped in its own `types.Content`, which returns one
vector per input — and the response count is checked, never assumed.

Errors are split so callers can react correctly:
  EmbeddingNotConfigured  — no GEMINI_API_KEY (permanent, never retried)
  EmbeddingAuthError      — key rejected / no permission (permanent; a
                            batch job must abort, not skip rows)
  EmbeddingRequestError   — other 4xx except 429: bad input/config
                            (permanent, never retried)
  EmbeddingUnavailable    — 429 / 5xx / timeout / network, still failing
                            after the retry budget (transient; safe to retry
                            later — the re-embed script resumes from here)
  EmbeddingResponseError  — the API answered but with the wrong number of
                            vectors, wrong dimension, or non-finite values
The API key is never logged or included in an error message.
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
import time
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger("orion.embeddings")

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIM = 768

# One interactive request should never hang on the embedding call: a short
# timeout, one quick retry, and never a long wait for a quota window —
# then degrade (retrieval.py turns this into a "semantic retrieval
# unavailable" warning instead of a 500).
QUERY_TIMEOUT_S = 10.0
QUERY_MAX_ATTEMPTS = 2
QUERY_MAX_WAIT_S = 2.0
# Batch/ingestion calls can afford to wait out a per-minute quota window
# (the free tier answers 429 with "retry in ~60s"). A longer server-
# requested wait (e.g. a daily quota) stops the batch instead.
BATCH_TIMEOUT_S = 60.0
BATCH_MAX_ATTEMPTS = 6
BATCH_MAX_WAIT_S = 120.0

# Free-tier quota counts every embedded TEXT as one request (verified:
# `embed_content_free_tier_requests`, limit 100/min for gemini-embedding-2),
# not every API call — so batch pacing is expressed in texts per minute.
DEFAULT_TEXTS_PER_MINUTE = 90

QUERY_TASK_QA = "question answering"
QUERY_TASK_SEARCH = "search result"


class EmbeddingError(RuntimeError):
    pass


class EmbeddingNotConfigured(EmbeddingError):
    pass


class EmbeddingRequestError(EmbeddingError):
    pass


class EmbeddingAuthError(EmbeddingRequestError):
    pass


class EmbeddingUnavailable(EmbeddingError):
    pass


class EmbeddingResponseError(EmbeddingError):
    pass


# ------------------------------------------------------------- formatting


def _clean(text: str) -> str:
    # "|" is the field separator of the task-prefix format; collapse
    # whitespace so the prefix stays unambiguous.
    return " ".join((text or "").split())


def format_query(text: str, task: str = QUERY_TASK_QA) -> str:
    return f"task: {task} | query: {_clean(text)}"


def format_document(text: str, title: Optional[str] = None) -> str:
    t = _clean(title or "") or "none"
    return f"title: {t} | text: {(text or '').strip()}"


def chunk_title(document_title: Optional[str], section_title: Optional[str] = None) -> Optional[str]:
    """The title used for a document chunk. Shared by ingestion and the
    re-embed script so the same chunk always embeds to the same input."""
    parts = [p.strip() for p in (document_title, section_title) if p and p.strip()]
    return " / ".join(parts) or None


# ----------------------------------------------------------------- client

_client: Any = None
_client_key: Optional[str] = None


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise EmbeddingNotConfigured("GEMINI_API_KEY is not set")
    return key


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _get_client() -> Any:
    """Lazily-built, process-wide google-genai client (re-created only if
    the key changes). Tests monkeypatch this function."""
    global _client, _client_key
    key = _api_key()
    if _client is None or _client_key != key:
        from google import genai

        _client = genai.Client(api_key=key)
        _client_key = key
    return _client


# ----------------------------------------------------------------- errors


def _is_transient(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code == 429 or code >= 500
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
    except ImportError:  # pragma: no cover - httpx is a google-genai dependency
        pass
    return isinstance(exc, (TimeoutError, ConnectionError))


def _is_auth(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return True
    # Gemini answers an invalid key with 400 INVALID_ARGUMENT / API_KEY_INVALID.
    text = f"{getattr(exc, 'message', '')} {getattr(exc, 'details', '')}".lower()
    return code == 400 and ("api key" in text or "api_key_invalid" in text)


def _server_retry_delay(exc: BaseException) -> Optional[float]:
    """The wait the API asked for on a 429 (google.rpc.RetryInfo
    `retryDelay: "56s"`, or "Please retry in 56.4s" in the message)."""
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        for d in (details.get("error") or {}).get("details") or []:
            delay = isinstance(d, dict) and d.get("retryDelay")
            if isinstance(delay, str) and delay.endswith("s"):
                try:
                    return float(delay[:-1])
                except ValueError:
                    pass
    m = re.search(r"retry in ([0-9.]+)s", str(getattr(exc, "message", "") or exc))
    return float(m.group(1)) if m else None


def _is_daily_quota(exc: BaseException) -> bool:
    """A per-day quota 429 (free tier: 1000 embedded texts/day, verified)
    won't clear within any retry window — retrying only burns time."""
    if getattr(exc, "code", None) != 429:
        return False
    text = f"{getattr(exc, 'message', '')} {getattr(exc, 'details', '')}"
    return "PerDay" in text or "per day" in text.lower()


def _describe(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    msg = getattr(exc, "message", None) or exc.__class__.__name__
    label = " ".join(str(p) for p in (code, status) if p)
    return f"{label}: {msg}" if label else str(msg)


def _with_retry(
    fn: Callable[[], Any],
    *,
    max_attempts: int,
    max_wait_s: float,
    sleep: Optional[Callable[[float], None]] = None,
) -> Any:
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_transient(exc):
                cls = EmbeddingAuthError if _is_auth(exc) else EmbeddingRequestError
                raise cls(f"Gemini embedding request rejected ({_describe(exc)})") from exc
            if _is_daily_quota(exc):
                raise EmbeddingUnavailable(
                    "Gemini embedding daily quota exhausted — retry after the quota resets "
                    f"({_describe(exc)})"
                ) from exc
            if attempt >= max_attempts:
                raise EmbeddingUnavailable(
                    f"Gemini embedding still failing after {attempt} attempt(s) ({_describe(exc)})"
                ) from exc
            delay = max(2 ** (attempt - 1), _server_retry_delay(exc) or 0) * (1 + random.random() * 0.1)
            if delay > max_wait_s:
                raise EmbeddingUnavailable(
                    f"Gemini embedding rate-limited; server asks to wait {delay:.0f}s ({_describe(exc)})"
                ) from exc
            logger.warning("embedding attempt %d failed (%s); retrying in %.1fs", attempt, _describe(exc), delay)
            (sleep or time.sleep)(delay)


def _validate(vectors: Any, expected: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        got = len(vectors) if isinstance(vectors, list) else type(vectors).__name__
        raise EmbeddingResponseError(f"expected {expected} embedding(s), got {got}")
    out: list[list[float]] = []
    for v in vectors:
        values = getattr(v, "values", None)
        if not values or len(values) != EMBEDDING_DIM:
            n = len(values) if values else 0
            raise EmbeddingResponseError(f"expected {EMBEDDING_DIM}-dim embedding, got {n}")
        floats = [float(x) for x in values]
        if not all(math.isfinite(x) for x in floats) or not any(floats):
            raise EmbeddingResponseError("embedding contains non-finite or all-zero values")
        out.append(floats)
    return out


# -------------------------------------------------------------------- API


def _embed(inputs: Sequence[str], *, timeout_s: float, max_attempts: int, max_wait_s: float) -> list[list[float]]:
    from google.genai import types

    client = _get_client()
    contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in inputs]
    config = types.EmbedContentConfig(
        output_dimensionality=EMBEDDING_DIM,
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
    )

    def call() -> Any:
        return client.models.embed_content(model=EMBEDDING_MODEL, contents=contents, config=config)

    started = time.perf_counter()
    response = _with_retry(call, max_attempts=max_attempts, max_wait_s=max_wait_s)
    vectors = _validate(getattr(response, "embeddings", None), len(inputs))
    logger.debug("embedded %d input(s) in %.0f ms", len(inputs), (time.perf_counter() - started) * 1000)
    return vectors


def embed_query(
    text: str,
    *,
    task: str = QUERY_TASK_QA,
    timeout_s: float = QUERY_TIMEOUT_S,
    max_attempts: int = QUERY_MAX_ATTEMPTS,
    max_wait_s: float = QUERY_MAX_WAIT_S,
) -> list[float]:
    """One 768-dim query vector. Call once per retrieval operation."""
    if not (text or "").strip():
        raise EmbeddingRequestError("cannot embed an empty query")
    return _embed([format_query(text, task)], timeout_s=timeout_s, max_attempts=max_attempts, max_wait_s=max_wait_s)[0]


def embed_documents(
    texts: Sequence[str],
    titles: Optional[Sequence[Optional[str]]] = None,
    *,
    timeout_s: float = BATCH_TIMEOUT_S,
    max_attempts: int = BATCH_MAX_ATTEMPTS,
    max_wait_s: float = BATCH_MAX_WAIT_S,
) -> list[list[float]]:
    """One 768-dim vector per text, in order, in a single API call. Callers
    own batching/pacing (keep batches small — see scripts/reembed_gemini.py)."""
    if not texts:
        return []
    if titles is not None and len(titles) != len(texts):
        raise ValueError("titles must be the same length as texts")
    if any(not (t or "").strip() for t in texts):
        raise EmbeddingRequestError("cannot embed an empty document text")
    inputs = [format_document(t, titles[i] if titles else None) for i, t in enumerate(texts)]
    return _embed(inputs, timeout_s=timeout_s, max_attempts=max_attempts, max_wait_s=max_wait_s)


def embed_document(text: str, title: Optional[str] = None) -> list[float]:
    return embed_documents([text], [title])[0]


def batch_interval_s(batch_size: int, texts_per_minute: Optional[float] = None) -> float:
    """Seconds to leave between batch calls to stay under the per-minute
    text quota (ORION_EMBED_TEXTS_PER_MINUTE overrides the default)."""
    rate = texts_per_minute or float(os.environ.get("ORION_EMBED_TEXTS_PER_MINUTE") or DEFAULT_TEXTS_PER_MINUTE)
    return batch_size * 60.0 / rate
