# ADR-002: LLM Model Strategy

**Status:** Accepted  
**Date:** 2024-01-20

## Context

The pipeline uses LLMs in two places with very different requirements:

1. **ICP fit-check** — needs to browse real company websites, reason over geography and industry, and return a structured verdict with rationale.
2. **Hiring-manager validation** — needs to classify yes/no with a one-sentence reason, given facts already in the prompt. No browsing required.

Using the same model for both would be either overkill (expensive browsing model for classification) or insufficient (cheap model can't browse websites).

## Decision

**ICP fit-check → `perplexity/sonar` (web-enabled)**

- Reasons: perplexity/sonar can browse the live web, which is required by the spec ("must include a website-research step"). It's cheaper than sonar-pro and has sufficient reasoning quality for binary + confidence classification. `temperature=0` for deterministic outputs.
- Alternative considered: `openai/gpt-4o:online` — more capable but ~10× the cost per call. Overkill for this classification task.
- Alternative considered: `perplexity/sonar-pro` — better reasoning, but 3× the cost of sonar. Not justified for binary fit/not_fit.

**Hiring-manager validation → `deepseek/deepseek-chat`**

- Reasons: This is a pure classification task (yes/no + one sentence). The facts are all in the prompt — no web access needed. deepseek/deepseek-chat is ~$0.0014 per 1K tokens, ~50× cheaper than GPT-4o, and at `temperature=0` produces consistent structured JSON. We run this once per candidate person, so cost compounds fast at scale.
- Alternative considered: `anthropic/claude-haiku` — excellent at structured output, ~5× more expensive than DeepSeek for this task.
- Alternative considered: `mistralai/mistral-7b-instruct` — free tier available, but JSON adherence is less reliable without function calling.

## AI Governance

All LLM outputs are:
- Persisted with their rationale in Supabase (`icp_rationale`, `hm_validation_reason`)
- `temperature=0` across all calls for reproducibility
- Parsed defensively — malformed JSON falls back to `not_fit`/`no` rather than crashing
- Never the sole source of factual data — the LLM reasons over API-retrieved facts, not general knowledge alone
