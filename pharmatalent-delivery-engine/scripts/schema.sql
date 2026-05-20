-- PharmaTalent Europe — Supabase schema
-- Run with:  psql $SUPABASE_DB_URL -f scripts/schema.sql
-- Or paste into the Supabase SQL Editor.
-- All statements are idempotent (IF NOT EXISTS).

-- ── jobs ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    linkedin_id         TEXT NOT NULL,
    title               TEXT NOT NULL,
    organization        TEXT NOT NULL,
    organization_url    TEXT,
    organization_slug   TEXT,
    normalized_org_name TEXT NOT NULL DEFAULT '',
    date_posted         TEXT,
    job_url             TEXT NOT NULL,
    description_text    TEXT,
    employment_types    TEXT[],
    locations           TEXT[],
    cities              TEXT[],
    countries           TEXT[],
    org_employee_count  INTEGER,
    org_size_band       TEXT,
    org_industry        TEXT,
    org_headquarters    TEXT,
    org_domain          TEXT,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id              TEXT NOT NULL DEFAULT '',
    CONSTRAINT jobs_linkedin_id_key UNIQUE (linkedin_id),
    CONSTRAINT jobs_url_key         UNIQUE (job_url)
);

-- ── companies ─────────────────────────────────────────────────────────────────
-- Stores both fit and not_fit companies for full audit trail.
-- icp_decision='fit' companies proceed to DMM; 'not_fit' are kept for rationale.
CREATE TABLE IF NOT EXISTS companies (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_name   TEXT NOT NULL,
    raw_name          TEXT NOT NULL,
    domain            TEXT,
    headquarters      TEXT,
    employee_count    INTEGER,
    size_band         TEXT,          -- '50-200' | '201-1000' | '1001-2000'
    industry          TEXT,
    linkedin_url      TEXT,
    icp_decision      TEXT NOT NULL DEFAULT 'not_fit',  -- 'fit' | 'not_fit'
    icp_rationale     TEXT,          -- 1-3 sentences from website research
    icp_confidence    TEXT,          -- 'high' | 'medium' | 'low'
    icp_checked_at    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id            TEXT NOT NULL DEFAULT '',
    CONSTRAINT companies_normalized_name_key UNIQUE (normalized_name)
);

-- ── contacts ──────────────────────────────────────────────────────────────────
-- Validated decision-makers only (hm_validation_decision = 'yes').
-- Dedup: linkedin_url primary, (normalized_full_name, company_id) fallback.
CREATE TABLE IF NOT EXISTS contacts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name               TEXT NOT NULL,
    normalized_full_name    TEXT NOT NULL DEFAULT '',
    title                   TEXT,
    linkedin_url            TEXT,
    location                TEXT,
    about_snippet           TEXT,
    company_id              UUID REFERENCES companies(id),
    provider                TEXT NOT NULL DEFAULT '',   -- 'ai_ark' | 'prospeo'
    cascade_level           TEXT NOT NULL DEFAULT '',   -- 'city' | 'country' | 'region' | 'worldwide'
    hm_validation_decision  TEXT,                       -- 'yes' | 'no'
    hm_validation_reason    TEXT,
    found_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at            TEXT,
    run_id                  TEXT NOT NULL DEFAULT '',
    CONSTRAINT contacts_linkedin_url_key  UNIQUE (linkedin_url),
    CONSTRAINT contacts_name_company_key  UNIQUE (normalized_full_name, company_id)
);

-- ── contact_jobs ──────────────────────────────────────────────────────────────
-- Many-to-many: one person can surface across multiple jobs at the same company.
-- The pipeline creates one contacts row + N contact_jobs rows.
CREATE TABLE IF NOT EXISTS contact_jobs (
    contact_id  UUID NOT NULL REFERENCES contacts(id)  ON DELETE CASCADE,
    job_id      UUID NOT NULL REFERENCES jobs(id)      ON DELETE CASCADE,
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (contact_id, job_id)
);

-- ── dmm_cache ─────────────────────────────────────────────────────────────────
-- Tracks every (company, title_band, cascade_level, provider) query.
-- Pipeline checks this before any API call — prevents re-spending AI Ark credits.
-- result_count=0 means "we searched, found nothing" — don't retry on rerun.
CREATE TABLE IF NOT EXISTS dmm_cache (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_company_name TEXT NOT NULL,
    title_band              TEXT NOT NULL,
    cascade_level           TEXT NOT NULL,
    provider                TEXT NOT NULL,
    result_count            INTEGER NOT NULL DEFAULT 0,
    queried_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT dmm_cache_key UNIQUE (normalized_company_name, title_band, cascade_level, provider)
);

-- ── pipeline_runs ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       TEXT NOT NULL UNIQUE,
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    summary_json JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_org_name    ON jobs(normalized_org_name);
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_dmm_cache_lookup ON dmm_cache(normalized_company_name, provider);
