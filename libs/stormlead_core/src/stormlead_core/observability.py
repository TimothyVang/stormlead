from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import UUID, uuid4

import structlog

from .logging import get_logger

_corr_id: ContextVar[str | None] = ContextVar("stormlead_correlation_id", default=None)


class SharedErrorSink:
    """Tiny shared sink: structured error event for all services."""

    def __init__(self) -> None:
        self.log = get_logger("stormlead.error_sink")

    def report(self, service: str, component: str, error: Exception, **fields: Any) -> None:
        self.log.error(
            "error.reported",
            service=service,
            component=component,
            error_type=type(error).__name__,
            error=str(error),
            correlation_id=current_correlation_id(),
            **fields,
        )


ERROR_SINK = SharedErrorSink()


def current_correlation_id() -> str:
    corr = _corr_id.get()
    if corr:
        return corr
    generated = str(uuid4())
    _corr_id.set(generated)
    structlog.contextvars.bind_contextvars(correlation_id=generated)
    return generated


def bind_correlation_id(correlation_id: str | UUID | None) -> str:
    corr = str(correlation_id or uuid4())
    _corr_id.set(corr)
    structlog.contextvars.bind_contextvars(correlation_id=corr)
    return corr


@contextmanager
def correlation_scope(correlation_id: str | UUID | None = None):
    previous = _corr_id.get()
    corr = bind_correlation_id(correlation_id)
    try:
        yield corr
    finally:
        if previous:
            bind_correlation_id(previous)
        else:
            _corr_id.set(None)
            structlog.contextvars.unbind_contextvars("correlation_id")


def emit_metric(name: str, value: float = 1, **labels: Any) -> None:
    get_logger("stormlead.metrics").info(
        "metric.emitted",
        metric=name,
        value=value,
        correlation_id=current_correlation_id(),
        **labels,
    )


def emit_event(stage: str, **fields: Any) -> None:
    get_logger("stormlead.events").info(
        "funnel.stage",
        stage=stage,
        correlation_id=current_correlation_id(),
        **fields,
    )
