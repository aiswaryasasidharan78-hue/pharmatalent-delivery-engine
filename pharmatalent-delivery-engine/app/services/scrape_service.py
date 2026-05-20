"""
Stage 1 — Job scraping and persistence.

Responsibilities:
  - Call Apify actor
  - Normalize raw job rows into JobRecord objects
  - Deduplicate against existing jobs in Supabase (idempotent rerun)
  - Persist new jobs
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.api.apify_client import ApifyClient
from app.core.logging import get_logger
from app.db.repository import get_existing_linkedin_ids, upsert_job
from app.domain.normalization import (
    extract_domain_from_url,
    normalize_company_name,
    parse_size_band,
)
from app.domain.schemas import JobRecord, RunSummary

logger = get_logger(__name__)


def run_scrape_stage(summary: RunSummary) -> list[JobRecord]:
    """
    Scrape LinkedIn jobs via Apify and persist new ones to Supabase.
    Returns the list of all scraped JobRecords (including already-existing ones).
    """
    logger.info("scrape_started", stage="scrape")

    client = ApifyClient()
    raw_items = client.scrape_jobs()

    logger.info("scrape_raw_items_received", stage="scrape", count=len(raw_items))
    summary.jobs_scraped = len(raw_items)

    # Deduplicate: don't re-insert jobs we already have
    existing_ids = get_existing_linkedin_ids()

    jobs: list[JobRecord] = []
    new_count = 0

    for item in raw_items:
        job = _normalize_job(item, summary.run_id)
        jobs.append(job)

        if job.linkedin_id in existing_ids:
            logger.info(
                "job_already_exists",
                stage="scrape",
                linkedin_id=job.linkedin_id,
            )
            continue

        upsert_job(job)
        existing_ids.add(job.linkedin_id)
        new_count += 1

    summary.jobs_persisted = new_count
    logger.info(
        "scrape_completed",
        stage="scrape",
        total=len(jobs),
        new=new_count,
        skipped=len(jobs) - new_count,
    )
    return jobs


def _normalize_job(item: dict[str, Any], run_id: str) -> JobRecord:
    org_url = item.get("organization_url") or item.get("companyUrl") or ""
    domain = extract_domain_from_url(org_url)
    employee_count = item.get("linkedin_org_employees") or item.get("organizationEmployees")
    size_text = item.get("linkedin_org_size") or item.get("organizationSize")

    return JobRecord(
        linkedin_id=str(item.get("linkedin_id") or item.get("id") or uuid4()),
        title=item.get("title") or item.get("jobTitle") or "",
        organization=item.get("organization") or item.get("companyName") or "",
        organization_url=org_url or None,
        organization_slug=item.get("linkedin_org_slug") or item.get("organizationSlug"),
        normalized_org_name=normalize_company_name(
            item.get("organization") or item.get("companyName") or ""
        ),
        date_posted=item.get("date_posted") or item.get("datePosted"),
        job_url=item.get("url") or item.get("jobUrl") or "",
        description_text=item.get("description_text") or item.get("descriptionText"),
        employment_types=_ensure_list(item.get("employment_type") or item.get("employmentType")),
        locations=_ensure_list(item.get("locations_derived") or item.get("locationsDerived")),
        cities=_ensure_list(item.get("cities_derived") or item.get("citiesDerived")),
        countries=_ensure_list(item.get("countries_derived") or item.get("countriesDerived")),
        org_employee_count=employee_count,
        org_size_band=parse_size_band(employee_count, size_text),
        org_industry=item.get("linkedin_org_industry") or item.get("organizationIndustry"),
        org_headquarters=item.get("linkedin_org_headquarters") or item.get("organizationHeadquarters"),
        org_domain=domain or None,
        scraped_at=datetime.utcnow(),
        run_id=run_id,
    )


def _ensure_list(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]
