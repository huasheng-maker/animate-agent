"""Deterministic SourceInput routing; no model chooses ingestion tools."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter

from animate_agent.ingestion.exceptions import UnsupportedInput
from animate_agent.sources.adapters import (
    FileAdapter,
    GeminiWebSearchAdapter,
    KimiWebReaderAdapter,
    KimiWebSearchAdapter,
    OpenAIWebSearchAdapter,
    QueryAdapter,
    TextAdapter,
    UrlAdapter,
    WebReaderAdapter,
)
from animate_agent.sources.models import (
    FileSourceInput,
    QuerySourceInput,
    SourceDocument,
    SourceInput,
    TextSourceInput,
    UrlSourceInput,
)

SOURCE_INPUT_ADAPTER: TypeAdapter[SourceInput] = TypeAdapter(SourceInput)


def default_web_search_adapter() -> QueryAdapter:
    provider = os.environ.get("WEB_SEARCH_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        return GeminiWebSearchAdapter()
    if provider == "openai":
        return OpenAIWebSearchAdapter()
    if provider == "kimi":
        return KimiWebSearchAdapter()
    raise ValueError("WEB_SEARCH_PROVIDER must be 'gemini', 'openai', or 'kimi'.")


def default_web_reader_adapter() -> UrlAdapter:
    provider = os.environ.get("WEB_READER_PROVIDER", "local").strip().lower()
    if provider == "local":
        return WebReaderAdapter()
    if provider == "kimi":
        return KimiWebReaderAdapter()
    raise ValueError("WEB_READER_PROVIDER must be either 'local' or 'kimi'.")


class SourceResolver:
    def __init__(
        self,
        *,
        web_search: QueryAdapter | None = None,
        web_reader: UrlAdapter | None = None,
        text_adapter: TextAdapter | None = None,
        file_adapter: FileAdapter | None = None,
    ) -> None:
        self._web_search = web_search or default_web_search_adapter()
        self._web_reader = web_reader or default_web_reader_adapter()
        self._text = text_adapter or TextAdapter()
        self._file = file_adapter or FileAdapter()

    async def resolve(self, source: SourceInput | Mapping[str, Any]) -> list[SourceDocument]:
        validated = SOURCE_INPUT_ADAPTER.validate_python(source)
        if isinstance(validated, QuerySourceInput):
            return await self._web_search.resolve(validated)
        if isinstance(validated, UrlSourceInput):
            return await self._web_reader.resolve(validated)
        if isinstance(validated, TextSourceInput):
            return await self._text.resolve(validated)
        if isinstance(validated, FileSourceInput):
            return await self._file.resolve(validated)
        raise UnsupportedInput("Unsupported source input.")


async def resolve_source(source: SourceInput | Mapping[str, Any]) -> list[SourceDocument]:
    return await SourceResolver().resolve(source)
