"""Document ingestion and semantic extraction package."""

from animate_agent.documents.builder import DocumentIRBuilder, build_document_ir
from animate_agent.documents.file_parser import parse_file, parse_markdown
from animate_agent.documents.models import DocumentBlock, DocumentIR, DocumentSource, Section
from animate_agent.documents.parser import parse_html

__all__ = [
    "DocumentIRBuilder",
    "DocumentBlock",
    "DocumentIR",
    "DocumentSource",
    "Section",
    "build_document_ir",
    "parse_file",
    "parse_html",
    "parse_markdown",
]
