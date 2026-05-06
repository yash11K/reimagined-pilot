"""structlog wiring + correlation-id helpers.

Goals:
- Every log line auto-carries ``request_id`` (set by the HTTP middleware)
  and any other ``contextvars`` bindings (e.g. ``job_id`` set at pipeline
  entry).
- Existing call sites use plain ``logging.getLogger(__name__).info(...)``;
  they keep working because we install structlog as a *processor chain*
  in front of the stdlib logging module rather than forcing every call
  site onto ``structlog.get_logger()``.
- In production the renderer can flip from key=value plain text to JSON
  by setting ``KB_LOG_JSON=1`` — handy once we ship to a log aggregator.

This module exposes :func:`configure_logging` (called once on startup)
and :func:`bind_log_context` (called from request middleware / pipeline).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars


def _shared_processors() -> list[structlog.types.Processor]:
    return [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.add_logger_name,
    ]


def configure_logging(*, json_output: bool | None = None) -> None:
    """Configure stdlib + structlog so every log line carries contextvars.

    Idempotent — safe to call multiple times (used by tests too).
    """
    if json_output is None:
        json_output = os.environ.get("KB_LOG_JSON", "0") == "1"

    renderer: structlog.types.Processor
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    # 1. structlog's own pipeline (used when you call structlog.get_logger())
    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 2. A stdlib formatter that runs the same processor chain — this is
    #    what lets ``logging.getLogger(__name__).info(...)`` calls inherit
    #    contextvars without rewrites.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Replace any handlers configured by uvicorn / earlier basicConfig.
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)

    # Quiet noisy third-party loggers (matches the previous _configure_logging).
    for name in ("httpx", "httpcore", "sqlalchemy.engine", "botocore", "boto3", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)


def bind_log_context(**values: Any) -> None:
    """Bind values onto the current contextvar so all subsequent logs include them.

    Typical use: ``bind_log_context(job_id=str(job_id)[:8])`` at pipeline entry.
    """
    bind_contextvars(**values)


def clear_log_context() -> None:
    """Clear all bound contextvars — call at request/task teardown."""
    clear_contextvars()
