"""Bounded static-HTTP fallback for browser crawl failures."""

from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from animate_agent.ingestion.exceptions import ContentTooLarge, CrawlFailed, IngestionError
from animate_agent.ingestion.models import UrlInput, WebIngestionConfig
from animate_agent.ingestion.security import URLSecurityPolicy
from animate_agent.ingestion.web.contracts import CrawlSnapshot

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SUPPORTED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "text/markdown",
    "text/x-rst",
)
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,text/plain,text/markdown;q=0.9,*/*;q=0.1",
    "User-Agent": "AnimateAgent/0.1 (+safe document ingestion)",
}


def _html_metadata(html: str, content_type: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    metadata: dict[str, str] = {"content-type": content_type}
    if soup.title and soup.title.string and soup.title.string.strip():
        metadata["title"] = soup.title.string.strip()
    if soup.html:
        language = soup.html.get("lang")
        if isinstance(language, str) and language.strip():
            metadata["language"] = language.strip()
    description = soup.find("meta", attrs={"name": "description"})
    if description:
        content = description.get("content")
        if isinstance(content, str) and content.strip():
            metadata["description"] = content.strip()
    return metadata


async def fetch_static_snapshot(
    source: UrlInput,
    config: WebIngestionConfig,
    security_policy: URLSecurityPolicy,
    *,
    client: httpx.AsyncClient | None = None,
) -> CrawlSnapshot:
    """Fetch one public text document with redirect, SSRF, TLS, and size bounds."""

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(config.timeout_seconds),
        headers=_HEADERS,
        trust_env=False,
    )
    current_url = source.url
    try:
        for redirect_count in range(config.max_redirects + 1):
            validated = await security_policy.validate(current_url)
            try:
                async with http_client.stream("GET", validated.url) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            raise CrawlFailed("The page returned an invalid redirect.")
                        if redirect_count >= config.max_redirects:
                            raise CrawlFailed("The page exceeded the redirect limit.")
                        current_url = urljoin(validated.url, location)
                        continue

                    if response.status_code >= 400:
                        raise CrawlFailed(
                            f"The site refused the fallback request (HTTP {response.status_code})."
                        )
                    content_type = response.headers.get("content-type", "").lower()
                    media_type = content_type.split(";", 1)[0].strip()
                    if media_type and not any(
                        media_type == supported for supported in _SUPPORTED_CONTENT_TYPES
                    ):
                        raise CrawlFailed(
                            f"The URL returned unsupported content type {media_type}."
                        )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > config.max_content_bytes:
                            raise ContentTooLarge(
                                "The page exceeded the configured maximum size."
                            )
                    encoding = response.charset_encoding or "utf-8"
                    text = bytes(body).decode(encoding, errors="replace")
                    is_html = media_type in {"text/html", "application/xhtml+xml"}
                    metadata = _html_metadata(text, content_type) if is_html else {
                        "content-type": content_type,
                        "title": current_url.rsplit("/", 1)[-1] or "Untitled document",
                    }
                    return CrawlSnapshot(
                        success=True,
                        requested_url=source.url,
                        final_url=validated.url,
                        status_code=response.status_code,
                        raw_html=text if is_html else "",
                        cleaned_html=text if is_html else "",
                        raw_markdown="" if is_html else text,
                        metadata=metadata,
                    )
            except IngestionError:
                raise
            except httpx.HTTPError as exc:
                raise CrawlFailed(
                    "The page could not be fetched by the static fallback.", detail=str(exc)
                ) from exc
        raise CrawlFailed("The page exceeded the redirect limit.")
    finally:
        if owns_client:
            await http_client.aclose()
