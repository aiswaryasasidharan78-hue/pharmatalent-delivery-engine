"""
Supabase schema creation — idempotent DDL.

Strategy (in priority order):
  1. Direct Postgres via SUPABASE_DB_URL (most reliable, full DDL support)
  2. Supabase Management API SQL endpoint (/sql)
  3. Warn and continue — schema may already exist from a previous run

All statements use CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
so re-running never fails.

Tables:
  jobs           scraped LinkedIn jobs
  companies      ICP-qualified + not_fit companies (audit trail)
  contacts       validated decision-makers
  contact_jobs   M:M join — contacts ↔ jobs
  dmm_cache      (company, title_band, cascade, provider) query log — credit guard
  pipeline_runs  run metadata + summary JSON
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# DDL — split into individual statements so we can execute one at a time
# ---------------------------------------------------------------------------
_DDL_STATEMENTS: list[str] = [
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS companies (
        id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        normalized_name   TEXT NOT NULL,
        raw_name          TEXT NOT NULL,
        domain            TEXT,
        headquarters      TEXT,
        employee_count    INTEGER,
        size_band         TEXT,
        industry          TEXT,
        linkedin_url      TEXT,
        icp_decision      TEXT NOT NULL DEFAULT 'not_fit',
        icp_rationale     TEXT,
        icp_confidence    TEXT,
        icp_checked_at    TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        run_id            TEXT NOT NULL DEFAULT '',
        CONSTRAINT companies_normalized_name_key UNIQUE (normalized_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contacts (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        full_name               TEXT NOT NULL,
        normalized_full_name    TEXT NOT NULL DEFAULT '',
        title                   TEXT,
        linkedin_url            TEXT,
        location                TEXT,
        about_snippet           TEXT,
        company_id              UUID REFERENCES companies(id),
        provider                TEXT NOT NULL DEFAULT '',
        cascade_level           TEXT NOT NULL DEFAULT '',
        hm_validation_decision  TEXT,
        hm_validation_reason    TEXT,
        found_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        validated_at            TEXT,
        run_id                  TEXT NOT NULL DEFAULT '',
        CONSTRAINT contacts_linkedin_url_key    UNIQUE (linkedin_url),
        CONSTRAINT contacts_name_company_key    UNIQUE (normalized_full_name, company_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contact_jobs (
        contact_id  UUID NOT NULL REFERENCES contacts(id)  ON DELETE CASCADE,
        job_id      UUID NOT NULL REFERENCES jobs(id)      ON DELETE CASCADE,
        linked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (contact_id, job_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dmm_cache (
        id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        normalized_company_name TEXT NOT NULL,
        title_band              TEXT NOT NULL,
        cascade_level           TEXT NOT NULL,
        provider                TEXT NOT NULL,
        result_count            INTEGER NOT NULL DEFAULT 0,
        queried_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT dmm_cache_key UNIQUE (normalized_company_name, title_band, cascade_level, provider)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id       TEXT NOT NULL UNIQUE,
        started_at   TIMESTAMPTZ NOT NULL,
        finished_at  TIMESTAMPTZ,
        summary_json JSONB,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # Indexes — IF NOT EXISTS requires Postgres 9.5+; Supabase is on 15.x
    "CREATE INDEX IF NOT EXISTS idx_jobs_org_name    ON jobs(normalized_org_name)",
    "CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain)",
    "CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id)",
    "CREATE INDEX IF NOT EXISTS idx_dmm_cache_lookup ON dmm_cache(normalized_company_name, provider)",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_migrations() -> None:
    """Apply schema DDL.  Safe to call on every pipeline startup."""
    cfg = get_settings()
    logger.info("migrations_started", stage="init")

    if cfg.supabase_db_url:
        _apply_via_direct_postgres(cfg.supabase_db_url)
    else:
        _apply_via_management_api(cfg.supabase_url, cfg.supabase_service_role_key)

    logger.info("migrations_completed", stage="init")


# ---------------------------------------------------------------------------
# Strategy 1 — Direct Postgres (preferred when SUPABASE_DB_URL is set)
# ---------------------------------------------------------------------------

def _apply_via_direct_postgres(db_url: str) -> None:
    try:
        import psycopg2  # type: ignore
    except ImportError:
        logger.warning("psycopg2_not_available_falling_back_to_api")
        from app.core.config import get_settings
        cfg = get_settings()
        _apply_via_management_api(cfg.supabase_url, cfg.supabase_service_role_key)
        return

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for stmt in _DDL_STATEMENTS:
            s = stmt.strip()
            if s:
                cur.execute(s)
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Strategy 2 — Supabase Management API  (POST /rest/v1/rpc  is for app RPCs;
#              the SQL endpoint is /pg/query on the management plane — but that
#              requires a management token we don't have.
#
#              The *practical* alternative: ship a SQL migration file and tell
#              users to run  supabase db push  OR  psql.  We still attempt the
#              RPC path so fully-automated runs work when the DB URL is present.
# ---------------------------------------------------------------------------

def _apply_via_management_api(supabase_url: str, service_key: str) -> None:
    """
    Attempt DDL via Supabase's undocumented but stable SQL execution path.
    Falls back to printing instructions if it doesn't work (e.g. hosted projects
    without DB URL).  The pipeline will still function if schema already exists.
    """
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    all_ok = True
    for stmt in _DDL_STATEMENTS:
        s = stmt.strip()
        if not s:
            continue
        try:
            with httpx.Client(timeout=30.0) as http:
                # Supabase exposes a SQL endpoint at /rest/v1/rpc/exec_sql
                # only if you've created that function.  Instead we use the
                # internal pg/query endpoint available on all projects.
                resp = http.post(
                    f"{supabase_url}/rest/v1/rpc/exec_sql",
                    headers=headers,
                    json={"sql": s},
                )
                if resp.status_code == 404:
                    # RPC function not defined — try direct Supabase SQL API
                    resp2 = http.post(
                        f"{supabase_url}/pg/query",
                        headers=headers,
                        json={"query": s},
                    )
                    if resp2.status_code not in {200, 201, 204}:
                        all_ok = False
                elif resp.status_code not in {200, 201, 204}:
                    all_ok = False
        except Exception as exc:
            logger.warning("migration_stmt_error", error=str(exc), sql=s[:60])
            all_ok = False

    if not all_ok:
        logger.warning(
            "migration_api_incomplete",
            hint=(
                "Set SUPABASE_DB_URL in your .env for reliable schema creation, "
                "or run:  psql $SUPABASE_DB_URL -f scripts/schema.sql"
            ),
        )
