"""Stable document-acquisition boundary for Animate Agent."""

from animate_agent.ingestion.models import (
    NormalizedDocument,
    RawHtmlInput,
    UrlInput,
    WebIngestionConfig,
)
from animate_agent.ingestion.router import DocumentIngestionRouter

__all__ = [
    "DocumentIngestionRouter",
    "NormalizedDocument",
    "RawHtmlInput",
    "UrlInput",
    "WebIngestionConfig",
]
