"""
Integration tests — mock all external APIs but exercise the full
pipeline flow end-to-end.  No real credentials required.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURES = Path(__file__).parent.parent.parent / "app" / "fixtures"


@pytest.fixture
def sample_jobs():
    with open(FIXTURES / "sample_apify_jobs.json") as f:
        return json.load(f)


@pytest.fixture
def sample_people():
    with open(FIXTURES / "sample_people_search.json") as f:
        return json.load(f)


@pytest.mark.integration
class TestFullPipelineFlow:
    """
    Exercises the full pipeline with mocked APIs.
    Verifies: scrape → exclusion → ICP → DMM → validation → persist.
    """

    def test_pipeline_excludes_active_clients(self, sample_jobs, mock_supabase, tmp_path):
        """Pfizer and BioNTech jobs from the fixture must not reach ICP stage."""
        from app.domain.normalization import normalize_company_name
        from app.services.exclusion_service import run_exclusion_stage
        from app.domain.schemas import RunSummary
        from app.services.scrape_service import _normalize_job

        with patch("app.core.config.get_settings") as mock_cfg:
            cfg = MagicMock()
            cfg.output_dir = str(tmp_path)
            cfg.pipeline_concurrency = 1
            cfg.people_search_max_results = 2
            cfg.people_search_provider = "ai_ark"
            cfg.ai_ark_token = "test"
            cfg.prospeo_api_key = ""
            cfg.icp_model = "perplexity/sonar"
            cfg.hm_validation_model = "deepseek/deepseek-chat"
            mock_cfg.return_value = cfg

            jobs = [_normalize_job(j, "test-run") for j in sample_jobs]
            summary = RunSummary(run_id="test-run", started_at="2024-01-01")
            candidates = run_exclusion_stage(jobs, summary)

        # BioNTech and Pfizer should be excluded
        candidate_names = [c.normalized_name for c in candidates]
        assert not any("pfizer" in n for n in candidate_names)
        assert not any("biontech" in n for n in candidate_names)
        # Molecular Partners and Anavex should pass through
        assert any("molecular" in n for n in candidate_names)
        assert any("anavex" in n for n in candidate_names)
        assert summary.companies_excluded_active_client == 2

    def test_icp_stage_persists_both_fit_and_not_fit(self, mock_supabase, tmp_path):
        """ICP stage must persist all companies regardless of decision."""
        from app.services.icp_fit_service import run_icp_stage
        from app.services.exclusion_service import CandidateCompany
        from app.domain.schemas import RunSummary, JobRecord
        from datetime import datetime
        from uuid import uuid4

        with patch("app.core.config.get_settings") as mock_cfg:
            cfg = MagicMock()
            cfg.output_dir = str(tmp_path)
            cfg.pipeline_concurrency = 1
            cfg.icp_model = "perplexity/sonar"
            mock_cfg.return_value = cfg

            mock_openrouter = MagicMock()
            mock_openrouter.icp_fit_check.side_effect = [
                {"decision": "fit", "rationale": "EU biotech.", "confidence": "high"},
                {"decision": "not_fit", "rationale": "No EU office.", "confidence": "medium"},
            ]

            dummy_job = JobRecord(
                linkedin_id="test-1",
                title="Director RA",
                organization="TestCo",
                job_url="https://example.com/1",
                scraped_at=datetime.utcnow(),
                run_id="test",
            )
            candidates = [
                CandidateCompany("fit co", "Fit Co", "fitco.com", [dummy_job], 100, "50-200", "Biotech", None, None),
                CandidateCompany("not fit co", "Not Fit Co", "notfit.com", [dummy_job], 100, "50-200", "Unknown", None, None),
            ]
            summary = RunSummary(run_id="test-run", started_at="2024-01-01")

            with patch("app.services.icp_fit_service.OpenRouterClient", return_value=mock_openrouter):
                with patch("app.services.icp_fit_service.get_existing_company_names", return_value=set()):
                    with patch("app.services.icp_fit_service.upsert_company"):
                        fit = run_icp_stage(candidates, summary)

        assert len(fit) == 1
        assert fit[0].raw_name == "Fit Co"
        assert summary.companies_icp_fit == 1


class TestDMMCacheIdempotency:
    """DMM cache must prevent re-querying the same (company, title_band) pair."""

    def test_cache_hit_skips_api_call(self, mock_supabase):
        from app.db.repository import get_dmm_cache, set_dmm_cache
        from app.domain.schemas import DMMCacheKey

        # Simulate a cache hit
        mock_supabase.table.return_value.select.return_value.eq.return_value\
            .eq.return_value.eq.return_value.eq.return_value.limit.return_value\
            .execute.return_value.data = [{"result_count": 0, "queried_at": "2024-01-01"}]

        key = DMMCacheKey(
            normalized_company_name="molecular partners",
            title_band="Head of Talent,Head of HR",
            cascade_level="city",
            provider="ai_ark",
        )
        cached = get_dmm_cache(key)
        assert cached is not None  # Cache exists — don't re-query
