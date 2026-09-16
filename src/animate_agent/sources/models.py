"""Runtime-validated domain models shared by every source adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceDocumentType = Literal["web_search", "web_page", "text", "file", "pdf"]


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


class SourceDocument(SourceModel):
    """Animate Agent's validated boundary between acquisition and DocumentIR."""

    id: NonEmptyText
    source_type: SourceDocumentType
    title: str | None = None
    content: NonEmptyText
    url: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    citations: tuple[SourceCitation, ...] = ()


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
