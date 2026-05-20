"""
Repository layer.  All Supabase read/write operations live here.

Design principles:
  - Every write is an upsert (idempotency)
  - Upsert keys match the UNIQUE constraints in migrations.py
  - No business logic — just persistence
  - Returns the persisted row (with DB-generated id) after every write
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.db.supabase_client import get_supabase_client
from app.domain.schemas import (
    JobRecord,
    CompanyRecord,
    ContactRecord,
    DMMCacheKey,
    RunSummary,
)

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

def upsert_job(job: JobRecord) -> dict:
    client = get_supabase_client()
    data = _job_to_dict(job)
    result = (
        client.table("jobs")
        .upsert(data, on_conflict="linkedin_id")
        .execute()
    )
    row = result.data[0] if result.data else data
    logger.info(
        "db_upsert",
        stage="persist",
        table="jobs",
        linkedin_id=job.linkedin_id,
    )
    return row


def get_existing_linkedin_ids() -> set[str]:
    """Return all linkedin_ids already in the jobs table — for dedup."""
    client = get_supabase_client()
    result = client.table("jobs").select("linkedin_id").execute()
    return {row["linkedin_id"] for row in (result.data or [])}


# ─────────────────────────────────────────────────────────────────────────────
# Companies
# ─────────────────────────────────────────────────────────────────────────────

def upsert_company(company: CompanyRecord) -> dict:
    client = get_supabase_client()
    data = _company_to_dict(company)

    # Upsert on normalized_name; if domain is NULL skip the domain unique conflict
    result = (
        client.table("companies")
        .upsert(data, on_conflict="normalized_name")
        .execute()
    )
    row = result.data[0] if result.data else data
    logger.info(
        "db_upsert",
        stage="persist",
        table="companies",
        name=company.normalized_name,
        decision=company.icp_decision,
    )
    return row


def get_existing_company_names() -> set[str]:
    client = get_supabase_client()
    result = client.table("companies").select("normalized_name").execute()
    return {row["normalized_name"] for row in (result.data or [])}


def get_company_by_normalized_name(normalized_name: str) -> Optional[dict]:
    client = get_supabase_client()
    result = (
        client.table("companies")
        .select("*")
        .eq("normalized_name", normalized_name)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ─────────────────────────────────────────────────────────────────────────────
# Contacts
# ─────────────────────────────────────────────────────────────────────────────

def upsert_contact(contact: ContactRecord) -> dict:
    client = get_supabase_client()
    data = _contact_to_dict(contact)

    # Primary dedup key: linkedin_url (if available)
    if contact.linkedin_url:
        result = (
            client.table("contacts")
            .upsert(data, on_conflict="linkedin_url")
            .execute()
        )
    else:
        # Fallback dedup: (normalized_full_name, company_id)
        result = (
            client.table("contacts")
            .upsert(data, on_conflict="normalized_full_name,company_id")
            .execute()
        )

    row = result.data[0] if result.data else data
    logger.info(
        "db_upsert",
        stage="persist",
        table="contacts",
        name=contact.full_name,
        decision=contact.hm_validation_decision,
    )
    return row


def link_contact_to_job(contact_id: str, job_id: str) -> None:
    """Insert into contact_jobs join table. Idempotent — PK prevents dupes."""
    client = get_supabase_client()
    client.table("contact_jobs").upsert(
        {"contact_id": contact_id, "job_id": job_id},
        on_conflict="contact_id,job_id",
    ).execute()


# ─────────────────────────────────────────────────────────────────────────────
# DMM cache
# ─────────────────────────────────────────────────────────────────────────────

def get_dmm_cache(key: DMMCacheKey) -> Optional[dict]:
    """Return the cached DMM result for a (company, title_band, cascade, provider) tuple."""
    client = get_supabase_client()
    result = (
        client.table("dmm_cache")
        .select("*")
        .eq("normalized_company_name", key.normalized_company_name)
        .eq("title_band", key.title_band)
        .eq("cascade_level", key.cascade_level)
        .eq("provider", key.provider)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def set_dmm_cache(key: DMMCacheKey, result_count: int) -> None:
    client = get_supabase_client()
    client.table("dmm_cache").upsert(
        {
            "normalized_company_name": key.normalized_company_name,
            "title_band": key.title_band,
            "cascade_level": key.cascade_level,
            "provider": key.provider,
            "result_count": result_count,
        },
        on_conflict="normalized_company_name,title_band,cascade_level,provider",
    ).execute()
    logger.info(
        "dmm_cache_set",
        stage="dmm",
        company=key.normalized_company_name,
        cascade=key.cascade_level,
        provider=key.provider,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline runs
# ─────────────────────────────────────────────────────────────────────────────

def upsert_pipeline_run(summary: RunSummary) -> None:
    client = get_supabase_client()
    client.table("pipeline_runs").upsert(
        {
            "run_id": summary.run_id,
            "started_at": summary.started_at,
            "finished_at": summary.finished_at,
            "summary_json": summary.model_dump(),
        },
        on_conflict="run_id",
    ).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _job_to_dict(job: JobRecord) -> dict:
    return {
        "id": str(job.id),
        "linkedin_id": job.linkedin_id,
        "title": job.title,
        "organization": job.organization,
        "organization_url": job.organization_url,
        "organization_slug": job.organization_slug,
        "normalized_org_name": job.normalized_org_name,
        "date_posted": job.date_posted,
        "job_url": job.job_url,
        "description_text": job.description_text,
        "employment_types": job.employment_types,
        "locations": job.locations,
        "cities": job.cities,
        "countries": job.countries,
        "org_employee_count": job.org_employee_count,
        "org_size_band": job.org_size_band,
        "org_industry": job.org_industry,
        "org_headquarters": job.org_headquarters,
        "org_domain": job.org_domain,
        "scraped_at": job.scraped_at.isoformat(),
        "run_id": job.run_id,
    }


def _company_to_dict(company: CompanyRecord) -> dict:
    return {
        "id": str(company.id),
        "normalized_name": company.normalized_name,
        "raw_name": company.raw_name,
        "domain": company.domain or None,
        "headquarters": company.headquarters,
        "employee_count": company.employee_count,
        "size_band": company.size_band,
        "industry": company.industry,
        "linkedin_url": company.linkedin_url,
        "icp_decision": company.icp_decision,
        "icp_rationale": company.icp_rationale,
        "icp_confidence": company.icp_confidence,
        "icp_checked_at": company.icp_checked_at,
        "created_at": company.created_at.isoformat(),
        "run_id": company.run_id,
    }


def _contact_to_dict(contact: ContactRecord) -> dict:
    return {
        "id": str(contact.id),
        "full_name": contact.full_name,
        "normalized_full_name": contact.normalized_full_name,
        "title": contact.title,
        "linkedin_url": contact.linkedin_url,
        "location": contact.location,
        "about_snippet": contact.about_snippet,
        "company_id": str(contact.company_id) if contact.company_id else None,
        "provider": contact.provider,
        "cascade_level": contact.cascade_level,
        "hm_validation_decision": contact.hm_validation_decision,
        "hm_validation_reason": contact.hm_validation_reason,
        "found_at": contact.found_at.isoformat(),
        "validated_at": contact.validated_at,
        "run_id": contact.run_id,
    }
