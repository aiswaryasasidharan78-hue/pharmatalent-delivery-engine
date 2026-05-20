"""
AI Ark HTTP API client.

⚠️  FREE TIER = 100 credits.  One returned person = one credit.
Rules enforced here:
  - max_results=2 per call (hard cap from DMM.md)
  - Caller (dmm_service) must check the cache before calling this
  - Retries on 429/5xx only; auth failures propagate immediately
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.aiark.com/v1"


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


class AIArkClient:
    def __init__(self) -> None:
        cfg = get_settings()
        self._token = cfg.ai_ark_token
        self._max_results = cfg.people_search_max_results  # hard cap = 2

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=20),
        reraise=True,
    )
    def people_search(
        self,
        company_name: str,
        company_domain: str | None,
        titles: list[str],
        location: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for people at a company with given titles and location.
        Returns at most self._max_results (2) people — credit budget protection.
        """
        payload: dict[str, Any] = {
            "company_name": company_name,
            "titles": titles,
            "limit": self._max_results,
        }
        if company_domain:
            payload["company_domain"] = company_domain
        if location:
            payload["location"] = location

        logger.info(
            "ai_ark_people_search",
            stage="dmm",
            company=company_name,
            location=location,
            title_count=len(titles),
        )

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{_BASE_URL}/people/search",
                headers=self._headers(),
                json=payload,
            )
            # 401/403 → auth failure, let it propagate
            if resp.status_code in {401, 403}:
                logger.error(
                    "ai_ark_auth_error",
                    stage="dmm",
                    status=resp.status_code,
                )
                resp.raise_for_status()
            resp.raise_for_status()

        data = resp.json()
        people = data.get("people", data.get("results", data if isinstance(data, list) else []))
        # Enforce credit cap defensively
        people = people[: self._max_results]

        logger.info(
            "ai_ark_people_search_done",
            stage="dmm",
            company=company_name,
            returned=len(people),
        )
        return people
