"""Unit tests for Stage 5 — LLM hiring-manager validation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.domain.schemas import (
    CandidatePerson,
    CompanyRecord,
    JobRecord,
    RunSummary,
)
from app.domain.normalization import normalize_company_name
from app.services.hm_validation_service import run_hm_validation_stage, _validate_person
from datetime import datetime


def _make_company(name: str = "Test Biotech", size_band: str = "50-200") -> CompanyRecord:
    return CompanyRecord(
        normalized_name=normalize_company_name(name),
        raw_name=name,
        domain="testbiotech.com",
        size_band=size_band,
        icp_decision="fit",
        run_id="test",
    )


def _make_job(company: str = "Test Biotech") -> JobRecord:
    return JobRecord(
        linkedin_id=str(uuid4()),
        title="Director Regulatory Affairs",
        organization=company,
        job_url="https://linkedin.com/jobs/view/123",
        description_text="Looking for regulatory affairs expertise.",
        locations=["Zurich, Switzerland"],
        scraped_at=datetime.utcnow(),
        run_id="test",
    )


def _make_person(name: str = "Anna Müller", title: str = "Head of Talent") -> CandidatePerson:
    return CandidatePerson(
        full_name=name,
        title=title,
        linkedin_url=f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}",
        location="Zurich, Switzerland",
        provider="ai_ark",
        cascade_level="city",
    )


class TestHMValidation:
    def test_yes_decision_returns_contact(self, mock_supabase):
        company = _make_company()
        job = _make_job()
        person = _make_person()
        summary = RunSummary(run_id="r1", started_at="2024-01-01")

        mock_client = MagicMock()
        mock_client.validate_hiring_manager.return_value = {
            "decision": "yes",
            "reason": "Head of Talent at 150-person biotech would own this hire.",
        }

        contact, job_ids = _validate_person(
            person=person,
            company=company,
            jobs=[job],
            job_ids=[str(job.id)],
            client=mock_client,
            summary=summary,
        )

        assert contact is not None
        assert contact.hm_validation_decision == "yes"
        assert len(job_ids) == 1
        assert summary.contacts_dropped == 0

    def test_no_decision_increments_dropped(self, mock_supabase):
        company = _make_company()
        job = _make_job()
        person = _make_person(title="Junior HR Coordinator")
        summary = RunSummary(run_id="r2", started_at="2024-01-01")

        mock_client = MagicMock()
        mock_client.validate_hiring_manager.return_value = {
            "decision": "no",
            "reason": "Too junior to own a Director-level hire.",
        }

        contact, _ = _validate_person(
            person=person,
            company=company,
            jobs=[job],
            job_ids=[str(job.id)],
            client=mock_client,
            summary=summary,
        )

        assert contact.hm_validation_decision == "no"
        assert summary.contacts_dropped == 1

    def test_api_error_increments_dropped(self, mock_supabase):
        company = _make_company()
        job = _make_job()
        person = _make_person()
        summary = RunSummary(run_id="r3", started_at="2024-01-01")

        mock_client = MagicMock()
        mock_client.validate_hiring_manager.side_effect = Exception("API timeout")

        contact, _ = _validate_person(
            person=person,
            company=company,
            jobs=[job],
            job_ids=[str(job.id)],
            client=mock_client,
            summary=summary,
        )

        assert contact is None
        assert summary.contacts_dropped == 1
        assert len(summary.errors) == 1

    def test_invalid_decision_defaults_to_no(self, mock_supabase):
        company = _make_company()
        job = _make_job()
        person = _make_person()
        summary = RunSummary(run_id="r4", started_at="2024-01-01")

        mock_client = MagicMock()
        mock_client.validate_hiring_manager.return_value = {
            "decision": "maybe",  # invalid
            "reason": "Unclear.",
        }

        contact, _ = _validate_person(
            person=person,
            company=company,
            jobs=[job],
            job_ids=[str(job.id)],
            client=mock_client,
            summary=summary,
        )
        assert contact.hm_validation_decision == "no"
