"""Unit tests for Stage 2 — active-client exclusion service."""
from __future__ import annotations

import csv
import os
from unittest.mock import patch, MagicMock
from datetime import datetime
from uuid import uuid4

import pytest

from app.domain.schemas import JobRecord, RunSummary
from app.services.exclusion_service import run_exclusion_stage
from app.domain.normalization import normalize_company_name


def _make_job(org: str, org_url: str = "", linkedin_id: str = None) -> JobRecord:
    return JobRecord(
        linkedin_id=linkedin_id or str(uuid4()),
        title="Director Regulatory Affairs",
        organization=org,
        organization_url=org_url or None,
        normalized_org_name=normalize_company_name(org),
        job_url=f"https://linkedin.com/jobs/view/{uuid4()}",
        scraped_at=datetime.utcnow(),
        run_id="test-run",
    )


def _run(jobs, tmp_path):
    """Helper: run exclusion with tmp_path as output_dir."""
    summary = RunSummary(run_id="r-test", started_at="2024-01-01")
    with patch("app.services.exclusion_service.get_settings") as mock_cfg:
        cfg = MagicMock()
        cfg.output_dir = str(tmp_path)
        mock_cfg.return_value = cfg
        candidates = run_exclusion_stage(jobs, summary)
    return candidates, summary


class TestExclusionService:
    def test_excludes_pfizer(self, mock_supabase, tmp_path):
        jobs = [_make_job("Pfizer"), _make_job("Molecular Partners AG")]
        candidates, summary = _run(jobs, tmp_path)
        names = [c.normalized_name for c in candidates]
        assert "molecular partners" in names
        assert not any("pfizer" in n for n in names)
        assert summary.companies_excluded_active_client == 1

    def test_excludes_biontech_se(self, mock_supabase, tmp_path):
        jobs = [_make_job("BioNTech SE")]
        candidates, summary = _run(jobs, tmp_path)
        assert len(candidates) == 0
        assert summary.companies_excluded_active_client == 1

    def test_deduplicates_companies(self, mock_supabase, tmp_path):
        jobs = [
            _make_job("Anavex Life Sciences"),
            _make_job("Anavex Life Sciences"),
            _make_job("Molecular Partners AG"),
        ]
        candidates, _ = _run(jobs, tmp_path)
        assert len(candidates) == 2

    def test_writes_active_client_hiring_csv(self, mock_supabase, tmp_path):
        jobs = [_make_job("Roche")]
        _, summary = _run(jobs, tmp_path)
        csv_path = tmp_path / "active_client_hiring.csv"
        assert csv_path.exists(), f"CSV not found; files: {list(tmp_path.iterdir())}"
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["client_name"] == "Roche"

    def test_empty_jobs_list(self, mock_supabase, tmp_path):
        candidates, _ = _run([], tmp_path)
        assert candidates == []
