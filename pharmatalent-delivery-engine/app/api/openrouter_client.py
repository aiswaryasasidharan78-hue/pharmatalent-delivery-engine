"""
OpenRouter client.

Two models used:
  - icp_model (perplexity/sonar): web-enabled, reads company websites.
    Used for ICP fit-check — costs more per call.
  - hm_validation_model (deepseek/deepseek-chat): cheap classification.
    Used for hiring-manager validation — runs once per candidate person.

Both are called via the standard OpenAI-compatible messages endpoint.
temperature=0 everywhere for deterministic, auditable outputs.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenRouterClient:
    def __init__(self) -> None:
        cfg = get_settings()
        self._api_key = cfg.openrouter_api_key
        self._base_url = cfg.openrouter_base_url
        self._icp_model = cfg.icp_model
        self._hm_model = cfg.hm_validation_model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pharmatalent-delivery-engine",
            "X-Title": "PharmaTalent Europe Pipeline",
        }

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.TransportError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=2, max=30),
        reraise=True,
    )
    def _chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # ── ICP fit-check (web-enabled) ──────────────────────────────────────────

    def icp_fit_check(self, company_name: str, company_domain: str | None) -> dict:
        """
        Uses perplexity/sonar (web-enabled) to research the company website
        and return a structured ICP verdict.

        Returns a dict with keys: decision, rationale, confidence
        """
        from app.prompts.icp_prompt import build_icp_prompt, ICP_SYSTEM_PROMPT

        user_prompt = build_icp_prompt(company_name, company_domain)

        logger.info(
            "icp_check_started",
            stage="icp",
            company=company_name,
            model=self._icp_model,
        )

        raw = self._chat(
            model=self._icp_model,
            system_prompt=ICP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=512,
        )

        result = _parse_json_response(raw)
        logger.info(
            "icp_check_completed",
            stage="icp",
            company=company_name,
            decision=result.get("decision"),
            confidence=result.get("confidence"),
        )
        return result

    # ── Hiring-manager validation (cheap model) ──────────────────────────────

    def validate_hiring_manager(self, prompt_data: dict) -> dict:
        """
        Uses deepseek/deepseek-chat to classify whether a person could be the
        hiring manager for the scraped job.

        Returns a dict with keys: decision ("yes"|"no"), reason
        """
        from app.prompts.hm_validation_prompt import (
            build_hm_prompt,
            HM_VALIDATION_SYSTEM_PROMPT,
        )

        user_prompt = build_hm_prompt(prompt_data)

        logger.info(
            "hm_validation_started",
            stage="validation",
            person=prompt_data.get("person_full_name"),
            model=self._hm_model,
        )

        raw = self._chat(
            model=self._hm_model,
            system_prompt=HM_VALIDATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=256,
        )

        result = _parse_json_response(raw)
        logger.info(
            "hm_validation_completed",
            stage="validation",
            person=prompt_data.get("person_full_name"),
            decision=result.get("decision"),
        )
        return result


def _parse_json_response(raw: str) -> dict:
    """
    Safely parse JSON from an LLM response.
    Strips markdown code fences before parsing.
    Falls back to an error dict if parsing fails.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
    # Find the first JSON object in the response
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("llm_json_parse_failed", raw_response=raw[:300])
        return {"decision": "not_fit", "rationale": raw[:300], "confidence": "low"}
