"""Validated intermediate representation built from SourceDocument objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from animate_agent.sources.models import SourceAsset, SourceCitation


class DocumentSource(BaseModel):
    """Where the source document came from."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    type: Literal["url", "web_search", "web_page", "text", "file", "pdf"]
    title: str | None = None
    url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    citations: list[SourceCitation] = Field(default_factory=list)
    assets: list[SourceAsset] = Field(default_factory=list)


class DocumentBlock(BaseModel):
    """A single ordered content block within a section."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal[
        "paragraph",
        "code",
        "equation",
        "table",
        "image",
        "diagram",
        "list",
        "quote",
        "callout",
    ]
    text: str
    language: str | None = None
    caption: str | None = None
    asset_id: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    source_id: str | None = None
    source_ref: str | None = None


class Section(BaseModel):
    """A heading and the content that follows it."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    level: int = Field(ge=1, le=6)
    blocks: list[DocumentBlock] = Field(default_factory=list)


class DocumentIR(BaseModel):
    """Format-independent, validated document structure."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    source: DocumentSource
    sources: list[DocumentSource] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_sources(self) -> DocumentIR:
        """Keep the legacy primary source while exposing complete provenance."""

        if not self.sources:
            self.sources = [self.source]
        return self
