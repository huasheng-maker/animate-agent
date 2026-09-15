"""Small input router; future file adapters can register beside the web adapter."""

from collections.abc import Sequence

from animate_agent.ingestion.base import DocumentAdapter
from animate_agent.ingestion.exceptions import UnsupportedInput
from animate_agent.ingestion.models import DocumentInput, NormalizedDocument


class DocumentIngestionRouter:
    def __init__(self, adapters: Sequence[DocumentAdapter[DocumentInput]]) -> None:
        self._adapters = tuple(adapters)

    async def ingest(self, source: DocumentInput) -> NormalizedDocument:
        for adapter in self._adapters:
            if adapter.supports(source):
                return await adapter.ingest(source)
        raise UnsupportedInput("No document adapter supports this input type.")
