"""Framework-independent adapter contract for future document types."""

from typing import Protocol, TypeVar

from animate_agent.ingestion.models import DocumentInput, NormalizedDocument

InputT = TypeVar("InputT", bound=DocumentInput, contravariant=True)


class DocumentAdapter(Protocol[InputT]):
    """An adapter that turns one supported source into a normalized document."""

    def supports(self, source: DocumentInput) -> bool:
        """Return whether this adapter accepts the supplied source."""

    async def ingest(self, source: InputT) -> NormalizedDocument:
        """Acquire and normalize a document without semantic interpretation."""
