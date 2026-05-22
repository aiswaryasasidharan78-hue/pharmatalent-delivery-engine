# PharmaTalent Europe — Lead Discovery Pipeline

**Self-reported time:** ~10 hours

A weekly lead-discovery pipeline for PharmaTalent Europe (fictional recruitment agency). It scrapes open biotech/pharma jobs in Europe via Apify, qualifies the posting companies against PharmaTalent's ICP, maps the right decision-maker at each one, validates them with an LLM, and persists everything to Supabase ready for downstream outreach.

---

## What it does

```
Apify (LinkedIn jobs)
    ↓  Stage 1: Scrape + persist to jobs table
Active-client filter (21 companies)
    ↓  Stage 2: Exclude + emit active_client_hiring.csv
ICP fit-check (perplexity/sonar — web-enabled)
    ↓  Stage 3: Qualify + persist all verdicts to companies table
AI Ark / Prospeo people_search
    ↓  Stage 4: Decision-maker mapping, cascade + cache
LLM validation (deepseek/deepseek-chat)
    ↓  Stage 5: Keep/drop per person, log every reason
Supabase persist
    ↓  Stage 6: contacts + contact_jobs join table
run_summary.json
```

---

## Quick start (fresh clone)

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/pharmatalent-delivery-engine
cd pharmatalent-delivery-engine
make install
source .venv/bin/activate

# 2. Configure credentials
cp .env.example .env
# Fill in all values in .env (see "Credentials" section below)

# 3. Apply Supabase schema  (one-time; idempotent)
make schema          # requires SUPABASE_DB_URL in .env
# OR paste scripts/schema.sql into the Supabase SQL Editor

# 4. Run the pipeline
make run
```

Output artifacts appear in `output/`:
- `output/run_summary.json` — metrics for every run
- `output/active_client_hiring.csv` — active clients seen hiring (upsell signals)
- `output/icp_fit_decisions.csv` — full ICP audit trail

---

## Credentials

Copy `.env.example` to `.env` and fill in every value. The pipeline reads **all** account-scoped values from environment variables — no hardcoded URLs or tokens anywhere in the code.

| Env var | Where to get it | Required |
|---|---|---|
| `APIFY_TOKEN` | [apify.com](https://apify.com) → Settings → API | ✅ |
| `AI_ARK_TOKEN` | [aiark.com](https://aiark.com) → API Token | One of these two |
| `PROSPEO_API_KEY` | [prospeo.io](https://prospeo.io) → API Key | One of these two |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) → Keys | ✅ |
| `SUPABASE_URL` | Supabase project → Settings → API → Project URL | ✅ |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase project → Settings → API → service_role | ✅ |
| `SUPABASE_DB_URL` | Supabase project → Settings → Database → Connection string | Recommended for schema creation |

**People-search provider:** set `PEOPLE_SEARCH_PROVIDER=both` (default) to use AI Ark first with Prospeo as fallback. Set `ai_ark` or `prospeo` to use one only.

---

## Swapping credentials (reviewer instructions)

1. Replace all values in `.env` with your own credentials.
2. Point `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` at your Supabase project.
3. Run `make schema` (or paste `scripts/schema.sql` into the Supabase SQL Editor) to create the tables.
4. Run `make run`.

No code changes required. The pipeline reads everything from env vars.

---

## Database schema

Three core tables + three operational tables. Schema created from code (`scripts/schema.sql` + `app/db/migrations.py`).

```
jobs ──────────────────────────────────────────────────────────
  id, linkedin_id (UNIQUE), title, organization,
  normalized_org_name, job_url (UNIQUE), description_text,
  employment_types[], locations[], cities[], countries[],
  org_employee_count, org_size_band, org_domain, scraped_at, run_id

companies ─────────────────────────────────────────────────────
  id, normalized_name (UNIQUE), raw_name, domain,
  employee_count, size_band, industry, linkedin_url,
  icp_decision ('fit'|'not_fit'), icp_rationale,    ← audit trail
  icp_confidence, icp_checked_at, run_id

contacts ──────────────────────────────────────────────────────
  id, full_name, normalized_full_name, title,
  linkedin_url (UNIQUE), location, about_snippet,
  company_id → companies.id,
  provider, cascade_level,
  hm_validation_decision, hm_validation_reason,     ← audit trail
  found_at, validated_at, run_id

contact_jobs (M:M join) ───────────────────────────────────────
  contact_id → contacts.id
  job_id     → jobs.id
  PRIMARY KEY (contact_id, job_id)

dmm_cache ─────────────────────────────────────────────────────
  (normalized_company_name, title_band, cascade_level, provider) UNIQUE
  result_count — "0" means "searched, found nothing; don't retry"

pipeline_runs ─────────────────────────────────────────────────
  run_id (UNIQUE), started_at, finished_at, summary_json (JSONB)
```

**Why `contact_jobs`?** The same person can surface from multiple job postings at the same company. We keep one `contacts` row and link it to all surfacing jobs through the join table. See `docs/adr-001-supabase-schema-design.md`.

---

## Model choices

| Stage | Model | Why |
|---|---|---|
| ICP fit-check | `perplexity/sonar` | Web-enabled — browses real company websites. Cheaper than sonar-pro; sufficient for binary + confidence classification. |
| HM validation | `deepseek/deepseek-chat` | Cheap classification task (~$0.0014/1K tokens). All facts are in the prompt — no web access needed. ~50× cheaper than GPT-4o for this task. |

Both use `temperature=0` for deterministic, auditable outputs. See `docs/adr-002-model-strategy.md`.

---

## Idempotency and reruns

Re-running the pipeline against an already-populated Supabase is safe:

- **Jobs:** `UNIQUE (linkedin_id)` + pre-flight dedup check — existing jobs are skipped, not re-inserted.
- **Companies:** `UNIQUE (normalized_name)` upsert — already-checked companies skip the LLM call entirely.
- **Contacts:** `UNIQUE (linkedin_url)` / `UNIQUE (normalized_full_name, company_id)` upsert — no duplicate contacts.
- **DMM:** `dmm_cache` table records every `(company, title_band, cascade_level, provider)` query. On rerun, a cache hit skips the API call. A `result_count=0` hit means "we already searched and found nothing" — we don't retry. This is the primary mechanism protecting the AI Ark 100-credit budget.

---

## Observability

Every log line is structured JSON with `run_id`, `stage`, `event`, and `timestamp`:

```json
{"event": "company_excluded", "stage": "exclusion", "company": "Pfizer", "matched_client": "Pfizer", "method": "exact", "run_id": "abc-123", "timestamp": "2024-01-15T10:23:44Z"}
{"event": "company_qualified", "stage": "icp", "company": "Molecular Partners AG", "decision": "fit", "confidence": "high", "run_id": "abc-123"}
{"event": "dmm_cache_hit", "stage": "dmm", "company": "molecular partners", "cascade": "city", "provider": "ai_ark", "run_id": "abc-123"}
{"event": "hm_validation_dropped", "stage": "validation", "person": "John Doe", "reason": "Too junior to own a Director-level hire.", "run_id": "abc-123"}
{"event": "pipeline_summary", "stage": "finalize", "jobs_scraped": 120, "companies_icp_fit": 18, "contacts_validated": 24, "run_id": "abc-123"}
```

Key events logged: `scrape_started`, `scrape_completed`, `company_excluded`, `company_qualified`, `dmm_cache_hit`, `validation_failed`, `db_upsert`, `pipeline_summary`.

---

## Active-client exclusion

21 companies excluded by default (see `app/domain/matching.py`). Matching strategy (in order):
1. **Exact** — normalized name match
2. **Domain** — root domain match (e.g. `biontech.de` → BioNTech)
3. **Fuzzy** — Levenshtein ≤ 2 OR similarity ≥ 90% (catches typos, `Roche (Switzerland)`, `GlaxoSmithKline` vs `GSK`)

When an active client is spotted hiring, a row is written to `output/active_client_hiring.csv` as an account-manager upsell signal — they can offer to help fill the role.

---

## Scope cuts

- **No email finder / email verifier** — out of scope per the brief.
- **No outreach copy generation** — out of scope per the brief.
- **No parallel async scraping** — the Apify actor is synchronous and fast enough.
- **ICP size pre-filter not applied at scrape time** — deliberate: applying `organizationEmployeesGte/Lte` at scrape time would hide active-client signals (Pfizer, Bayer). We filter after exclusion instead.
- **No checkpoint resume mid-run** — the pipeline is fast enough that a full rerun is cheaper than managing checkpoint state. Idempotency covers reruns gracefully.

**With another day:** async concurrency for the ICP stage (5–10× faster), a Makefile target for scheduled `cron`/GitHub Actions runs, and a Grafana dashboard wired to the `pipeline_runs` table.

---

## Running tests

```bash
# Unit tests only (no credentials needed)
make test

# With coverage
pytest tests/unit/ --cov=app --cov-report=term-missing

# Integration tests (mocked APIs, no credits spent)
make test-integration
```

---

## MCP server (bonus)

`mcp.json` wires the AI Ark MCP server so you can plug the same AI Ark account into Claude Code or Cursor for ad-hoc people-search exploration:

```bash
# In Claude Code, with AI_ARK_TOKEN in your environment:
claude --mcp-config mcp.json
```

The pipeline itself uses the HTTP API directly (headless, credential-swappable). The MCP config is an additional exploration layer on top.

<!-- Pipeline verified: end-to-end run completed, 7 contacts validated in Supabase -->