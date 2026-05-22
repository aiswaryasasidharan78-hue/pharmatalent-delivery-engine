"""
Hiring-manager validation prompt.

Key insight: PharmaTalent sells to Talent/People/HR leaders who OWN ALL HIRING
at their company — including clinical, regulatory, and medical roles.
A "VP People" at a biotech IS the right target for a "Director Regulatory Affairs"
role. The prompt must reflect this or it will drop every valid contact.

Location rule: EU/UK is compatible with EU/UK. Don't drop someone in London
for a job in Germany — they may manage pan-European hiring remotely.
"""
from __future__ import annotations

HM_VALIDATION_SYSTEM_PROMPT = """You are evaluating whether a person at a biotech/pharma company
could plausibly be the hiring manager or key decision-maker for an open role.

CRITICAL CONTEXT: PharmaTalent Europe is a recruitment agency. Their clients are
Talent, People, and HR leaders at biotech/pharma companies. These people OWN ALL
HIRING at their company — including clinical, regulatory, pharmacovigilance, and
medical affairs roles. A VP People or Head of Talent at a biotech is EXACTLY the
right person regardless of whether the open role is in regulatory affairs, clinical
operations, or any other function.

Evaluation rules:
1. SENIORITY: The person must be senior enough to approve or own hiring (VP, Director,
   Head, Senior Director level or above). A junior HR coordinator is NOT a match.
2. FUNCTION: Talent/People/HR leaders are ALWAYS relevant for ANY open role.
   Functional heads (Director Regulatory Affairs, Head of Clinical Ops) are also
   valid if the open role is in their department.
3. LOCATION: Being in the same country OR anywhere in Europe/UK is sufficient.
   Reject ONLY if the person is clearly US-only, Asia-only, or another non-EU region
   with no European remit mentioned.

Return ONLY valid JSON — no markdown, no text outside the JSON object.

Required JSON structure:
{
  "decision": "yes" | "no",
  "reason": "<one sentence explaining the decision>"
}"""


def build_hm_prompt(data: dict) -> str:
    return f"""Open role at {data.get('company_name', 'N/A')}:
- Job title: {data.get('scraped_job_title', 'N/A')}
- Job location: {data.get('scraped_job_location', 'N/A')}
- Company size: {data.get('company_size_band', 'N/A')} employees
- Description: {data.get('scraped_job_description_snippet', 'N/A')[:400]}

Candidate person:
- Name: {data.get('person_full_name', 'N/A')}
- Title: {data.get('person_title', 'N/A')}
- Location: {data.get('person_location', 'N/A')}
- About: {(data.get('person_about_snippet') or 'N/A')[:300]}

Is this person a plausible hiring manager or key decision-maker for this role?
Remember: Talent/HR/People leaders own ALL hiring at their company.
Answer yes or no with one sentence."""
