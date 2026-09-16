"""Convert the safe acquisition boundary into the product DocumentIR."""

from __future__ import annotations

from animate_agent.documents.builder import build_document_ir
from animate_agent.documents.models import DocumentIR
from animate_agent.ingestion.models import NormalizedDocument, SourceType
from animate_agent.sources.models import SourceCitation, SourceDocument


def normalized_document_to_ir(normalized: NormalizedDocument) -> DocumentIR:
    """Map normalized, untrusted content into the validated product IR.

    The converter is deliberately vendor-independent. It consumes only the
    application-owned ``NormalizedDocument`` and runs its retained content
    through the deterministic HTML parser; no crawler types or raw page HTML
    cross into the AI stages.
    """

    if normalized.source_type != SourceType.URL:
        raise ValueError("Only URL NormalizedDocuments can be converted to a URL DocumentIR.")

    # ``final_url`` and ``source_url`` have passed URLSecurityPolicy. A page's
    # canonical metadata is author-controlled and is therefore not provenance
    # unless a future normalizer validates it explicitly.
    source_url = normalized.crawl.final_url or normalized.source_url
    if source_url is None:
        raise ValueError("The normalized URL document has no source URL.")

    content = (
        normalized.cleaned_html
        or normalized.fit_markdown
        or normalized.raw_markdown
        or normalized.text_content
    )
    content_format = "html" if normalized.cleaned_html else "markdown"
    source = SourceDocument(
        id=normalized.document_id,
        source_type="web_page",
        title=normalized.title,
        content=content,
        url=source_url,
        metadata={
            "content_format": content_format,
            "trust_level": "untrusted_external",
            "legacy_normalized_document": True,
        },
        citations=(
            SourceCitation(
                id=f"{normalized.document_id}-source",
                title=normalized.title,
                url=source_url,
            ),
        ),
    )
    return build_document_ir([source])
