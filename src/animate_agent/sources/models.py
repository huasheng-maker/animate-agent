"""Runtime-validated domain models shared by every source adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceDocumentType = Literal["web_search", "web_page", "text", "file", "pdf"]
SourceBlockType = Literal[
    "heading",
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
SourceAssetType = Literal["image", "diagram", "audio", "video", "attachment"]


class SourceModel(BaseModel):
    """Strict base model suitable for runtime validation and JSON Schema export."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceCitation(SourceModel):
    """A provider-neutral citation attached to acquired source content."""

    id: NonEmptyText
    title: str | None = None
    url: str | None = None
    start_index: int | None = Field(default=None, ge=0)
    end_index: int | None = Field(default=None, ge=0)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SourceAsset(SourceModel):
    """A reusable non-prose asset discovered during acquisition."""

    id: NonEmptyText
    type: SourceAssetType
    url: str | None = None
    title: str | None = None
    alt_text: str | None = None
    mime_type: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SourceBlock(SourceModel):
    """An ordered semantic block retained without provider-specific types."""

    id: NonEmptyText
    type: SourceBlockType
    text: str = ""
    level: int | None = Field(default=None, ge=1, le=6)
    language: str | None = None
    url: str | None = None
    caption: str | None = None
    asset_id: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> SourceBlock:
        if self.type == "heading" and self.level is None:
            raise ValueError("heading blocks require level")
        if self.type != "heading" and self.level is not None:
            raise ValueError("level is only valid for heading blocks")
        if not self.text.strip() and not self.url and not self.asset_id:
            raise ValueError("a source block requires text, url, or asset_id")
        return self


class SourceDocument(SourceModel):
    """Animate Agent's validated boundary between acquisition and DocumentIR."""

    id: NonEmptyText
    source_type: SourceDocumentType
    title: str | None = None
    content: NonEmptyText
    url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    citations: tuple[SourceCitation, ...] = ()
    blocks: tuple[SourceBlock, ...] = ()
    assets: tuple[SourceAsset, ...] = ()


class QuerySourceInput(SourceModel):
    type: Literal["query"] = "query"
    query: NonEmptyText


class UrlSourceInput(SourceModel):
    type: Literal["url"] = "url"
    url: NonEmptyText


class TextSourceInput(SourceModel):
    type: Literal["text"] = "text"
    text: NonEmptyText
    title: str | None = None


class FileSourceInput(SourceModel):
    type: Literal["file"] = "file"
    path: Path


SourceInput = Annotated[
    QuerySourceInput | UrlSourceInput | TextSourceInput | FileSourceInput,
    Field(discriminator="type"),
]
