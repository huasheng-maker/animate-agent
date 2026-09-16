"""Build DocumentIR from the provider-neutral SourceDocument boundary."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from html import escape
from typing import cast

from markdown_it import MarkdownIt

from animate_agent.documents.models import (
    DocumentBlock,
    DocumentIR,
    DocumentSource,
    Section,
)
from animate_agent.documents.parser import parse_html
from animate_agent.sources.models import SourceDocument

_RST_ADORNMENT = re.compile(r"^([=\-~^\"`:+*#<>_])\1{2,}$")
_RST_ADMONITION = re.compile(
    r"^\s*\.\.\s+(?:attention|caution|danger|error|hint|important|note|tip|warning)::\s*$",
    re.IGNORECASE,
)


def _rst_to_markdown(content: str) -> str:
    """Convert common reStructuredText headings without interpreting directives."""

    lines = content.splitlines()
    output: list[str] = []
    heading_levels: dict[str, int] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if _RST_ADMONITION.fullmatch(line):
            index += 1
            continue
        decoration = _RST_ADORNMENT.fullmatch(line.strip())
        if (
            decoration
            and index + 2 < len(lines)
            and lines[index + 1].strip()
            and lines[index + 2].strip() == line.strip()
        ):
            style = f"overline:{decoration.group(1)}"
            level = heading_levels.setdefault(style, len(heading_levels) + 1)
            output.append(f"{'#' * min(level, 6)} {lines[index + 1].strip()}")
            index += 3
            continue
        if line.strip() and index + 1 < len(lines):
            underline = _RST_ADORNMENT.fullmatch(lines[index + 1].strip())
            if underline and len(lines[index + 1].strip()) >= len(line.strip()):
                style = f"underline:{underline.group(1)}"
                level = heading_levels.setdefault(style, len(heading_levels) + 1)
                output.append(f"{'#' * min(level, 6)} {line.strip()}")
                index += 2
                continue
        if line.lstrip().startswith(".. _") and line.rstrip().endswith(":"):
            index += 1
            continue
        output.append(line)
        index += 1
    return "\n".join(output)


def _source_record(source: SourceDocument) -> DocumentSource:
    return DocumentSource(
        id=source.id,
        type=source.source_type,
        title=source.title,
        url=source.url,
        metadata=dict(source.metadata),
        citations=list(source.citations),
    )


def _source_html(source: SourceDocument) -> str:
    content_format = source.metadata.get("content_format")
    if content_format == "html":
        return source.content
    if content_format == "markdown":
        return cast(str, MarkdownIt("commonmark").render(source.content))
    if content_format == "rst":
        return cast(str, MarkdownIt("commonmark").render(_rst_to_markdown(source.content)))
    paragraphs = [item.strip() for item in source.content.splitlines() if item.strip()]
    body = "".join(f"<p>{escape(item)}</p>" for item in paragraphs)
    heading = f"<h1>{escape(source.title)}</h1>" if source.title else ""
    return f"<main>{heading}{body}</main>"


def _with_provenance(
    sections: list[Section], source_id: str, *, prefix_ids: bool
) -> list[Section]:
    output: list[Section] = []
    safe_prefix = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:8]
    for section in sections:
        section_id = f"source-{safe_prefix}-{section.id}" if prefix_ids else section.id
        blocks = [
            DocumentBlock(
                id=(f"source-{safe_prefix}-{block.id}" if prefix_ids else block.id),
                type=block.type,
                text=block.text,
                language=block.language,
                source_id=source_id,
                source_ref=block.source_ref,
            )
            for block in section.blocks
        ]
        output.append(
            Section(
                id=section_id,
                title=section.title,
                level=section.level,
                blocks=blocks,
            )
        )
    return output


def build_document_ir(sources: Sequence[SourceDocument]) -> DocumentIR:
    """Deterministically build one DocumentIR without acquisition dependencies."""

    validated = [SourceDocument.model_validate(source) for source in sources]
    if not validated:
        raise ValueError("At least one SourceDocument is required.")

    all_sections: list[Section] = []
    multiple = len(validated) > 1
    for source in validated:
        parsed = parse_html(_source_html(source), source.url or f"source://{source.id}")
        sections = parsed.sections
        if source.title and sections and sections[0].title == "Untitled document":
            sections[0].title = source.title
        all_sections.extend(_with_provenance(sections, source.id, prefix_ids=multiple))

    records = [_source_record(source) for source in validated]
    identity = "\n".join(source.id for source in validated)
    document_id = (
        validated[0].id
        if len(validated) == 1
        else hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    )
    title = validated[0].title or "Untitled document"
    return DocumentIR(
        document_id=document_id,
        title=title,
        source=records[0],
        sources=records,
        sections=all_sections,
    )


class DocumentIRBuilder:
    """Async-shaped facade matching the surrounding orchestration pipeline."""

    async def build(self, sources: Sequence[SourceDocument]) -> DocumentIR:
        return build_document_ir(sources)
