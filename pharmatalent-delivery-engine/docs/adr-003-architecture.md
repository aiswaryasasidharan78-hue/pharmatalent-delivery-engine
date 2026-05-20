# ADR-003: Architectural Style — Modular Monolith

**Status:** Accepted  
**Date:** 2024-01-20

## Context

The pipeline needs to be deliverable in ~3 days, runnable by a reviewer who swaps in their own credentials, debuggable when something fails mid-run, and extensible to a second client.

## Decision

**Modular Monolith with Sequential Pipeline**

One Python process, six sequential stages, each with typed inputs and typed outputs. No distributed orchestration, no task queues, no microservices.

```
main.py → orchestrator.py
  Stage 1: scrape_service
  Stage 2: exclusion_service
  Stage 3: icp_fit_service
  Stage 4: dmm_service
  Stage 5: hm_validation_service
  Stage 6: persistence_service
  Finalize: summary_service
```

## Alternatives considered

**LangChain agents** — rejected. Adds a framework dependency that obscures the data flow, makes debugging harder, and is unnecessary for a deterministic sequential pipeline.

**Celery + Redis task queue** — rejected. Adds two new infrastructure dependencies (Redis, worker processes), complicates the reviewer's setup (they'd need to run multiple processes), and provides no benefit at the volume this pipeline operates at.

**Async concurrency via asyncio** — partially adopted. The `asyncio.Semaphore(5)` cap is used to limit concurrent API calls within a stage, but the pipeline stages themselves are sequential. This gives us rate-limit safety without the complexity of a fully async pipeline.

## Consequences

- Each stage is independently testable with mocked inputs/outputs
- Failures in one stage cause an early exit with a meaningful error in `run_summary.json`
- Adding a new client means adding a new ICP config file and swapping the `icp_config.py` import — no architectural change
- At 100+ companies per run, the pipeline will take ~5-10 minutes (LLM calls dominate). This is acceptable for a weekly scheduled job. If latency becomes an issue, Stage 3 (ICP) is the natural place to parallelize first.
