"""
Stage 3 — ICP fit-check.

Responsibilities:
  - For each candidate company, call OpenRouter (perplexity/sonar) to browse
    the company website and return a fit verdict
  - Persist ALL companies (fit AND not_fit) with rationale for auditability
  - Return only fit companies for the DMM step

Model choice: perplexity/sonar
  - Web-enabled: can browse the company's actual website
  - Cheaper than sonar-pro for this volume
  - Sufficient reasoning quality for binary + confidence classification
"""
from __future__ import annotations

import asyncio
import csv
import os
from datetime import datetime
from uuid import uuid4

from app.api.openrouter_client import OpenRouterClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.repository import get_existing_company_names, upsert_company
from app.domain.schemas import CompanyRecord, RunSummary
from app.services.exclusion_service import CandidateCompany

logger = get_logger(__name__)


def run_icp_stage(
    candidates: list[CandidateCompany], summary: RunSummary
) -> list[CompanyRecord]:
    """
    Run ICP fit-check on all candidate companies.

    Idempotency: skip companies already in the DB (normalized_name match).
    Returns list of CompanyRecord with icp_decision == "fit".
    """
    logger.info("icp_started", stage="icp", candidate_count=len(candidates))

    existing_names = get_existing_company_names()
    client = OpenRouterClient()
    cfg = get_settings()

    fit_companies: list[CompanyRecord] = []
    icp_audit_rows: list[dict] = []

    sem = asyncio.Semaphore(cfg.pipeline_concurrency)

    # Run synchronously for simplicity; async version below if needed
    for candidate in candidates:
        record = _process_company(candidate, client, existing_names, summary)
        if record:
            icp_audit_rows.append(
                {
                    "company_name": record.raw_name,
                    "domain": record.domain,
                    "decision": record.icp_decision,
                    "rationale": record.icp_rationale,
                    "confidence": record.icp_confidence,
                    "checked_at": record.icp_checked_at,
                }
            )
            if record.icp_decision == "fit":
                fit_companies.append(record)

    summary.companies_icp_fit = len(fit_companies)
    summary.companies_icp_not_fit = summary.companies_found - summary.companies_excluded_active_client - len(fit_companies)

    _write_icp_audit_csv(icp_audit_rows, cfg.output_dir)

    logger.info(
        "icp_completed",
        stage="icp",
        fit=len(fit_companies),
        not_fit=summary.companies_icp_not_fit,
    )
    return fit_companies


def _process_company(
    candidate: CandidateCompany,
    client: OpenRouterClient,
    existing_names: set[str],
    summary: RunSummary,
) -> CompanyRecord | None:
    """Fit-check a single company and persist the result."""

    # Idempotency: if already checked, load from DB
    if candidate.normalized_name in existing_names:
        logger.info(
            "icp_company_already_checked",
            stage="icp",
            company=candidate.raw_name,
        )
        from app.db.repository import get_company_by_normalized_name
        row = get_company_by_normalized_name(candidate.normalized_name)
        if row:
            return _row_to_company_record(row)
        return None

    try:
        verdict = client.icp_fit_check(candidate.raw_name, candidate.domain)
    except Exception as e:
        logger.error(
            "icp_check_failed",
            stage="icp",
            company=candidate.raw_name,
            error=str(e),
        )
        summary.errors.append(f"ICP check failed for {candidate.raw_name}: {e}")
        verdict = {
            "decision": "not_fit",
            "rationale": f"Error during fit-check: {e}",
            "confidence": "low",
        }

    decision = verdict.get("decision", "not_fit")
    if decision not in ("fit", "not_fit"):
        decision = "not_fit"

    record = CompanyRecord(
        normalized_name=candidate.normalized_name,
        raw_name=candidate.raw_name,
        domain=candidate.domain,
        headquarters=candidate.headquarters,
        employee_count=candidate.employee_count,
        size_band=candidate.size_band,
        industry=candidate.industry,
        linkedin_url=candidate.linkedin_url,
        icp_decision=decision,
        icp_rationale=verdict.get("rationale", ""),
        icp_confidence=verdict.get("confidence", "low"),
        icp_checked_at=datetime.utcnow().isoformat(),
        run_id=summary.run_id,
    )

    upsert_company(record)
    existing_names.add(candidate.normalized_name)

    logger.info(
        "company_qualified",
        stage="icp",
        company=candidate.raw_name,
        decision=decision,
        confidence=record.icp_confidence,
    )
    return record


def _row_to_company_record(row: dict) -> CompanyRecord:
    from uuid import UUID
    return CompanyRecord(
        id=UUID(row["id"]) if row.get("id") else uuid4(),
        normalized_name=row["normalized_name"],
        raw_name=row["raw_name"],
        domain=row.get("domain"),
        headquarters=row.get("headquarters"),
        employee_count=row.get("employee_count"),
        size_band=row.get("size_band"),
        industry=row.get("industry"),
        linkedin_url=row.get("linkedin_url"),
        icp_decision=row.get("icp_decision", "not_fit"),
        icp_rationale=row.get("icp_rationale"),
        icp_confidence=row.get("icp_confidence"),
        icp_checked_at=row.get("icp_checked_at"),
        run_id=row.get("run_id", ""),
    )


def _write_icp_audit_csv(rows: list[dict], output_dir: str) -> None:
    if not rows:
        return
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "icp_fit_decisions.csv")
    fieldnames = ["company_name", "domain", "decision", "rationale", "confidence", "checked_at"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("icp_audit_csv_written", stage="icp", path=path, rows=len(rows))
