"""
Shared pytest fixtures.

Integration tests that hit real APIs are marked @pytest.mark.integration
and skipped by default.  Unit tests use only mocks and fixtures — no API
keys required, no credits spent.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures dir ──────────────────────────────────────────────────────────────
FIXTURES_DIR = Path(__file__).parent.parent / "app" / "fixtures"


@pytest.fixture
def sample_apify_jobs() -> list[dict]:
    with open(FIXTURES_DIR / "sample_apify_jobs.json") as f:
        return json.load(f)


@pytest.fixture
def sample_people() -> list[dict]:
    with open(FIXTURES_DIR / "sample_people_search.json") as f:
        return json.load(f)


# ── Env var stubs — allow importing config without real credentials ───────────
@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    """Provide dummy env vars so Settings() doesn't raise during unit tests."""
    monkeypatch.setenv("APIFY_TOKEN", "test-apify-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-sb-key")
    monkeypatch.setenv("AI_ARK_TOKEN", "test-aiark-token")
    monkeypatch.setenv("PROSPEO_API_KEY", "test-prospeo-key")
    # Reset singleton so each test gets a fresh Settings with patched env
    import app.core.config as cfg_mod
    cfg_mod._settings = None
    yield
    cfg_mod._settings = None


# ── Mock Supabase client ───────────────────────────────────────────────────────
@pytest.fixture
def mock_supabase(monkeypatch):
    mock = MagicMock()
    # Simulate empty DB (no existing records)
    mock.table.return_value.select.return_value.execute.return_value.data = []
    mock.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "test-uuid"}]
    mock.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

    import app.db.supabase_client as sb_mod
    sb_mod._client = mock
    yield mock
    sb_mod._client = None


# ── Mark integration tests ────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as requiring live API credentials"
    )
