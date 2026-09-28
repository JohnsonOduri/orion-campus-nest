"""Shared test setup.

Hybrid document search (backend/query/documents.py) calls Gemini for the
question's vector whenever an API key is configured — and some tests load
`.env`, which would make the rest of the run depend on the network. Unit
tests run with vector search OFF; a test that exercises the hybrid path
turns it back on explicitly and fakes the embedding.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_vector_search(monkeypatch):
    monkeypatch.setenv("ORION_VECTOR_SEARCH", "off")
    yield
