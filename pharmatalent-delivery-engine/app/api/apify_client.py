"""
Apify client — wraps the fantastic.jobs LinkedIn Jobs API actor.

Actor ID: vIGxjRrHqDTPuE6M4
Runs synchronously (blocks until dataset is ready).
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.icp_config import (
    TITLE_SEARCHES,
    LOCATION_SEARCHES,
    EMPLOYMENT_TYPE_FILTERS,
)

logger = get_logger(__name__)

_ACTOR_ID = "vIGxjRrHqDTPuE6M4"


class ApifyClient:
    def __init__(self) -> None:
        cfg = get_settings()
        self._token = cfg.apify_token
        self._actor_id = cfg.apify_actor_id
        self._max_items = cfg.max_scrape_items
        self._time_range = cfg.scrape_time_range

    def _build_input(self) -> dict[str, Any]:
        return {
            "titleSearch": TITLE_SEARCHES,
            "locationSearch": LOCATION_SEARCHES,
            "EmploymentTypeFilter": EMPLOYMENT_TYPE_FILTERS,
            "timeRange": self._time_range,
            "removeAgency": True,
            "descriptionType": "text",
            "maxItems": self._max_items,
            "includeAi": False,
        }

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(min=2, max=30),
        reraise=True,
    )
    def scrape_jobs(self) -> list[dict[str, Any]]:
        """
        Run the Apify actor synchronously and return raw job rows.
        Uses the run-sync-get-dataset-items endpoint so we get results in one
        blocking call — no polling needed.
        """
        actor_input = self._build_input()
        url = (
            f"https://api.apify.com/v2/acts/{self._actor_id}"
            f"/run-sync-get-dataset-items?token={self._token}"
        )

        logger.info(
            "apify_scrape_started",
            stage="scrape",
            actor_id=self._actor_id,
            max_items=self._max_items,
            time_range=self._time_range,
        )

        with httpx.Client(timeout=300.0) as client:
            response = client.post(
                url,
                json=actor_input,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

        items: list[dict[str, Any]] = response.json()
        logger.info(
            "apify_scrape_completed",
            stage="scrape",
            job_count=len(items),
        )
        return items


def load_fixture_jobs(path: str = "app/fixtures/sample_apify_jobs.json") -> list[dict]:
    """Fallback: load scrape results from a local fixture file."""
    with open(path) as f:
        return json.load(f)
