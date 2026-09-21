"""Small request context shared by orchestration and transport logs."""

from __future__ import annotations

from contextvars import ContextVar, Token

_ANIMATION_RUN_ID: ContextVar[str] = ContextVar("animation_run_id", default="-")


def animation_run_id() -> str:
    return _ANIMATION_RUN_ID.get()


def bind_animation_run_id(run_id: str) -> Token[str]:
    return _ANIMATION_RUN_ID.set(run_id)


def reset_animation_run_id(token: Token[str]) -> None:
    _ANIMATION_RUN_ID.reset(token)
