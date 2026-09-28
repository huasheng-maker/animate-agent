"""Validated pipeline milestones, independent of transport and job storage."""

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

ProgressSink = Callable[[str, dict[str, Any]], None]
progress_sink: ContextVar[ProgressSink | None] = ContextVar("progress_sink", default=None)


def report_progress(kind: str, **data: Any) -> None:
    sink = progress_sink.get()
    if sink is not None:
        sink(kind, data)
