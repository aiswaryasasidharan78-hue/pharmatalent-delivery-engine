"""
Stage 4 — Decision-Maker Mapping (DMM).

Responsibilities:
  - Determine title band based on company size
  - Geographic cascade: city → country → region → worldwide
  - Check dmm_cache before any API call (idempotency + credit protection)
  - Call AI Ark (primary) with Prospeo fallback
  - Stop on first hit per company
  - Return raw CandidatePerson objects for validation

Model choice for people-search: no LLM here — pure API calls.
The LLM validation happens in the next stage.

Credit budget:
  AI Ark: 100 credits total = 100 people. Cap = 2 per call.
  Prospeo: 100 credits × 25 people = 2,500 people available.
"""
from __future__ import annotations

from typing import Optional

from app.api.aiark_client import AIArkClient
from app.api.prospeo_client import ProspeoClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.repository import get_dmm_cache, set_dmm_cache
from app.domain.icp_config import DMM_TITLE_BANDS, EU_REGIONS
from app.domain.schemas import CandidatePerson, CompanyRecord, DMMCacheKey, RunSummary
from app.services.exclusion_service import CandidateCompany

logger = get_logger(__name__)


def run_dmm_stage(
    fit_companies: list[CompanyRecord],
    candidate_map: dict[str, CandidateCompany],
    summary: RunSummary,
) -> dict[str, list[CandidatePerson]]:
    """
    For each fit company, find candidate decision-makers.

    Returns: { normalized_company_name → [CandidatePerson, ...] }
    """
    logger.info("dmm_started", stage="dmm", company_count=len(fit_companies))

    cfg = get_settings()
    provider = cfg.people_search_provider

    ai_ark = AIArkClient() if provider in ("ai_ark", "both") and cfg.ai_ark_token else None
    prospeo = ProspeoClient() if provider in ("prospeo", "both") and cfg.prospeo_api_key else None

    results: dict[str, list[CandidatePerson]] = {}

    for company in fit_companies:
        candidate = candidate_map.get(company.normalized_name)
        jobs = candidate.jobs if candidate else []

        # Determine job location for cascade
        primary_location = _extract_primary_location(jobs)

        titles = _get_title_band(company.size_band)
        if not titles:
            logger.warning(
                "dmm_no_title_band",
                stage="dmm",
                company=company.raw_name,
                size_band=company.size_band,
            )
            continue

        people = _cascade_search(
            company=company,
            titles=titles,
            primary_location=primary_location,
            ai_ark=ai_ark,
            prospeo=prospeo,
            summary=summary,
        )

        if people:
            results[company.normalized_name] = people
            summary.contacts_candidates += len(people)
        else:
            logger.info(
                "dmm_no_candidate_found",
                stage="dmm",
                company=company.raw_name,
            )

    logger.info(
        "dmm_completed",
        stage="dmm",
        companies_with_candidates=len(results),
        total_candidates=summary.contacts_candidates,
    )
    return results


def _cascade_search(
    company: CompanyRecord,
    titles: list[str],
    primary_location: Optional[str],
    ai_ark: Optional[AIArkClient],
    prospeo: Optional[ProspeoClient],
    summary: RunSummary,
) -> list[CandidatePerson]:
    """
    Geographic cascade: city → country → region → worldwide.
    Stop on first hit.  Check cache before every API call.
    """
    cfg = get_settings()
    cascade_locations = _build_cascade(primary_location)
    title_band_key = ",".join(sorted(titles))

    for level, location in cascade_locations:
        # Check DMM cache for each provider
        for provider_name, client in _providers(ai_ark, prospeo, cfg.people_search_provider):
            cache_key = DMMCacheKey(
                normalized_company_name=company.normalized_name,
                title_band=title_band_key,
                cascade_level=level,
                provider=provider_name,
            )
            cached = get_dmm_cache(cache_key)
            if cached is not None:
                summary.dmm_cache_hits += 1
                logger.info(
                    "dmm_cache_hit",
                    stage="dmm",
                    company=company.raw_name,
                    level=level,
                    provider=provider_name,
                    cached_result_count=cached.get("result_count", 0),
                )
                if cached.get("result_count", 0) > 0:
                    # Cache hit with results — we already stored them; skip re-query
                    return []  # caller loads from contacts table
                continue  # cache hit, 0 results — try next

            # Make the API call
            try:
                raw_people = _call_provider(
                    client=client,
                    provider_name=provider_name,
                    company=company,
                    titles=titles,
                    location=location,
                )
                summary.dmm_api_calls += 1
            except Exception as e:
                logger.error(
                    "dmm_api_error",
                    stage="dmm",
                    company=company.raw_name,
                    provider=provider_name,
                    level=level,
                    error=str(e),
                )
                set_dmm_cache(cache_key, 0)
                continue

            set_dmm_cache(cache_key, len(raw_people))

            if raw_people:
                people = [
                    _normalize_person(p, provider_name, level, company)
                    for p in raw_people
                ]
                logger.info(
                    "dmm_cascade_hit",
                    stage="dmm",
                    company=company.raw_name,
                    level=level,
                    provider=provider_name,
                    count=len(people),
                )
                return people

    return []


def _get_title_band(size_band: str | None) -> list[str]:
    if not size_band:
        return DMM_TITLE_BANDS.get("50-200", [])
    return DMM_TITLE_BANDS.get(size_band, DMM_TITLE_BANDS.get("50-200", []))


def _extract_primary_location(jobs: list) -> str | None:
    for job in jobs:
        if job.cities:
            return job.cities[0]
        if job.countries:
            return job.countries[0]
    return None


def _build_cascade(primary_location: str | None) -> list[tuple[str, str | None]]:
    """Build ordered list of (level_name, location_string) for cascade."""
    cascade = []
    if primary_location:
        cascade.append(("city", primary_location))
        # Derive country from location (simplified — use the location string itself)
        cascade.append(("country", primary_location))
    cascade.append(("region", "Europe"))
    cascade.append(("worldwide", None))
    return cascade


def _providers(
    ai_ark: Optional[AIArkClient],
    prospeo: Optional[ProspeoClient],
    provider_setting: str,
) -> list[tuple[str, object]]:
    """Return ordered list of (provider_name, client) pairs."""
    pairs = []
    if provider_setting in ("ai_ark", "both") and ai_ark:
        pairs.append(("ai_ark", ai_ark))
    if provider_setting in ("prospeo", "both") and prospeo:
        pairs.append(("prospeo", prospeo))
    if not pairs and prospeo:
        pairs.append(("prospeo", prospeo))
    if not pairs and ai_ark:
        pairs.append(("ai_ark", ai_ark))
    return pairs


def _call_provider(
    client: object,
    provider_name: str,
    company: CompanyRecord,
    titles: list[str],
    location: str | None,
) -> list[dict]:
    return client.people_search(  # type: ignore[union-attr]
        company_name=company.raw_name,
        company_domain=company.domain,
        titles=titles,
        location=location,
    )


def _normalize_person(
    raw: dict,
    provider: str,
    cascade_level: str,
    company: CompanyRecord,
) -> CandidatePerson:
    return CandidatePerson(
        full_name=raw.get("full_name") or raw.get("name") or raw.get("firstName", "") + " " + raw.get("lastName", ""),
        title=raw.get("title") or raw.get("job_title") or raw.get("jobTitle"),
        linkedin_url=raw.get("linkedin_url") or raw.get("linkedinUrl") or raw.get("linkedin"),
        location=raw.get("location") or raw.get("city"),
        about_snippet=raw.get("about") or raw.get("summary") or raw.get("headline"),
        company_name=company.raw_name,
        company_domain=company.domain,
        provider=provider,  # type: ignore[arg-type]
        cascade_level=cascade_level,  # type: ignore[arg-type]
    )
