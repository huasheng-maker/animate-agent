"""Internal compatibility DTOs between the crawler and normalizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from animate_agent.ingestion.models import RawHtmlInput, UrlInput, WebIngestionConfig


@dataclass(frozen=True)
class CrawlSnapshot:
    success: bool
    requested_url: str | None
    final_url: str | None
    status_code: int | None = None
    raw_html: str = ""
    cleaned_html: str = ""
    raw_markdown: str = ""
    fit_markdown: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    links: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    media: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    tables: list[dict[str, Any]] = field(default_factory=list)
    error_message: str | None = None


class CrawlInvoker(Protocol):
    async def crawl(
        self, source: UrlInput | RawHtmlInput, config: WebIngestionConfig
    ) -> CrawlSnapshot:
        """Invoke a crawler and return only application-owned data."""

    async def close(self) -> None:
        """Release crawler resources."""
