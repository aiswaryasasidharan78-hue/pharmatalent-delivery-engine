"""
Prospeo.io HTTP API client — POST /search-person

Correct filter keys (from Prospeo docs):
  person_job_title   — { "include": ["VP People", ...] }
  company            — { "include": ["Immatics"] }   <-- NOT company_name/company_website

Previous wrong attempts:
  company_website    — 400 (wrong key)
  company_name       — 400 (wrong key, whether string or object)
  {"include": [...]} — 400 (company_name doesn't exist at all)
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
        Search for decision-makers using POST /search-person.

        Correct Prospeo filter keys:
          "company"          -> { "include": ["CompanyName"] }
          "person_job_title" -> { "include": ["VP People", ...] }
        """
        filters: dict[str, Any] = {
            "person_job_title": {
                "include": titles[:5]
            },
            "company": {
                "include": [company_name]
            }
        }

        filters: dict[str, Any] = {
            "person_job_title": {
            "include": titles[:5]
        },
        "company": {
            "include": [company_name]
        },
        "person_location_search": {
            "include": [
                "Germany", "Switzerland", "Netherlands", "Belgium",
                "Denmark", "Sweden", "Ireland", "France",
                "United Kingdom", "Spain", "Italy", "Austria",
                "Finland", "Norway"
            ]
        }
}

        payload: dict[str, Any] = {
            "page": 1,
            "filters": filters,
        }

        logger.info(
            "prospeo_people_search",
            stage="dmm",
            company=company_name,
            titles=titles[:3],
            location=location,
            endpoint="/search-person",
            filters_sent={"company": company_name, "titles": titles[:2]},
        )

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{_BASE_URL}/search-person",
                    headers=self._headers(),
                    json=payload,
                )

                if resp.status_code in {401, 403}:
                    logger.error(
                        "prospeo_auth_error",
                        stage="dmm",
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
                    resp.raise_for_status()

                # Log raw response always — critical for debugging
                logger.info(
                    "prospeo_raw_response",
                    stage="dmm",
                    company=company_name,
                    status=resp.status_code,
                    body_preview=resp.text[:400],
                )

                resp.raise_for_status()

            data = resp.json()

            if data.get("error"):
                logger.warning(
                    "prospeo_api_error_response",
                    stage="dmm",
                    company=company_name,
                    error_code=data.get("error_code"),
                    filter_error=data.get("filter_error", data.get("message", "unknown")),
                )
                return []

            # Response: {"error": false, "results": [{"person": {...}, "company": {...}}, ...]}
            raw_results = data.get("results", [])
            people = [item.get("person", item) for item in raw_results]
            people = people[: self._max_results]

        except httpx.HTTPStatusError as e:
            logger.warning(
                "prospeo_http_error",
                stage="dmm",
                company=company_name,
                status=e.response.status_code,
                body=e.response.text[:400],
            )
            return []
        except Exception as e:
            logger.warning(
                "prospeo_request_failed",
                stage="dmm",
                company=company_name,
                error=str(e),
            )
            return []

        logger.info(
            "prospeo_people_search_done",
            stage="dmm",
            company=company_name,
            returned=len(people),
        )
        return people
