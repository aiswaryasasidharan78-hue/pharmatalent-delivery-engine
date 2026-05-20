"""
Stage 6 — Finalization persistence.

Writes validated contacts and contact_jobs links to Supabase.
Handles dedup: same person at multiple jobs → one contacts row,
multiple contact_jobs rows.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.db.repository import link_contact_to_job, upsert_contact
from app.domain.schemas import ContactRecord, RunSummary

logger = get_logger(__name__)


def persist_validated_contacts(
    validated: list[tuple[ContactRecord, list[str]]],
    summary: RunSummary,
) -> None:
    """
    Upsert each validated contact and link to all surfacing job IDs.
    Dedup is handled at the DB level via UNIQUE constraints on linkedin_url
    and (normalized_full_name, company_id).
    """
    logger.info(
        "persist_contacts_started",
        stage="persist",
        count=len(validated),
    )

    for contact, job_ids in validated:
        try:
            row = upsert_contact(contact)
            contact_id = row.get("id") or str(contact.id)

            for job_id in job_ids:
                link_contact_to_job(contact_id, job_id)

            logger.info(
                "contact_persisted",
                stage="persist",
                name=contact.full_name,
                company_id=str(contact.company_id),
                job_links=len(job_ids),
            )
        except Exception as e:
            logger.error(
                "contact_persist_failed",
                stage="persist",
                name=contact.full_name,
                error=str(e),
            )
            summary.errors.append(f"Failed to persist contact {contact.full_name}: {e}")

    logger.info("persist_contacts_completed", stage="persist")
