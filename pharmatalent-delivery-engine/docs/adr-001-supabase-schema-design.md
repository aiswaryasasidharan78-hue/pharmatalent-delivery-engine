# ADR-001: Supabase Relationship Design

**Status:** Accepted  
**Date:** 2024-01-20

## Context

The pipeline produces three core entities: `jobs` (scraped from LinkedIn), `companies` (ICP-qualified), and `contacts` (validated decision-makers). The relationships between them are non-trivial:

- One company has many jobs (posted across multiple titles/locations)
- One contact belongs to one company
- One contact can surface from multiple jobs at that company
- The same person must not be duplicated even if they match 3 different job postings

## Decision

**`contact_jobs` join table (M:M between contacts and jobs)**

A contact is linked to jobs via `contact_jobs(contact_id, job_id)` with a composite primary key. This means:

- One `contacts` row per validated person (deduped on `linkedin_url`)
- N `contact_jobs` rows if the person surfaces from N jobs
- The `contacts.company_id` FK points directly to `companies` for the common case of "who are the contacts at this company?"
- Querying "which jobs surfaced this contact?" requires joining through `contact_jobs` — deliberate, not accidental

## Alternatives considered

**Option A: Denormalize — embed job references as a JSONB array in `contacts`**
Rejected. Supabase has no native operator for "append to array without duplicate" in one upsert. We'd need read-modify-write, which introduces a race condition on reruns.

**Option B: `(contact_id, job_id)` columns directly on contacts**
Rejected. Forces a new contacts row per job — breaks the "one person, one row" dedup guarantee.

**Option C: Store job IDs as TEXT[] on contacts**
Rejected. Same read-modify-write problem as Option A. Also makes the referential integrity between contacts and jobs invisible to Postgres.

## Consequences

- ICP `not_fit` companies are persisted (with rationale) in the `companies` table. This is intentional: auditors need to see why a company was dropped, not just which companies made it through.
- The `dmm_cache` table prevents re-spending API credits on reruns. It records both "we found people" (result_count > 0) and "we searched and found nothing" (result_count = 0) — the latter is equally important to cache.
- The `UNIQUE (normalized_full_name, company_id)` constraint on contacts is a fallback dedup key for people who don't have a LinkedIn URL in the people-search response.
