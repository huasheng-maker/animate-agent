"""Stable, user-safe ingestion failures."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(eq=False)
class IngestionError(Exception):
    """Base exception with separate user and developer diagnostics."""

    message: str
    detail: str | None = None
    code: ClassVar[str] = "ingestion_error"

    def __str__(self) -> str:
        return self.message


class InvalidURL(IngestionError):
    code = "invalid_url"


class UnsupportedScheme(IngestionError):
    code = "unsupported_scheme"


class BlockedAddress(IngestionError):
    code = "blocked_address"


class CrawlTimeout(IngestionError):
    code = "timeout"


class NetworkError(IngestionError):
    code = "network_error"


class ContentTooLarge(IngestionError):
    code = "content_too_large"


class CrawlFailed(IngestionError):
    code = "crawl_failed"


class RobotsDenied(IngestionError):
    code = "robots_denied"


class NormalizationError(IngestionError):
    code = "normalization_error"


class UnsupportedInput(IngestionError):
    code = "unsupported_input"
