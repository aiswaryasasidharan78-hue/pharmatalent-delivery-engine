"""
Stage 2 — Active-client exclusion.

Responsibilities:
  - Deduplicate companies from the jobs list
  - Check each against the active-client list
  - Write excluded-but-hiring signals to active_client_hiring.csv
  - Return candidate companies that passed the filter
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import NamedTuple

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.matching import check_active_client
from app.domain.normalization import extract_domain_from_url, normalize_company_name
from app.domain.schemas import ActiveClientHiringRow, JobRecord, RunSummary

logger = get_logger(__name__)


class CandidateCompany(NamedTuple):
    normalized_name: str
    raw_name: str
    domain: str | None
    jobs: list[JobRecord]
    employee_count: int | None
    size_band: str | None
    industry: str | None
    headquarters: str | None
    linkedin_url: str | None


def run_exclusion_stage(
    jobs: list[JobRecord], summary: RunSummary
) -> list[CandidateCompany]:
    """
    Deduplicate companies across jobs, exclude active clients,
    and return candidate companies for ICP fit-check.

    Side effect: writes active_client_hiring.csv for excluded-but-hiring signals.
    """
    logger.info("exclusion_started", stage="exclusion", job_count=len(jobs))

    # Deduplicate companies (one entry per normalized company name)
    company_map: dict[str, CandidateCompany] = {}
    for job in jobs:
        key = normalize_company_name(job.organization)
        if not key:
            continue
        if key in company_map:
            # Merge jobs for the same company
            existing = company_map[key]
            company_map[key] = existing._replace(jobs=existing.jobs + [job])
        else:
            company_map[key] = CandidateCompany(
                normalized_name=key,
                raw_name=job.organization,
                domain=job.org_domain,
                jobs=[job],
                employee_count=job.org_employee_count,
                size_band=job.org_size_band,
                industry=job.org_industry,
                headquarters=job.org_headquarters,
                linkedin_url=job.organization_url,
            )

    summary.companies_found = len(company_map)
    logger.info("companies_deduped", stage="exclusion", count=len(company_map))

    candidates: list[CandidateCompany] = []
    hiring_signals: list[ActiveClientHiringRow] = []

    for norm_name, company in company_map.items():
        result = check_active_client(company.raw_name, company.domain)

        if result.is_excluded:
            logger.info(
                "company_excluded",
                stage="exclusion",
                company=company.raw_name,
                matched_client=result.matched_client,
                method=result.match_method,
            )
            summary.companies_excluded_active_client += 1

            # P2: emit hiring signal for each excluded-but-hiring active client
            for job in company.jobs:
                hiring_signals.append(
                    ActiveClientHiringRow(
                        client_name=result.matched_client or company.raw_name,
                        matched_company_name_raw=company.raw_name,
                        scraped_job_title=job.title,
                        scraped_job_url=job.job_url,
                        location=", ".join(job.locations) if job.locations else "",
                        posted_at=job.date_posted,
                        detected_at=datetime.utcnow().isoformat(),
                    )
                )
        else:
            candidates.append(company)

    _write_hiring_signals_csv(hiring_signals, summary)

    logger.info(
        "exclusion_completed",
        stage="exclusion",
        candidates=len(candidates),
        excluded=summary.companies_excluded_active_client,
        hiring_signals=len(hiring_signals),
    )
    return candidates


def _write_hiring_signals_csv(
    rows: list[ActiveClientHiringRow], summary: RunSummary
) -> None:
    if not rows:
        return

    cfg = get_settings()
    os.makedirs(cfg.output_dir, exist_ok=True)
    path = os.path.join(cfg.output_dir, "active_client_hiring.csv")

    fieldnames = [
        "client_name",
        "matched_company_name_raw",
        "scraped_job_title",
        "scraped_job_url",
        "location",
        "posted_at",
        "detected_at",
    ]

    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

    summary.active_client_hiring_signals = len(rows)
    logger.info(
        "active_client_hiring_csv_written",
        stage="exclusion",
        path=path,
        rows=len(rows),
    )
