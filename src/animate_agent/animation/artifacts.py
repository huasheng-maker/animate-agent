"""Run-scoped persistence for the animation pipeline."""

from __future__ import annotations

import json
from collections.abc import Sequence
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from animate_agent.paths import RUNS_DIR
from animate_agent.sources.models import SourceDocument

DEFAULT_RUNS_DIR = RUNS_DIR

_RUN_DIRECTORY: ContextVar[Path | None] = ContextVar("animation_run_directory", default=None)


def bind_run_directory(path: Path) -> Token[Path | None]:
    path.mkdir(parents=True, exist_ok=False)
    return _RUN_DIRECTORY.set(path)


def reset_run_directory(token: Token[Path | None]) -> None:
    _RUN_DIRECTORY.reset(token)


def current_run_directory() -> Path | None:
    return _RUN_DIRECTORY.get()


def _write_json(filename: str, payload: Any) -> Path | None:
    run_directory = current_run_directory()
    if run_directory is None:
        return None
    destination = run_directory / filename
    serialized: Any
    if isinstance(payload, BaseModel):
        serialized = payload.model_dump(mode="json")
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        serialized = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in payload
        ]
    else:
        serialized = payload
    destination.write_text(
        json.dumps(serialized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def persist_source_documents(sources: Sequence[SourceDocument]) -> Path | None:
    return _write_json("01-source-document.json", sources)


def persist_document_ir(document: BaseModel) -> Path | None:
    return _write_json("02-document-ir.json", document)


def persist_lesson_ir(lesson: BaseModel) -> Path | None:
    return _write_json("03-lesson-ir.json", lesson)


def persist_skipped_lesson_ir() -> Path | None:
    return _write_json(
        "03-lesson-ir.json",
        {
            "status": "skipped",
            "reason": "query intent pipeline generates StoryboardIR directly",
        },
    )


def persist_storyboard_ir(storyboard: BaseModel) -> Path | None:
    return _write_json("04-storyboard-ir.json", storyboard)


def persist_animation_ir(animation: BaseModel) -> Path | None:
    return _write_json("05-animation-ir.json", animation)


def persist_render_spec(spec: BaseModel) -> Path | None:
    return _write_json("06-render-spec.json", spec)
