"""Offline tests for backend/app/core/config.py's COOKIE_SAMESITE validation
(added 2026-09-22 for the Vercel/Render cross-site deployment — see
docs/backend-requirements.md §7). Reloads the module under a patched
environment rather than importing it once, since config.py evaluates its
module-level constants at import time.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

REQUIRED_ENV = {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "x"}


def _reload_config(monkeypatch, **env):
    for k, v in {**REQUIRED_ENV, **env}.items():
        monkeypatch.setenv(k, v)
    import app.core.config as config  # noqa: E402

    return importlib.reload(config)


def test_default_samesite_is_lax_and_unchanged(monkeypatch):
    config = _reload_config(monkeypatch)
    assert config.COOKIE_SAMESITE == "lax"
    assert config.COOKIE_SECURE is False


def test_samesite_none_requires_secure(monkeypatch):
    with pytest.raises(RuntimeError, match="requires COOKIE_SECURE=true"):
        _reload_config(monkeypatch, COOKIE_SAMESITE="none", COOKIE_SECURE="false")


def test_samesite_none_with_secure_is_accepted(monkeypatch):
    config = _reload_config(monkeypatch, COOKIE_SAMESITE="none", COOKIE_SECURE="true")
    assert config.COOKIE_SAMESITE == "none"


def test_invalid_samesite_value_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="not valid"):
        _reload_config(monkeypatch, COOKIE_SAMESITE="banana")


def test_samesite_is_case_and_whitespace_insensitive(monkeypatch):
    config = _reload_config(monkeypatch, COOKIE_SAMESITE=" Strict ")
    assert config.COOKIE_SAMESITE == "strict"
