"""Pure conversion from crawler snapshots to the stable domain model."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from html import unescape
from time import monotonic
from typing import Any
from urllib.parse import urljoin, urlsplit

from animate_agent.ingestion.exceptions import ContentTooLarge, NormalizationError
from animate_agent.ingestion.models import (
    CrawlInfo,
    DocumentMetadata,
    NormalizedCodeBlock,
    NormalizedDocument,
    NormalizedImage,
    NormalizedLink,
    NormalizedSection,
    NormalizedTable,
    RawHtmlInput,
    RetentionPolicy,
    SourceType,
    UrlInput,
    WebIngestionConfig,
)
from animate_agent.ingestion.web.contracts import CrawlSnapshot

_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")


def _text_from_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _sections(markdown: str) -> tuple[NormalizedSection, ...]:
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        return ()
    sections: list[NormalizedSection] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections.append(
            NormalizedSection(
                heading=match.group(2).strip(),
                level=len(match.group(1)),
                markdown=markdown[match.end() : end].strip(),
            )
        )
    return tuple(sections)


def _code_blocks(markdown: str) -> tuple[NormalizedCodeBlock, ...]:
    return tuple(
        NormalizedCodeBlock(code=match.group(2).rstrip(), language=match.group(1).strip() or None)
        for match in _FENCE_RE.finditer(markdown)
        if match.group(2).strip()
    )


def _clean_optional(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _metadata(snapshot: CrawlSnapshot) -> DocumentMetadata:
    keywords = snapshot.metadata.get("keywords", ())
    if isinstance(keywords, str):
        keyword_items = tuple(item.strip() for item in keywords.split(",") if item.strip())
    elif isinstance(keywords, (list, tuple)):
        keyword_items = tuple(str(item).strip() for item in keywords if str(item).strip())
    else:
        keyword_items = ()
    return DocumentMetadata(
        description=_clean_optional(snapshot.metadata.get("description")),
        author=_clean_optional(snapshot.metadata.get("author")),
        keywords=keyword_items,
        content_type=_clean_optional(snapshot.metadata.get("content-type")),
        status_code=snapshot.status_code,
    )


def _links(snapshot: CrawlSnapshot, base_url: str | None) -> tuple[NormalizedLink, ...]:
    output: list[NormalizedLink] = []
    seen: set[tuple[str, str]] = set()
    for scope in ("internal", "external"):
        for item in snapshot.links.get(scope, []):
            href = item.get("href")
            if not isinstance(href, str) or not href.strip():
                continue
            normalized = urljoin(base_url or "", href.strip())
            if urlsplit(normalized).scheme not in {"http", "https"}:
                continue
            key = (scope, normalized)
            if key in seen:
                continue
            seen.add(key)
            output.append(
                NormalizedLink(
                    href=normalized,
                    text=_clean_optional(item.get("text")),
                    title=_clean_optional(item.get("title")),
                    scope=scope,
                )
            )
    return tuple(output)


def _images(snapshot: CrawlSnapshot, base_url: str | None) -> tuple[NormalizedImage, ...]:
    output: list[NormalizedImage] = []
    seen: set[str] = set()
    for item in snapshot.media.get("images", []):
        src = item.get("src")
        if not isinstance(src, str) or not src.strip():
            continue
        normalized = urljoin(base_url or "", src.strip())
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(
            NormalizedImage(
                src=normalized,
                alt=_clean_optional(item.get("alt")),
                title=_clean_optional(item.get("title")),
            )
        )
    return tuple(output)


def _tables(snapshot: CrawlSnapshot) -> tuple[NormalizedTable, ...]:
    output: list[NormalizedTable] = []
    for item in snapshot.tables:
        headers = item.get("headers", ())
        rows = item.get("rows", ())
        if not isinstance(headers, (list, tuple)) or not isinstance(rows, (list, tuple)):
            continue
        output.append(
            NormalizedTable(
                caption=_clean_optional(item.get("caption")),
                headers=tuple(str(value) for value in headers),
                rows=tuple(
                    tuple(str(value) for value in row)
                    for row in rows
                    if isinstance(row, (list, tuple))
                ),
            )
        )
    return tuple(output)


def normalize_snapshot(
    snapshot: CrawlSnapshot,
    source: UrlInput | RawHtmlInput,
    config: WebIngestionConfig,
    *,
    started_at: float,
    crawl_id: str,
) -> NormalizedDocument:
    """Validate size and map crawler output without leaking crawler-specific objects."""

    raw_size = len(snapshot.raw_html.encode("utf-8"))
    if raw_size > config.max_content_bytes:
        raise ContentTooLarge("The page exceeded the configured maximum size.")
    primary_markdown = snapshot.fit_markdown.strip() or snapshot.raw_markdown.strip()
    text_content = primary_markdown or _text_from_html(snapshot.cleaned_html)
    if not text_content:
        raise NormalizationError("The page returned no meaningful document content.")
    metadata = _metadata(snapshot)
    title = _clean_optional(snapshot.metadata.get("title")) or "Untitled document"
    language = _clean_optional(snapshot.metadata.get("language")) or _clean_optional(
        snapshot.metadata.get("lang")
    )
    final_url = snapshot.final_url if source.kind == "url" else source.base_url
    requested_url = source.url if source.kind == "url" else source.base_url
    canonical = _clean_optional(snapshot.metadata.get("canonical")) or final_url
    if canonical:
        identity = canonical
    elif isinstance(source, RawHtmlInput):
        identity = hashlib.sha256(source.html.encode("utf-8")).hexdigest()
    else:  # URL crawls always have a requested or final URL.
        identity = source.url
    document_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    content_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
    retention = config.retention
    warnings: list[str] = []
    if config.use_content_filter and not snapshot.fit_markdown.strip():
        warnings.append("Content filtering produced no fit Markdown; raw Markdown was used.")
    return NormalizedDocument(
        document_id=document_id,
        source_type=SourceType.URL if source.kind == "url" else SourceType.RAW_HTML,
        source_url=requested_url,
        canonical_url=canonical,
        title=title,
        language=language,
        raw_html=snapshot.raw_html if retention == RetentionPolicy.FULL else None,
        cleaned_html=snapshot.cleaned_html if retention != RetentionPolicy.MINIMAL else None,
        raw_markdown=snapshot.raw_markdown if retention != RetentionPolicy.MINIMAL else None,
        fit_markdown=snapshot.fit_markdown or None,
        text_content=text_content,
        sections=_sections(primary_markdown),
        code_blocks=_code_blocks(primary_markdown),
        tables=_tables(snapshot),
        images=_images(snapshot, final_url) if config.extract_images else (),
        links=_links(snapshot, final_url) if config.extract_links else (),
        metadata=metadata,
        crawl_timestamp=datetime.now(UTC),
        content_hash=content_hash,
        crawl=CrawlInfo(
            crawl_id=crawl_id,
            requested_url=requested_url,
            final_url=final_url,
            javascript_enabled=config.javascript_enabled,
            content_filter_applied=config.use_content_filter
            and bool(snapshot.fit_markdown.strip()),
            duration_ms=max(0, round((monotonic() - started_at) * 1000)),
        ),
        warnings=tuple(warnings),
    )
