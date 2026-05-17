"""Structured JSON logging with contextvars (job_id, clip_id, stage)."""
from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_CONFIGURED = False


def configure_logging(logs_dir: Path, level: str = "INFO") -> None:
    """Idempotent: safe to call from tests and the lifespan handler."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logs_dir.mkdir(parents=True, exist_ok=True)

    handlers: list[logging.Handler] = []

    file_handler = TimedRotatingFileHandler(
        logs_dir / "pipeline.jsonl",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(stderr_handler)

    logging.basicConfig(level=level, format="%(message)s", handlers=handlers, force=True)

    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)


def bind_job(job_id: str, clip_id: str) -> None:
    bind_contextvars(job_id=job_id, clip_id=clip_id)


def bind_stage(stage: str) -> None:
    bind_contextvars(stage=stage)


def clear_log_context() -> None:
    clear_contextvars()
