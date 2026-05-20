"""
Pipeline orchestrator.

Sequential modular pipeline:
  Stage 1 → Scrape jobs (Apify)
  Stage 2 → Active-client exclusion
  Stage 3 → ICP fit-check (perplexity/sonar, web-enabled)
  Stage 4 → Decision-maker mapping (AI Ark + Prospeo)
  Stage 5 → LLM hiring-manager validation (deepseek/deepseek-chat)
  Stage 6 → Persist contacts + job links
  Finalize → run_summary.json + pipeline_runs row

Design decisions:
  - Modular monolith: no microservices, no distributed orchestration.
    Simpler, easier to test, easier to debug.
  - Every stage has typed inputs and outputs.
  - Every failure is logged with context; pipeline continues where possible.
  - Single run_id threads through all logs and DB rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from app.core.logging import configure_logging, get_logger, set_run_id
from app.core.config import get_settings
from app.db.migrations import run_migrations
from app.domain.schemas import RunSummary
from app.services.dmm_service import run_dmm_stage
from app.services.exclusion_service import run_exclusion_stage
from app.services.hm_validation_service import run_hm_validation_stage
from app.services.icp_fit_service import run_icp_stage
from app.services.persistence_service import persist_validated_contacts
from app.services.scrape_service import run_scrape_stage
from app.services.summary_service import finalize_summary

logger = get_logger(__name__)


def run_pipeline() -> RunSummary:
    cfg = get_settings()
    configure_logging(cfg.log_level)

    run_id = str(uuid.uuid4())
    set_run_id(run_id)

    summary = RunSummary(
        run_id=run_id,
        started_at=datetime.utcnow().isoformat(),
    )

    logger.info("pipeline_started", stage="init", run_id=run_id)

    # ── Init: ensure schema exists ────────────────────────────────────────────
    try:
        run_migrations()
    except Exception as e:
        logger.error("migration_failed", error=str(e))
        summary.errors.append(f"Migration failed: {e}")
        # Continue — schema may already exist

    # ── Stage 1: Scrape ───────────────────────────────────────────────────────
    try:
        jobs = run_scrape_stage(summary)
    except Exception as e:
        logger.error("scrape_stage_failed", error=str(e))
        summary.errors.append(f"Scrape failed: {e}")
        finalize_summary(summary)
        return summary

    if not jobs:
        logger.warning("no_jobs_scraped", stage="scrape")
        finalize_summary(summary)
        return summary

    # ── Stage 2: Exclusion ────────────────────────────────────────────────────
    try:
        candidates = run_exclusion_stage(jobs, summary)
    except Exception as e:
        logger.error("exclusion_stage_failed", error=str(e))
        summary.errors.append(f"Exclusion failed: {e}")
        finalize_summary(summary)
        return summary

    if not candidates:
        logger.warning("no_candidates_after_exclusion", stage="exclusion")
        finalize_summary(summary)
        return summary

    # Build a lookup: normalized_name → CandidateCompany (needed later)
    candidate_map = {c.normalized_name: c for c in candidates}

    # ── Stage 3: ICP fit-check ────────────────────────────────────────────────
    try:
        fit_companies = run_icp_stage(candidates, summary)
    except Exception as e:
        logger.error("icp_stage_failed", error=str(e))
        summary.errors.append(f"ICP stage failed: {e}")
        finalize_summary(summary)
        return summary

    if not fit_companies:
        logger.warning("no_icp_fit_companies", stage="icp")
        finalize_summary(summary)
        return summary

    # ── Stage 4: DMM ──────────────────────────────────────────────────────────
    try:
        dmm_results = run_dmm_stage(fit_companies, candidate_map, summary)
    except Exception as e:
        logger.error("dmm_stage_failed", error=str(e))
        summary.errors.append(f"DMM failed: {e}")
        finalize_summary(summary)
        return summary

    if not dmm_results:
        logger.warning("no_dmm_candidates_found", stage="dmm")
        finalize_summary(summary)
        return summary

    # ── Stage 5: HM validation ────────────────────────────────────────────────
    try:
        validated = run_hm_validation_stage(
            dmm_results, fit_companies, candidate_map, summary
        )
    except Exception as e:
        logger.error("hm_validation_stage_failed", error=str(e))
        summary.errors.append(f"HM validation failed: {e}")
        finalize_summary(summary)
        return summary

    # ── Stage 6: Persist contacts ─────────────────────────────────────────────
    try:
        persist_validated_contacts(validated, summary)
    except Exception as e:
        logger.error("persist_stage_failed", error=str(e))
        summary.errors.append(f"Persist failed: {e}")

    # ── Finalize ──────────────────────────────────────────────────────────────
    finalize_summary(summary)
    logger.info("pipeline_completed", stage="finalize", run_id=run_id)
    return summary
