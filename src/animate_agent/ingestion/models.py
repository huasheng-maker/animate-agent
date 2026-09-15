"""Crawl4AI-independent domain models for document acquisition."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceType(StrEnum):
    URL = "url"
    RAW_HTML = "raw_html"


class RetentionPolicy(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


class CachePolicy(StrEnum):
    ENABLED = "enabled"
    BYPASS = "bypass"
    DISABLED = "disabled"


class TrustLevel(StrEnum):
    UNTRUSTED_EXTERNAL = "untrusted_external"


class UrlInput(DomainModel):
    kind: Literal["url"] = "url"
    url: NonEmptyText


class RawHtmlInput(DomainModel):
    kind: Literal["raw_html"] = "raw_html"
    html: NonEmptyText
    base_url: str | None = None


DocumentInput = UrlInput | RawHtmlInput


class WebIngestionConfig(DomainModel):
    """Stable application policy translated internally to Crawl4AI settings."""

    allowed_domains: frozenset[str] = frozenset()
    excluded_tags: tuple[str, ...] = (
        "script",
        "style",
        "nav",
        "footer",
        "aside",
        "form",
        "noscript",
        "template",
    )
    excluded_selectors: tuple[str, ...] = (
        "[role='navigation']",
        "[role='complementary']",
        ".sidebar",
        ".breadcrumbs",
        "[class*='cookie' i]",
        "[id*='cookie' i]",
        ".headerlink",
    )
    content_selector: str | None = None
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    max_content_bytes: int = Field(default=5_000_000, ge=1_024, le=100_000_000)
    max_redirects: int = Field(default=5, ge=0, le=20)
    javascript_enabled: bool = True
    cache_policy: CachePolicy = CachePolicy.BYPASS
    extract_links: bool = True
    extract_images: bool = True
    respect_robots_txt: bool = True
    use_content_filter: bool = True
    filter_threshold: float = Field(default=0.48, ge=0.0, le=1.0)
    filter_min_words: int = Field(default=20, ge=0, le=1_000)
    retention: RetentionPolicy = RetentionPolicy.STANDARD
    crawler_data_directory: Path = Path(".cache/crawl4ai")

    @model_validator(mode="after")
    def normalize_domains(self) -> WebIngestionConfig:
        normalized = frozenset(item.strip().lower().rstrip(".") for item in self.allowed_domains)
        object.__setattr__(self, "allowed_domains", normalized)
        return self


class NormalizedLink(DomainModel):
    href: str
    text: str | None = None
    title: str | None = None
    scope: Literal["internal", "external"]


class NormalizedImage(DomainModel):
    src: str
    alt: str | None = None
    title: str | None = None


class NormalizedCodeBlock(DomainModel):
    code: str
    language: str | None = None


class NormalizedTable(DomainModel):
    caption: str | None = None
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()


class NormalizedSection(DomainModel):
    heading: str
    level: int = Field(ge=1, le=6)
    markdown: str


class DocumentMetadata(DomainModel):
    description: str | None = None
    author: str | None = None
    keywords: tuple[str, ...] = ()
    content_type: str | None = None
    status_code: int | None = None


class CrawlInfo(DomainModel):
    crawl_id: str
    requested_url: str | None = None
    final_url: str | None = None
    javascript_enabled: bool
    content_filter_applied: bool
    truncated: bool = False
    duration_ms: int = Field(ge=0)


class NormalizedDocument(DomainModel):
    """Stable output boundary. All textual fields remain untrusted data."""

    schema_version: Literal["1.0"] = "1.0"
    document_id: str
    source_type: SourceType
    source_url: str | None = None
    canonical_url: str | None = None
    title: str
    language: str | None = None
    cleaned_html: str | None = None
    raw_html: str | None = None
    raw_markdown: str | None = None
    fit_markdown: str | None = None
    text_content: str
    sections: tuple[NormalizedSection, ...] = ()
    code_blocks: tuple[NormalizedCodeBlock, ...] = ()
    tables: tuple[NormalizedTable, ...] = ()
    images: tuple[NormalizedImage, ...] = ()
    links: tuple[NormalizedLink, ...] = ()
    metadata: DocumentMetadata = DocumentMetadata()
    crawl_timestamp: datetime
    content_hash: str
    trust_level: Literal[TrustLevel.UNTRUSTED_EXTERNAL] = TrustLevel.UNTRUSTED_EXTERNAL
    crawl: CrawlInfo
    warnings: tuple[str, ...] = ()
