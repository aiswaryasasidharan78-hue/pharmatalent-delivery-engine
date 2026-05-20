"""
Summary service — generates run_summary.json artifact after pipeline completion.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.repository import upsert_pipeline_run
from app.domain.schemas import RunSummary

logger = get_logger(__name__)


def finalize_summary(summary: RunSummary) -> None:
    """Write run_summary.json and persist run metadata to Supabase."""
    summary.finished_at = datetime.utcnow().isoformat()

    cfg = get_settings()
    os.makedirs(cfg.output_dir, exist_ok=True)
    path = os.path.join(cfg.output_dir, "run_summary.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, default=str)

    logger.info(
        "pipeline_summary",
        stage="finalize",
        run_id=summary.run_id,
        jobs_scraped=summary.jobs_scraped,
        companies_icp_fit=summary.companies_icp_fit,
        contacts_validated=summary.contacts_validated,
        contacts_dropped=summary.contacts_dropped,
        dmm_cache_hits=summary.dmm_cache_hits,
        errors=len(summary.errors),
        summary_path=path,
    )

    try:
        upsert_pipeline_run(summary)
    except Exception as e:
        logger.warning("pipeline_run_persist_failed", error=str(e))
