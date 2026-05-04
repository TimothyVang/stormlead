"""structured logging via structlog. json output in prod, pretty in dev."""

from __future__ import annotations

import logging
import re
import os
import sys

import structlog

_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE_RE = re.compile(r"\+?1?[-.\s()]*(\d{3})[-.\s()]*(\d{3})[-.\s()]*(\d{4})")
_ADDRESS_RE = re.compile(r"\b\d{1,6}\s+[A-Za-z0-9.\s]{2,40}\s(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Dr|Drive)\b", re.IGNORECASE)


def _redact_value(v):
    if isinstance(v, str):
        v = _EMAIL_RE.sub(r"\1***\2", v)
        v = _PHONE_RE.sub(r"***-***-\3", v)
        v = _ADDRESS_RE.sub("[REDACTED_ADDRESS]", v)
        return v
    if isinstance(v, dict):
        return {k: _redact_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_redact_value(i) for i in v]
    return v


def redact_pii(_, __, event_dict):
    return {k: _redact_value(v) for k, v in event_dict.items()}


def configure_logging(level: str | None = None) -> None:
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        redact_pii,
    ]

    if os.getenv("ENV", "dev") == "dev" and sys.stderr.isatty():
        shared_processors.append(structlog.dev.ConsoleRenderer())
    else:
        shared_processors.extend(
            [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ]
        )

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # tame noisy loggers
    for name in ("httpx", "httpcore", "asyncio"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]
