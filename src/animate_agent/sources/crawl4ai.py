"""Optional Crawl4AI adapter behind the SourceDocument boundary."""

from __future__ import annotations

from animate_agent.ingestion.models import UrlInput
from animate_agent.ingestion.web.crawl4ai_adapter import Crawl4AIWebDocumentAdapter
from animate_agent.sources.models import SourceCitation, SourceDocument, UrlSourceInput


class Crawl4AIAdapter:
    """Use browser crawling explicitly for future multi-page/dynamic ingestion."""

    def __init__(self, adapter: Crawl4AIWebDocumentAdapter | None = None) -> None:
        self._adapter = adapter or Crawl4AIWebDocumentAdapter()

    async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
        normalized = await self._adapter.ingest(UrlInput(url=source.url))
        final_url = normalized.crawl.final_url or normalized.source_url or source.url
        content = (
            normalized.fit_markdown
            or normalized.raw_markdown
            or normalized.cleaned_html
            or normalized.text_content
        )
        content_format = "markdown" if (
            normalized.fit_markdown or normalized.raw_markdown
        ) else ("html" if normalized.cleaned_html else "text")
        citation = SourceCitation(
            id=f"{normalized.document_id}-source",
            title=normalized.title,
            url=final_url,
        )
        return [
            SourceDocument(
                id=normalized.document_id,
                source_type="web_page",
                title=normalized.title,
                content=content,
                url=final_url,
                metadata={
                    "adapter": "crawl4ai",
                    "content_format": content_format,
                    "trust_level": "untrusted_external",
                },
                citations=(citation,),
            )
        ]

    async def close(self) -> None:
        await self._adapter.close()

    async def __aenter__(self) -> Crawl4AIAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
