"""
Prospeo.io HTTP API client.

Free tier: 100 credits, 25 people per credit → ~2,500 people available.
We still cap at max_results=2 at the pipeline level (LLM validation budget).

Used as:
  - Alternative primary (if PEOPLE_SEARCH_PROVIDER=prospeo)
  - Fallback (if PEOPLE_SEARCH_PROVIDER=both and AI Ark returns nothing)
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.prospeo.io"


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


class ProspeoClient:
    def __init__(self) -> None:
        cfg = get_settings()
        self._api_key = cfg.prospeo_api_key
        self._max_results = cfg.people_search_max_results  # hard cap = 2

    def _headers(self) -> dict[str, str]:
        return {
            "X-KEY": self._api_key,
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
        Search for people at a company.  Returns at most max_results people.
        Prospeo's /linkedin-search or /company-search endpoint.
        """
        # Prospeo's search: POST /linkedin-search with job_title + company
        results: list[dict] = []
        for title in titles[: 3]:  # try top 3 titles max
            payload: dict[str, Any] = {
                "job_title": title,
                "company": company_domain or company_name,
                "limit": self._max_results,
            }
            if location:
                payload["location"] = location

            logger.info(
                "prospeo_people_search",
                stage="dmm",
                company=company_name,
                title=title,
                location=location,
            )

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{_BASE_URL}/linkedin-search",
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code in {401, 403}:
                    logger.error("prospeo_auth_error", status=resp.status_code)
                    resp.raise_for_status()
                resp.raise_for_status()

            data = resp.json()
            people = data.get("response", data.get("results", []))
            results.extend(people)
            if len(results) >= self._max_results:
                break

        results = results[: self._max_results]
        logger.info(
            "prospeo_people_search_done",
            stage="dmm",
            company=company_name,
            returned=len(results),
        )
        return results
