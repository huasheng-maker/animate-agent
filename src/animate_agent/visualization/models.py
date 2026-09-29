"""Contracts between controlled retrieval and intent-driven storyboard planning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from animate_agent.documents.models import DocumentIR


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualizationIntent(_Model):
    """What the user wants to understand, independent of any source format."""

    question: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="beginner", min_length=1, max_length=80)
    focus: list[str] = Field(default_factory=list, max_length=8)


class EvidenceItem(_Model):
    """One addressable fact-bearing block supplied by the retrieval boundary."""

    id: str
    section_title: str
    text: str
    source_id: str | None = None
    source_ref: str | None = None


class EvidenceSource(_Model):
    id: str | None = None
    title: str | None = None
    url: str | None = None


class EvidencePack(_Model):
    """Compact, provider-neutral evidence presented to the Storyboard model."""

    document_id: str
    title: str
    sources: list[EvidenceSource] = Field(default_factory=list)
    items: list[EvidenceItem] = Field(min_length=1)
    coverage_gaps: list[str] = Field(default_factory=list)

    @classmethod
    def from_document(cls, document: DocumentIR) -> EvidencePack:
        gaps: set[str] = set()
        for source in document.sources:
            hints = source.metadata.get("evidence_gaps")
            if isinstance(hints, list):
                gaps.update(hint for hint in hints if isinstance(hint, str))
        items = [
            EvidenceItem(
                id=block.id,
                section_title=section.title,
                text=block.text,
                source_id=block.source_id,
                source_ref=block.source_ref,
            )
            for section in document.sections
            for block in section.blocks
            if block.text.strip()
        ]
        return cls(
            document_id=document.document_id,
            title=document.title,
            sources=[
                EvidenceSource(id=source.id, title=source.title, url=source.url)
                for source in document.sources
            ],
            items=items,
            coverage_gaps=sorted(gaps),
        )
