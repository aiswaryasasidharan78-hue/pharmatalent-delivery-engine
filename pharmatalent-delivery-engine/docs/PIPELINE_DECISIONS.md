# Pipeline Architecture Decisions

This document records the key architectural decisions made during the design and implementation of the PharmaTalent Europe Lead Discovery Pipeline, along with the rationale behind each choice.

---

## 1. Sequential Stage Design Over Distributed Orchestration

**Decision:** The pipeline runs as a single Python process with six sequential stages, not as a distributed system with message queues or worker pools.

**Rationale:** The pipeline is designed for weekly batch runs processing ~100–500 companies in 5–10 minutes. Sequential execution is straightforward to debug when a stage fails mid-run, requires no infrastructure (no Redis, Celery, or worker processes), and is deterministic. Partial concurrency via `asyncio.Semaphore(5)` is used within each stage to respect external API rate limits without the operational complexity of full async pipelines.

**Rejected alternatives:** Celery + Redis (unnecessary infrastructure overhead), full async concurrency (complicates stack traces and debugging).

---

## 2. Typed Pydantic Models as Stage Contracts

**Decision:** All data crossing stage boundaries is typed via Pydantic models, never raw dicts.

**Rationale:** Each stage emits and consumes a specific model (`ScrapedJob` → `JobRecord` → `CandidateCompany` → `CompanyRecord` → `CandidatePerson` → `ContactRecord`). This enforces clear contracts between stages, surfaces schema mismatches at parse time rather than at downstream write time, and makes refactoring safe.

---

## 3. All Companies Persisted (Fit and Not-Fit)

**Decision:** Every company that passes active-client exclusion is written to the `companies` table regardless of ICP verdict, with the full LLM rationale stored alongside the decision.

**Rationale:** Storing rejected companies with their rationale provides a searchable audit trail, prevents redundant LLM calls on reruns (upsert skips re-evaluation if a row exists), and surfaces useful data for refining ICP criteria over time.

---

## 4. `contact_jobs` Many-to-Many Join Table

**Decision:** The relationship between contacts and job postings is modelled as a separate `contact_jobs` join table rather than denormalizing job references into the `contacts` row.

**Rationale:** The same decision-maker at a company can be surfaced by multiple job postings across different pipeline runs. A join table avoids read-modify-write race conditions on reruns (no array-append needed), maintains a strict 1:1 person-to-contact deduplication guarantee, and makes the "which jobs surfaced this contact?" query an explicit join rather than an implicit array scan.

---

## 5. DMM Cache for People-Search Budget Protection

**Decision:** Every decision-maker mapping (DMM) query result — including "no results found" — is cached in the `dmm_cache` table keyed on `(company, title_band, cascade_level, provider)`.

**Rationale:** AI Ark provides 100 credits per run (~100 people). Without a cache, reruns on the same company set would exhaust the budget immediately. Caching "no results" responses is equally important: it prevents the pipeline from re-querying a dead end and consuming credits on a known-empty search.

---

## 6. Geographic Cascade Strategy for Decision-Maker Mapping

**Decision:** People searches use a four-level geographic fallback: city → country → region → worldwide, stopping on the first level that returns results.

**Rationale:** Pharma companies with a small local footprint often list employees under a parent-company country or EMEA region rather than a specific city. Cascading from narrow to broad maximises the chance of finding a relevant contact without skipping straight to a worldwide search that returns high-noise results.

---

## 7. Model Selection — Perplexity Sonar for ICP, DeepSeek for HM Validation

**Decision:** ICP fit-checking uses `perplexity/sonar` (web-enabled) via OpenRouter; hiring-manager validation uses `deepseek/deepseek-chat`.

**Rationale:**
- ICP fit-checking requires browsing the company's live website to verify pipeline activity, funding stage, and headcount — Perplexity Sonar's web retrieval capability is essential here.
- Hiring-manager validation is a binary classification (`yes`/`no`) over facts already in the prompt (title, company, job description). No browsing is needed, so the ~50× cheaper DeepSeek model is preferred.
- Both models run at `temperature=0` for deterministic, auditable outputs.

**Rejected alternatives:** GPT-4o for both tasks (cost prohibitive at scale), LangChain agents (obscures data flow, adds framework complexity).

---

## 8. AI Ark Primary / Prospeo Fallback for People Search

**Decision:** Decision-maker mapping attempts AI Ark first and falls back to Prospeo only when AI Ark returns no results.

**Rationale:** AI Ark provides richer profile data but carries a tighter credit budget (~100 credits). Prospeo covers a much broader dataset (~2,500 people per 100 credits) and serves as a safety net for companies that AI Ark cannot resolve. The cascade is transparent: the `provider` column in `dmm_cache` and `contacts` records which source surfaced each person.

---

## 9. Idempotent Upserts on Natural Keys

**Decision:** All database writes use upsert semantics on domain-meaningful natural keys:
- `jobs` → `linkedin_id`
- `companies` → `normalized_name`
- `contacts` → `linkedin_url`, with `(normalized_full_name, company_id)` as a composite fallback when a LinkedIn URL is absent

**Rationale:** The pipeline is designed to be safely rerunnable without manual cleanup. Natural-key deduplication means that a partial run (e.g., interrupted after Stage 3) can be resumed without duplicating data or re-invoking expensive LLM or API calls for records already committed.

---

## 10. Active-Client Exclusion With Fuzzy Matching and Upsell Signal

**Decision:** The 16 hardcoded active clients are matched using a three-tier strategy — exact name, root domain substring, then Levenshtein/similarity fuzzy match — before any LLM or API call is made. Matches write a row to `output/active_client_hiring.csv`.

**Rationale:** ICP evaluation against existing clients wastes LLM credits and pollutes the lead database. The fuzzy tier catches common name variations ("Pfizer Inc." vs. "Pfizer"). The CSV output turns an exclusion into an actionable upsell signal for account managers — the pipeline deliberately produces value from every company it touches, including those it filters out.

---

## 11. Structured JSON Logging With Run-ID Threading

**Decision:** Every log line is emitted as a structured JSON object with `event`, `stage`, `run_id`, and `timestamp` fields.

**Rationale:** Structured logs can be queried programmatically (e.g., `jq '.[] | select(.event == "validation_dropped")'`) to audit decisions without reading prose. Threading `run_id` through every log entry makes it trivial to isolate a specific run's trace when multiple runs are stored together.

---

## 12. Environment-Driven Configuration With Pydantic Settings

**Decision:** All credentials, project IDs, and account-scoped URLs are read from environment variables and validated at startup via a Pydantic `Settings` class. No secrets are hardcoded anywhere.

**Rationale:** Pydantic validation fails fast with a clear error message if a required variable is missing, preventing silent misconfiguration. Environment-driven config makes the pipeline portable across machines without code changes and simplifies credential rotation.

---

## 13. Defensive JSON Parsing With Safe Defaults

**Decision:** LLM responses are parsed with a try/except that falls back to a safe default on malformed JSON: `not_fit` for ICP decisions, `no` for hiring-manager validation.

**Rationale:** LLMs occasionally return markdown-fenced JSON, partial responses, or prose instead of the requested structure. Rather than crashing the pipeline and losing the run's progress, the error is logged, counted in `RunSummary.errors`, and the stage continues. The conservative default (reject rather than accept) is intentional — it prevents unqualified leads from reaching the outreach database due to a parse failure.

---

## 14. Deliberate Scope Exclusions

The following capabilities were evaluated and explicitly left out of v1:

| Capability | Reason Excluded |
|---|---|
| Email finder / verifier | Out of scope for lead discovery; belongs in outreach tooling |
| Outreach copy generation | Separate concern; left to the CRM layer |
| Checkpoint / resume mid-run | A full rerun is cheaper than managing distributed state; idempotent upserts make reruns safe |
| ICP size filter at scrape time | Large active clients (e.g., Pfizer) would be excluded before generating the upsell CSV |
| Async concurrency across all stages | Adds debugging complexity that outweighs the ~5× speedup for a weekly batch job |
