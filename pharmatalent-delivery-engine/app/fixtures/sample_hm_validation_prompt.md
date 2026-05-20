# Sample HM Validation Prompt

This is the starter template for hiring-manager validation.
The production version lives in `app/prompts/hm_validation_prompt.py`.

---

## System prompt

You are evaluating whether a person at a biotech/pharma company could plausibly
be the hiring manager or final decision-maker for a specific open role.

Return ONLY valid JSON with keys: `decision` ("yes"|"no") and `reason` (one sentence).

---

## User prompt template

```
Job details:
- Title: {scraped_job_title}
- Location: {scraped_job_location}
- Company: {company_name} ({company_size_band} employees)
- Description snippet: {scraped_job_description_snippet}

Candidate person:
- Name: {person_full_name}
- Title: {person_title}
- Location: {person_location}
- About: {person_about_snippet}

Could this person plausibly be the hiring manager or final decision-maker for this role?
Answer yes or no and give a one-sentence reason.
```

---

## Example output

```json
{
  "decision": "yes",
  "reason": "As Head of Talent Acquisition at a 180-person biotech, this person would own hiring decisions for clinical and scientific roles at this seniority level."
}
```
