"""Unit tests for scrape service normalization."""
import pytest
from app.services.scrape_service import _normalize_job, _ensure_list


class TestNormalizeJob:
    def test_basic_normalization(self):
        raw = {
            "linkedin_id": "123",
            "title": "Director Regulatory Affairs",
            "organization": "Molecular Partners AG",
            "organization_url": "https://www.linkedin.com/company/molecular-partners",
            "url": "https://www.linkedin.com/jobs/view/123",
            "employment_type": ["FULL_TIME"],
            "locations_derived": ["Zurich, Zurich, Switzerland"],
            "cities_derived": ["Zurich"],
            "countries_derived": ["Switzerland"],
            "linkedin_org_employees": 180,
            "linkedin_org_size": "51-200 employees",
        }
        job = _normalize_job(raw, "run-001")
        assert job.linkedin_id == "123"
        assert job.normalized_org_name == "molecular partners"
        assert job.org_size_band == "50-200"
        assert job.org_domain == "linkedin.com"  # from linkedin URL
        assert job.run_id == "run-001"

    def test_handles_missing_optional_fields(self):
        raw = {
            "linkedin_id": "456",
            "title": "Head of Clinical Operations",
            "organization": "TestCo",
            "url": "https://example.com/job/456",
        }
        job = _normalize_job(raw, "run-002")
        assert job.linkedin_id == "456"
        assert job.employment_types == []
        assert job.locations == []


class TestEnsureList:
    def test_none_returns_empty(self):
        assert _ensure_list(None) == []

    def test_list_passthrough(self):
        assert _ensure_list(["a", "b"]) == ["a", "b"]

    def test_scalar_wrapped(self):
        assert _ensure_list("FULL_TIME") == ["FULL_TIME"]
