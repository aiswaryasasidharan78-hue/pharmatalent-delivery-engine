"""
Structured JSON logging.  Every log record carries:
  run_id  — pipeline correlation ID
  stage   — which pipeline stage emitted the log
  event   — what happened

Use get_logger(__name__) everywhere.  Never use print().
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
import logging

logging.basicConfig(level=logging.INFO)

# Context variable so run_id propagates across async tasks automatically
_run_id_var: ContextVar[str] = ContextVar("run_id", default="")


def set_run_id(run_id: str) -> None:
    _run_id_var.set(run_id)


def get_run_id() -> str:
    return _run_id_var.get() or str(uuid.uuid4())


def _add_run_id(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    rid = _run_id_var.get()
    if rid:
        event_dict["run_id"] = rid
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Call once at pipeline startup."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_run_id,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:  # type: ignore[type-arg]
    return structlog.get_logger(name)
