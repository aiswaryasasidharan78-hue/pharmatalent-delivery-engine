"""
ICP fit-check prompt for perplexity/sonar (web-enabled).

The model must browse the company website and return structured JSON.
temperature=0 for deterministic, auditable outputs.
"""
from __future__ import annotations

from app.domain.icp_config import (
    TARGET_INDUSTRIES,
    DISQUALIFIERS,
    MIN_EMPLOYEES,
    MAX_EMPLOYEES,
)

ICP_SYSTEM_PROMPT = """You are a biotech/pharma industry analyst evaluating whether a company
fits a specific ideal customer profile (ICP).

You MUST browse the company's website and LinkedIn page to gather real information.
Do NOT rely solely on general knowledge.

Return ONLY valid JSON — no markdown fences, no preamble, no explanation outside the JSON object.

Required JSON structure:
{
  "decision": "fit" | "not_fit",
  "rationale": "<1-3 sentences referencing specific website findings>",
  "confidence": "high" | "medium" | "low"
}"""


def build_icp_prompt(company_name: str, company_domain: str | None) -> str:
    domain_hint = f" (website: {company_domain})" if company_domain else ""
    industries_str = ", ".join(TARGET_INDUSTRIES[:10])
    disqualifiers_str = ", ".join(DISQUALIFIERS[:8])

    return f"""Evaluate whether this company fits the ICP for PharmaTalent Europe,
a recruitment agency placing PhD-level pharmacists, regulatory affairs leads,
clinical operations managers, and clinical research scientists.

Company: {company_name}{domain_hint}

ICP criteria (ALL must be met):
1. Industry: One of [{industries_str}]
2. Company size: {MIN_EMPLOYEES}–{MAX_EMPLOYEES} employees globally
3. Geography: Must have at least one operational/hiring presence in EU/EEA/UK/Switzerland/Norway
   (US, Japanese, Korean, or Chinese companies with a European office/subsidiary ARE in scope)

Automatic disqualifiers (ANY one → not_fit):
[{disqualifiers_str}]

Steps:
1. Search for and browse the company's website and LinkedIn page
2. Check their employee count, office locations, and business focus
3. Look for: EU subsidiary, EU office address, European job postings, or EU legal entity

Return your verdict as JSON only."""
