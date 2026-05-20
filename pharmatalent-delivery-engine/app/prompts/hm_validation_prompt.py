"""
Hiring-manager validation prompt for deepseek/deepseek-chat.

Cheap, deterministic classification: yes/no + one-sentence reason.
Runs once per candidate person returned by people_search.
"""
from __future__ import annotations

HM_VALIDATION_SYSTEM_PROMPT = """You are evaluating whether a person at a biotech/pharma company
could plausibly be the hiring manager or final decision-maker for a specific open role.

Consider:
- Does their seniority level match the role? (they should be able to hire for it)
- Is their functional area relevant? (e.g. Head of Talent for a clinical hire is plausible)
- Is their location compatible with the job location?

Return ONLY valid JSON — no markdown, no explanation outside the JSON.

Required JSON structure:
{
  "decision": "yes" | "no",
  "reason": "<one sentence explaining the decision>"
}"""


def build_hm_prompt(data: dict) -> str:
    return f"""Job details:
- Title: {data.get('scraped_job_title', 'N/A')}
- Location: {data.get('scraped_job_location', 'N/A')}
- Company: {data.get('company_name', 'N/A')} ({data.get('company_size_band', 'N/A')} employees)
- Description snippet: {data.get('scraped_job_description_snippet', 'N/A')[:500]}

Candidate person:
- Name: {data.get('person_full_name', 'N/A')}
- Title: {data.get('person_title', 'N/A')}
- Location: {data.get('person_location', 'N/A')}
- About: {data.get('person_about_snippet', 'N/A')[:300] if data.get('person_about_snippet') else 'N/A'}

Could this person plausibly be the hiring manager or final decision-maker for this role?
Answer yes or no and give a one-sentence reason."""
