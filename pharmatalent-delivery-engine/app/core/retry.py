"""
Retry helpers built on tenacity.

Retryable:   429, timeouts, transient 5xx
Non-retryable: 400, 401, 403, 404, validation errors
"""
from __future__ import annotations

import random
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def http_retry(
    max_attempts: int = 4,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
) -> Any:
    """Decorator: retry on retryable HTTP errors with exponential backoff + jitter."""
    return retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        reraise=True,
    )
