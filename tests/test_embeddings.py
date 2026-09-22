"""Offline tests for backend/query/embeddings.py — the Gemini API is always
mocked; no GEMINI_API_KEY or network is needed."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors as genai_errors

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.query import embeddings  # noqa: E402

DIM = embeddings.EMBEDDING_DIM


def _vec(seed: float = 0.1, dim: int = DIM) -> SimpleNamespace:
    return SimpleNamespace(values=[seed] * dim)


class FakeModels:
    """Stands in for genai.Client().models. `script` is a list of outcomes
    consumed one per call: an exception to raise, or a callable
    (contents) -> list of embedding objects."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[dict] = []

    def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self.script.pop(0) if self.script else None
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return SimpleNamespace(embeddings=outcome(contents))
        return SimpleNamespace(embeddings=[_vec() for _ in contents])


@pytest.fixture
def fake(monkeypatch):
    models = FakeModels()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(embeddings, "_get_client", lambda: SimpleNamespace(models=models))
    monkeypatch.setattr(embeddings.time, "sleep", lambda _s: None)
    return models


def _texts(call) -> list[str]:
    return [c.parts[0].text for c in call["contents"]]


# ------------------------------------------------------------------ happy path


def test_embed_query_returns_one_768_dim_vector(fake):
    v = embeddings.embed_query("What is the attendance requirement?")
    assert len(v) == DIM
    call = fake.calls[0]
    assert call["model"] == "gemini-embedding-2"
    assert call["config"].output_dimensionality == DIM
    assert _texts(call) == ["task: question answering | query: What is the attendance requirement?"]


def test_embed_documents_wraps_each_text_separately(fake):
    """gemini-embedding-2 aggregates a plain list into ONE vector — every
    text must be its own Content so we get one vector per chunk."""
    vs = embeddings.embed_documents(["a", "b", "c"], ["Doc / Sec", None, "  "])
    assert len(vs) == 3 and all(len(v) == DIM for v in vs)
    assert len(fake.calls) == 1
    assert _texts(fake.calls[0]) == [
        "title: Doc / Sec | text: a",
        "title: none | text: b",
        "title: none | text: c",
    ]


def test_chunk_title_is_shared_format():
    assert embeddings.chunk_title("UG Regulations", "Attendance") == "UG Regulations / Attendance"
    assert embeddings.chunk_title("UG Regulations", None) == "UG Regulations"
    assert embeddings.chunk_title(None, None) is None


def test_empty_inputs(fake):
    assert embeddings.embed_documents([]) == []
    with pytest.raises(embeddings.EmbeddingRequestError):
        embeddings.embed_query("   ")
    with pytest.raises(embeddings.EmbeddingRequestError):
        embeddings.embed_documents(["ok", ""])
    assert fake.calls == []


# --------------------------------------------------------------------- failure


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(embeddings, "_client", None)
    assert embeddings.is_configured() is False
    with pytest.raises(embeddings.EmbeddingNotConfigured):
        embeddings.embed_query("hello")


def test_429_is_retried_then_succeeds(fake):
    fake.script = [genai_errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}})]
    assert len(embeddings.embed_query("q")) == DIM
    assert len(fake.calls) == 2


def test_5xx_exhausts_retry_budget(fake):
    fake.script = [genai_errors.ServerError(503, {"error": {"message": "overloaded"}})] * 10
    with pytest.raises(embeddings.EmbeddingUnavailable):
        embeddings.embed_documents(["x"], max_attempts=3)
    assert len(fake.calls) == 3


def test_timeout_is_transient(fake):
    fake.script = [httpx.ReadTimeout("slow")] * 5
    with pytest.raises(embeddings.EmbeddingUnavailable):
        embeddings.embed_query("q")  # query budget: 2 attempts
    assert len(fake.calls) == embeddings.QUERY_MAX_ATTEMPTS


def test_bad_request_is_not_retried(fake):
    fake.script = [genai_errors.ClientError(400, {"error": {"message": "bad input", "status": "INVALID_ARGUMENT"}})]
    with pytest.raises(embeddings.EmbeddingRequestError) as ei:
        embeddings.embed_query("q")
    assert not isinstance(ei.value, embeddings.EmbeddingAuthError)
    assert len(fake.calls) == 1


def test_invalid_key_is_auth_error_and_never_leaks_key(fake):
    fake.script = [genai_errors.ClientError(400, {"error": {"message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})]
    with pytest.raises(embeddings.EmbeddingAuthError) as ei:
        embeddings.embed_query("q")
    assert "test-key-not-real" not in str(ei.value)
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    "bad",
    [
        lambda contents: [],  # wrong count
        lambda contents: [_vec(dim=384) for _ in contents],  # wrong dimension
        lambda contents: [SimpleNamespace(values=[float("nan")] * DIM) for _ in contents],
        lambda contents: [SimpleNamespace(values=[0.0] * DIM) for _ in contents],
        lambda contents: None,
    ],
)
def test_malformed_response(fake, bad):
    fake.script = [bad]
    with pytest.raises(embeddings.EmbeddingResponseError):
        embeddings.embed_query("q")


def _quota_429(seconds: str) -> genai_errors.ClientError:
    return genai_errors.ClientError(
        429,
        {"error": {"message": f"Quota exceeded. Please retry in {seconds}.", "status": "RESOURCE_EXHAUSTED",
                   "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": seconds}]}},
    )


def test_query_does_not_wait_out_a_quota_window(fake):
    """An interactive request must degrade, not block for ~a minute."""
    fake.script = [_quota_429("56s")]
    with pytest.raises(embeddings.EmbeddingUnavailable):
        embeddings.embed_query("q")
    assert len(fake.calls) == 1


def test_batch_honours_server_retry_delay(fake, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(embeddings.time, "sleep", slept.append)
    fake.script = [_quota_429("56s")]
    assert len(embeddings.embed_documents(["x"])) == 1
    assert len(fake.calls) == 2
    assert slept and slept[0] >= 56


def test_batch_stops_on_very_long_server_delay(fake):
    fake.script = [_quota_429("3600s")]  # e.g. a daily quota
    with pytest.raises(embeddings.EmbeddingUnavailable):
        embeddings.embed_documents(["x"])
    assert len(fake.calls) == 1


def test_batch_interval_respects_per_minute_quota():
    assert embeddings.batch_interval_s(15, 90) == pytest.approx(10.0)


def test_daily_quota_stops_immediately(fake):
    fake.script = [genai_errors.ClientError(429, {"error": {
        "message": "Quota exceeded for metric: embed_content_free_tier_requests, limit: 1000",
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                     "violations": [{"quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier"}]}]}})]
    with pytest.raises(embeddings.EmbeddingUnavailable, match="daily quota"):
        embeddings.embed_documents(["x"])
    assert len(fake.calls) == 1
