"""Source resolution, DocumentIR construction, and persistence."""

from pathlib import Path

from animate_agent.animation.artifacts import (
    current_run_directory,
    persist_source_documents,
)
from animate_agent.documents.builder import DocumentIRBuilder, build_document_ir
from animate_agent.documents.models import DocumentIR
from animate_agent.paths import DOCUMENTS_DIR
from animate_agent.sources.adapters import FileAdapter
from animate_agent.sources.models import FileSourceInput, SourceInput, UrlSourceInput
from animate_agent.sources.resolver import SourceResolver

DEFAULT_DOCUMENTS_DIR = DOCUMENTS_DIR


def _persist(document: DocumentIR, output_dir: Path) -> DocumentIR:
    if current_run_directory() is not None:
        return document
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{document.document_id}.json"
    destination.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    return document


async def ingest_source(
    source: SourceInput,
    *,
    output_dir: Path = DEFAULT_DOCUMENTS_DIR,
    resolver: SourceResolver | None = None,
    builder: DocumentIRBuilder | None = None,
) -> DocumentIR:
    """Resolve one input and build DocumentIR from SourceDocument objects only."""

    sources = await (resolver or SourceResolver()).resolve(source)
    persist_source_documents(sources)
    document = await (builder or DocumentIRBuilder()).build(sources)
    return _persist(document, output_dir)


async def ingest_url(
    url: str,
    *,
    output_dir: Path = DEFAULT_DOCUMENTS_DIR,
    resolver: SourceResolver | None = None,
    builder: DocumentIRBuilder | None = None,
) -> DocumentIR:
    """Resolve a direct URL through the lightweight single-page Web Reader."""

    return await ingest_source(
        UrlSourceInput(url=url),
        output_dir=output_dir,
        resolver=resolver,
        builder=builder,
    )


def ingest_file(
    path: str | Path,
    *,
    output_dir: Path = DEFAULT_DOCUMENTS_DIR,
) -> DocumentIR:
    """Parse, validate, and persist one uploaded document file."""
    source = FileAdapter().resolve_sync(FileSourceInput(path=Path(path)))[0]
    document = build_document_ir([source])
    return _persist(document, output_dir)
