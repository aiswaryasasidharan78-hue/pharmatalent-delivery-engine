"""
Domain schemas.  These are the typed data contracts between pipeline stages.
All persistence models mirror these; no raw dicts cross stage boundaries.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

class ScrapedJob(BaseModel):
    """Raw job as returned by Apify / fantastic.jobs actor."""

    linkedin_id: str
    title: str
    organization: str
    organization_url: Optional[str] = None
    organization_slug: Optional[str] = None
    date_posted: Optional[str] = None
    url: str
    description_text: Optional[str] = None
    seniority: Optional[str] = None
    employment_type: list[str] = Field(default_factory=list)
    locations_derived: list[str] = Field(default_factory=list)
    cities_derived: list[str] = Field(default_factory=list)
    countries_derived: list[str] = Field(default_factory=list)
    linkedin_org_employees: Optional[int] = None
    linkedin_org_size: Optional[str] = None
    linkedin_org_industry: Optional[str] = None
    linkedin_org_headquarters: Optional[str] = None
    linkedin_org_specialties: Optional[list[str]] = None
    linkedin_org_description: Optional[str] = None
    raw_payload: Optional[dict] = None  # full Apify row stored for audit


class JobRecord(BaseModel):
    """Persisted job row (Supabase `jobs` table)."""

    id: UUID = Field(default_factory=uuid4)
    linkedin_id: str
    title: str
    organization: str
    organization_url: Optional[str] = None
    organization_slug: Optional[str] = None
    normalized_org_name: str = ""
    date_posted: Optional[str] = None
    job_url: str
    description_text: Optional[str] = None
    employment_types: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    cities: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    org_employee_count: Optional[int] = None
    org_size_band: Optional[str] = None
    org_industry: Optional[str] = None
    org_headquarters: Optional[str] = None
    org_domain: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    run_id: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Active-client exclusion
# ─────────────────────────────────────────────────────────────────────────────

class ExclusionResult(BaseModel):
    is_excluded: bool
    matched_client: Optional[str] = None
    match_method: Optional[Literal["exact", "domain", "fuzzy", "llm"]] = None
    raw_company_name: str = ""


class ActiveClientHiringRow(BaseModel):
    """Row written to output/active_client_hiring.csv."""

    client_name: str
    matched_company_name_raw: str
    scraped_job_title: str
    scraped_job_url: str
    location: str
    posted_at: Optional[str]
    detected_at: str


# ─────────────────────────────────────────────────────────────────────────────
# ICP fit-check
# ─────────────────────────────────────────────────────────────────────────────

class ICPDecision(BaseModel):
    decision: Literal["fit", "not_fit"]
    rationale: str  # 1-3 sentences referencing website findings
    confidence: Literal["high", "medium", "low"]
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CompanyRecord(BaseModel):
    """Persisted company row (Supabase `companies` table)."""

    id: UUID = Field(default_factory=uuid4)
    normalized_name: str
    raw_name: str
    domain: Optional[str] = None
    headquarters: Optional[str] = None
    employee_count: Optional[int] = None
    size_band: Optional[str] = None  # "50-200" | "201-1000" | "1001-2000"
    industry: Optional[str] = None
    linkedin_url: Optional[str] = None
    icp_decision: Literal["fit", "not_fit"] = "not_fit"
    icp_rationale: Optional[str] = None
    icp_confidence: Optional[str] = None
    icp_checked_at: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    run_id: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Decision-maker mapping
# ─────────────────────────────────────────────────────────────────────────────

class CandidatePerson(BaseModel):
    """Raw person returned by AI Ark or Prospeo."""

    full_name: str
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    about_snippet: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    provider: Literal["ai_ark", "prospeo"] = "ai_ark"
    cascade_level: Literal["city", "country", "region", "worldwide"] = "city"


class HMValidationResult(BaseModel):
    decision: Literal["yes", "no"]
    reason: str
    validated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ContactRecord(BaseModel):
    """Persisted contact row (Supabase `contacts` table)."""

    id: UUID = Field(default_factory=uuid4)
    full_name: str
    normalized_full_name: str = ""
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    about_snippet: Optional[str] = None
    company_id: Optional[UUID] = None
    provider: str = ""
    cascade_level: str = ""
    hm_validation_decision: Optional[str] = None
    hm_validation_reason: Optional[str] = None
    found_at: datetime = Field(default_factory=datetime.utcnow)
    validated_at: Optional[str] = None
    run_id: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# DMM cache
# ─────────────────────────────────────────────────────────────────────────────

class DMMCacheKey(BaseModel):
    """Uniquely identifies a people-search call we've already made."""

    normalized_company_name: str
    title_band: str  # comma-joined sorted title list
    cascade_level: str
    provider: str


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline run summary
# ─────────────────────────────────────────────────────────────────────────────

class RunSummary(BaseModel):
    run_id: str
    started_at: str
    finished_at: Optional[str] = None
    jobs_scraped: int = 0
    jobs_persisted: int = 0
    companies_found: int = 0
    companies_excluded_active_client: int = 0
    companies_icp_fit: int = 0
    companies_icp_not_fit: int = 0
    contacts_candidates: int = 0
    contacts_validated: int = 0
    contacts_dropped: int = 0
    dmm_cache_hits: int = 0
    dmm_api_calls: int = 0
    errors: list[str] = Field(default_factory=list)
    active_client_hiring_signals: int = 0
