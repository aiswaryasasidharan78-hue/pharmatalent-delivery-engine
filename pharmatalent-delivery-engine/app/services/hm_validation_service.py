"""
Stage 5 — Hiring-manager validation.

For every candidate returned by DMM, call deepseek/deepseek-chat to
classify whether this person could plausibly own the hiring decision.

Model choice: deepseek/deepseek-chat
  - Very cheap (~$0.0014 per 1K tokens)
  - Deterministic at temperature=0
  - Excellent for structured yes/no classification
  - Much cheaper than perplexity/sonar — no web browsing needed here,
    we're reasoning over facts already in the prompt

Runs once per candidate person.  Every drop is logged with a reason.
"""
from __future__ import annotations

from app.api.openrouter_client import OpenRouterClient
from app.core.logging import get_logger
from app.domain.normalization import canonicalize_linkedin_url, normalize_full_name
from app.domain.schemas import (
    CandidatePerson,
    CompanyRecord,
    ContactRecord,
    JobRecord,
    RunSummary,
)

logger = get_logger(__name__)


def run_hm_validation_stage(
    dmm_results: dict[str, list[CandidatePerson]],
    fit_companies: list[CompanyRecord],
    candidate_map: dict,
    summary: RunSummary,
) -> list[tuple[ContactRecord, list[str]]]:
    """
    Validate each candidate person with an LLM.
    Returns list of (ContactRecord, [job_id, ...]) for validated contacts.
    """
    logger.info(
        "hm_validation_started",
        stage="validation",
        total_candidates=summary.contacts_candidates,
    )

    client = OpenRouterClient()
    company_by_name: dict[str, CompanyRecord] = {c.normalized_name: c for c in fit_companies}

    validated: list[tuple[ContactRecord, list[str]]] = []

    for norm_company_name, people in dmm_results.items():
        company = company_by_name.get(norm_company_name)
        if not company:
            continue

        # Get associated jobs for this company
        candidate = candidate_map.get(norm_company_name)
        jobs: list[JobRecord] = candidate.jobs if candidate else []
        # Fetch real DB IDs by linkedin_id — in-memory UUIDs on existing
        # (skipped) jobs won't match what's stored in Supabase
        job_ids = _resolve_job_ids(jobs)

        for person in people:
            contact, job_id_list = _validate_person(
                person=person,
                company=company,
                jobs=jobs,
                job_ids=job_ids,
                client=client,
                summary=summary,
            )
            if contact and contact.hm_validation_decision == "yes":
                validated.append((contact, job_id_list))

    summary.contacts_validated = len(validated)
    logger.info(
        "hm_validation_completed",
        stage="validation",
        validated=summary.contacts_validated,
        dropped=summary.contacts_dropped,
    )
    return validated


def _validate_person(
    person: CandidatePerson,
    company: CompanyRecord,
    jobs: list[JobRecord],
    job_ids: list[str],
    client: OpenRouterClient,
    summary: RunSummary,
) -> tuple[ContactRecord | None, list[str]]:
    """Validate a single person and build a ContactRecord."""

    # Use the first (most relevant) job for the validation prompt
    primary_job = jobs[0] if jobs else None

    prompt_data = {
        "scraped_job_title": primary_job.title if primary_job else "",
        "scraped_job_description_snippet": (primary_job.description_text or "")[:500] if primary_job else "",
        "scraped_job_location": ", ".join(primary_job.locations) if primary_job and primary_job.locations else "",
        "person_full_name": person.full_name,
        "person_title": person.title or "",
        "person_about_snippet": person.about_snippet or "",
        "person_location": person.location or "",
        "company_name": company.raw_name,
        "company_size_band": company.size_band or "",
    }

    try:
        result = client.validate_hiring_manager(prompt_data)
    except Exception as e:
        logger.error(
            "hm_validation_error",
            stage="validation",
            person=person.full_name,
            error=str(e),
        )
        summary.errors.append(f"HM validation error for {person.full_name}: {e}")
        summary.contacts_dropped += 1
        return None, []

    decision = result.get("decision", "no")
    if decision not in ("yes", "no"):
        decision = "no"
    reason = result.get("reason", "")

    if decision == "no":
        logger.info(
            "hm_validation_dropped",
            stage="validation",
            person=person.full_name,
            company=company.raw_name,
            reason=reason,
        )
        summary.contacts_dropped += 1

    linkedin_url = canonicalize_linkedin_url(person.linkedin_url or "")

    contact = ContactRecord(
        full_name=person.full_name,
        normalized_full_name=normalize_full_name(person.full_name),
        title=person.title,
        linkedin_url=linkedin_url or None,
        location=person.location,
        about_snippet=person.about_snippet,
        company_id=company.id,
        provider=person.provider,
        cascade_level=person.cascade_level,
        hm_validation_decision=decision,
        hm_validation_reason=reason,
        validated_at=result.get("validated_at"),
        run_id=summary.run_id,
    )

    return contact, job_ids


def _resolve_job_ids(jobs: list) -> list[str]:
    """
    Look up the real Supabase-stored UUIDs for a list of jobs by their
    linkedin_id. This avoids the mismatch where existing (already-scraped)
    jobs have a freshly-generated in-memory UUID that doesn't match the DB.
    """
    if not jobs:
        return []
    from app.db.supabase_client import get_supabase_client
    client = get_supabase_client()
    linkedin_ids = [j.linkedin_id for j in jobs if j.linkedin_id]
    if not linkedin_ids:
        return []
    try:
        result = (
            client.table("jobs")
            .select("id, linkedin_id")
            .in_("linkedin_id", linkedin_ids)
            .execute()
        )
        return [row["id"] for row in (result.data or [])]
    except Exception:
        # Fallback to in-memory IDs — better than failing entirely
        return [str(j.id) for j in jobs]
