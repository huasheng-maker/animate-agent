"""Deterministic adapters that normalize external inputs into SourceDocument."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

from animate_agent.documents.file_parser import parse_file
from animate_agent.ingestion.models import UrlInput, WebIngestionConfig
from animate_agent.ingestion.security import URLSecurityPolicy
from animate_agent.ingestion.web.http_fallback import fetch_static_snapshot
from animate_agent.sources.models import (
    FileSourceInput,
    QuerySourceInput,
    SourceAsset,
    SourceBlock,
    SourceCitation,
    SourceDocument,
    TextSourceInput,
    UrlSourceInput,
)
from animate_agent.sources.search_focus import FOCUSED_SEARCH_INSTRUCTION, SEARCH_RESULT_LIMIT

_NOISE_TAGS = ("script", "style", "nav", "footer", "aside", "form", "noscript", "template")
_NOISE_SELECTORS = (
    "[role='navigation']",
    "[role='complementary']",
    "[class*='cookie' i]",
    "[id*='cookie' i]",
    "[class*='sidebar' i]",
    "[id*='sidebar' i]",
    "[class*='breadcrumb' i]",
)


class QueryAdapter(Protocol):
    async def resolve(self, source: QuerySourceInput) -> list[SourceDocument]: ...


class UrlAdapter(Protocol):
    async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]: ...


class TextAdapter:
    async def resolve(self, source: TextSourceInput) -> list[SourceDocument]:
        identity = hashlib.sha256(source.text.encode("utf-8")).hexdigest()[:20]
        return [
            SourceDocument(
                id=f"text-{identity}",
                source_type="text",
                title=source.title,
                content=source.text,
                metadata={"content_format": "text", "trust_level": "user_supplied"},
            )
        ]


def _document_as_markdown(
    path: Path,
) -> tuple[str, str, str, tuple[SourceBlock, ...], tuple[SourceAsset, ...]]:
    parsed = parse_file(path)
    lines: list[str] = []
    source_blocks: list[SourceBlock] = []
    assets: list[SourceAsset] = []
    for section in parsed.sections:
        if section.title:
            lines.append(f"{'#' * section.level} {section.title}")
            source_blocks.append(
                SourceBlock(
                    id=section.id,
                    type="heading",
                    text=section.title,
                    level=section.level,
                )
            )
        for block in section.blocks:
            block_type = block.type
            asset_id: str | None = None
            if block_type in {"image", "diagram"} and block.source_ref:
                asset_id = f"asset-{block.id}"
                assets.append(
                    SourceAsset(
                        id=asset_id,
                        type=block_type,
                        url=block.source_ref,
                        alt_text=block.text or None,
                        title=block.caption,
                    )
                )
            source_blocks.append(
                SourceBlock(
                    id=block.id,
                    type=block_type,
                    text=block.text,
                    language=block.language,
                    url=block.source_ref,
                    caption=block.caption,
                    asset_id=asset_id,
                    metadata=dict(block.metadata),
                )
            )
            if block.type == "code":
                lines.extend((f"```{block.language or ''}", block.text, "```"))
            elif block.type == "list":
                lines.append(f"- {block.text}")
            elif block.type == "image":
                lines.append(f"![{block.text}]()")
            else:
                lines.append(block.text)
        lines.append("")
    content = "\n".join(lines).strip()
    if not content:
        raise ValueError(f"The file contains no readable content: {path}")
    return parsed.document_id, parsed.title, content, tuple(source_blocks), tuple(assets)


class FileAdapter:
    def resolve_sync(self, source: FileSourceInput) -> list[SourceDocument]:
        path = source.path.expanduser().resolve()
        document_id, title, content, blocks, assets = _document_as_markdown(path)
        extension = path.suffix.lower()
        return [
            SourceDocument(
                id=document_id,
                source_type="pdf" if extension == ".pdf" else "file",
                title=title,
                content=content,
                blocks=blocks,
                assets=assets,
                metadata={
                    "content_format": "markdown",
                    "file_name": path.name,
                    "extension": extension,
                    "trust_level": "user_supplied",
                },
            )
        ]

    async def resolve(self, source: FileSourceInput) -> list[SourceDocument]:
        return self.resolve_sync(source)


def _readable_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup.find("article") or soup.select_one("[role='main']")
    if root is None:
        root = soup.body or soup
    for element in root.find_all(_NOISE_TAGS):
        element.decompose()
    for selector in _NOISE_SELECTORS:
        for element in root.select(selector):
            element.decompose()
    return str(root).strip()


class WebReaderAdapter:
    """Read exactly one public page through the bounded static HTTP path."""

    def __init__(
        self,
        config: WebIngestionConfig | None = None,
        *,
        security_policy: URLSecurityPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or WebIngestionConfig(javascript_enabled=False)
        self.security_policy = security_policy or URLSecurityPolicy(
            allowed_domains=self.config.allowed_domains
        )
        self._client = client

    async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
        snapshot = await fetch_static_snapshot(
            UrlInput(url=source.url),
            self.config,
            self.security_policy,
            client=self._client,
        )
        final_url = snapshot.final_url or source.url
        media_type = str(snapshot.metadata.get("content-type", "")).split(";", 1)[0]
        if snapshot.cleaned_html:
            content = _readable_html(snapshot.cleaned_html)
            content_format = "html"
        else:
            content = snapshot.raw_markdown.strip()
            if "markdown" in media_type:
                content_format = "markdown"
            elif media_type in {"text/x-rst", "text/prs.fallenstein.rst"} or urlsplit(
                final_url
            ).path.lower().endswith(".rst"):
                content_format = "rst"
            else:
                content_format = "text"
        if not content:
            raise ValueError("The web page contains no readable content.")
        document_id = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:20]
        title_value = snapshot.metadata.get("title")
        title = str(title_value).strip() if title_value else final_url
        citation = SourceCitation(id=f"{document_id}-source", title=title, url=final_url)
        return [
            SourceDocument(
                id=document_id,
                source_type="web_page",
                title=title,
                content=content,
                url=final_url,
                metadata={
                    "content_format": content_format,
                    "content_type": media_type,
                    "trust_level": "untrusted_external",
                },
                citations=(citation,),
            )
        ]


class KimiWebReaderAdapter:
    """Read one validated public URL through Kimi's official Tools Fetch API."""

    def __init__(
        self,
        config: WebIngestionConfig | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        security_policy: URLSecurityPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or WebIngestionConfig(javascript_enabled=False)
        self._api_key = api_key
        self._base_url = base_url
        self.security_policy = security_policy or URLSecurityPolicy(
            allowed_domains=self.config.allowed_domains
        )
        self._client = client

    async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
        api_key = (
            self._api_key
            or os.environ.get("KIMI_KEY", "")
            or os.environ.get("MOONSHOT_API_KEY", "")
        )
        if not api_key:
            raise RuntimeError("KIMI_KEY (or MOONSHOT_API_KEY) is required for Kimi Tools Fetch.")
        base_url = _https_service_url(
            self._base_url
            or f"{os.environ.get('KIMI_BASE', 'https://api.moonshot.cn/v1').rstrip('/')}"
            "/tools/fetch",
            "Kimi Tools Fetch",
        )
        validated = await self.security_policy.validate(source.url)
        track_id = str(uuid.uuid4())
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.timeout_seconds), trust_env=False
        )
        try:
            response = await client.post(
                base_url,
                json={"url": validated.url},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "X-Msh-Track-Id": track_id,
                },
            )
            response.raise_for_status()
            if len(response.content) > self.config.max_content_bytes:
                raise ValueError("Kimi Web Fetch response exceeded the configured size limit.")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Kimi Tools Fetch returned an invalid response object.")
            content_value = data.get("markdown")
            content = content_value.strip() if isinstance(content_value, str) else ""
            if not content:
                raise ValueError("Kimi Tools Fetch returned no readable Markdown.")
            returned_url = _public_result_url(data.get("url")) or validated.url
            title_value = data.get("title")
            title = title_value.strip() if isinstance(title_value, str) else returned_url
            identity = hashlib.sha256(returned_url.encode("utf-8")).hexdigest()[:20]
            return [
                SourceDocument(
                    id=identity,
                    source_type="web_page",
                    title=title,
                    content=content,
                    url=returned_url,
                    metadata={
                        "content_format": "markdown",
                        "provider": "kimi",
                        "provider_api": "tools_fetch",
                        "provider_request_id": response.headers.get("X-Msh-Track-Id", track_id),
                        "trust_level": "untrusted_external",
                    },
                    citations=(
                        SourceCitation(
                            id=f"{identity}-source",
                            title=title,
                            url=returned_url,
                        ),
                    ),
                )
            ]
        finally:
            if owns_client:
                await client.aclose()


def _public_result_url(raw_url: object) -> str | None:
    if not isinstance(raw_url, str):
        return None
    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(hostname.strip("[]")).is_global:
                return None
        except ValueError:
            pass
    except ValueError:
        return None
    return raw_url


def _mapping(value: object) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _https_service_url(raw_url: str, service_name: str) -> str:
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise ValueError(f"{service_name} endpoint is malformed.") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(
            f"{service_name} endpoint must be an HTTPS URL without embedded credentials."
        )
    return raw_url


def normalize_web_search_response(payload: Mapping[str, Any], query: str) -> list[SourceDocument]:
    """Map an OpenAI Responses payload to provider-neutral source documents."""

    output = payload.get("output")
    if not isinstance(output, list):
        raise ValueError("Web Search returned no output items.")
    response_id = str(payload.get("id", ""))
    answer_parts: list[str] = []
    sources: dict[str, dict[str, Any]] = {}

    for raw_item in output:
        item = _mapping(raw_item)
        if item is None:
            continue
        action = _mapping(item.get("action"))
        raw_sources = action.get("sources") if action else None
        if isinstance(raw_sources, list):
            for raw_source in raw_sources:
                provider_source = _mapping(raw_source)
                if provider_source is None:
                    continue
                url = _public_result_url(provider_source.get("url"))
                if url:
                    sources.setdefault(url, {"title": provider_source.get("title"), "snippets": []})

        content = item.get("content")
        if not isinstance(content, list):
            continue
        for raw_content in content:
            part = _mapping(raw_content)
            if part is None or part.get("type") != "output_text":
                continue
            text = part.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            answer_parts.append(text.strip())
            annotations = part.get("annotations")
            if not isinstance(annotations, list):
                continue
            for raw_annotation in annotations:
                annotation = _mapping(raw_annotation)
                if annotation is None or annotation.get("type") != "url_citation":
                    continue
                url = _public_result_url(annotation.get("url"))
                if not url:
                    continue
                entry = sources.setdefault(url, {"title": annotation.get("title"), "snippets": []})
                start = annotation.get("start_index")
                end = annotation.get("end_index")
                if (
                    isinstance(start, int)
                    and isinstance(end, int)
                    and 0 <= start < end <= len(text)
                ):
                    entry["snippets"].append(text[start:end].strip())

    answer = "\n\n".join(answer_parts).strip()
    if not answer:
        raise ValueError("Web Search returned no readable answer.")
    if not sources:
        identity = hashlib.sha256(query.encode("utf-8")).hexdigest()[:20]
        return [
            SourceDocument(
                id=f"search-{identity}",
                source_type="web_search",
                title=f"Web search: {query}",
                content=answer,
                metadata={
                    "content_format": "markdown",
                    "provider": "openai",
                    "provider_response_id": response_id,
                    "query": query,
                    "trust_level": "untrusted_external",
                },
            )
        ]

    documents: list[SourceDocument] = []
    for url, entry in sources.items():
        identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        title = str(entry.get("title") or url)
        snippets = [item for item in entry["snippets"] if item]
        content = "\n\n".join(dict.fromkeys(snippets)) or answer
        citation = SourceCitation(id=f"{identity}-citation", title=title, url=url)
        documents.append(
            SourceDocument(
                id=f"search-{identity}",
                source_type="web_search",
                title=title,
                content=content,
                url=url,
                metadata={
                    "content_format": "markdown",
                    "provider": "openai",
                    "provider_response_id": response_id,
                    "query": query,
                    "trust_level": "untrusted_external",
                    "synthesized": True,
                },
                citations=(citation,),
            )
        )
    return documents


class OpenAIWebSearchAdapter:
    """Hosted Web Search adapter using the OpenAI Responses API over HTTP."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    async def resolve(self, source: QuerySourceInput) -> list[SourceDocument]:
        api_key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for hosted Web Search.")
        model = self._model or os.environ.get("OPENAI_WEB_SEARCH_MODEL", "gpt-5-mini")
        payload = {
            "model": model,
            "tools": [{"type": "web_search"}],
            "tool_choice": {"type": "web_search"},
            "include": ["web_search_call.action.sources"],
            "store": False,
            "instructions": FOCUSED_SEARCH_INSTRUCTION,
            "input": source.query,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0), trust_env=False)
        try:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Web Search returned an invalid response object.")
            return normalize_web_search_response(data, source.query)
        finally:
            if owns_client:
                await client.aclose()


def normalize_kimi_search_response(
    payload: Mapping[str, Any],
    query: str,
    *,
    mode: str,
    request_id: str = "",
) -> list[SourceDocument]:
    """Map Kimi Tools Search Basic/Pro responses to SourceDocument objects."""

    raw_results = payload.get("search_results")
    if not isinstance(raw_results, list):
        raise ValueError("Kimi Web Search returned no search_results list.")

    documents: list[SourceDocument] = []
    for raw_result in raw_results:
        result = _mapping(raw_result)
        if result is None:
            continue
        url = _public_result_url(result.get("url"))
        if not url:
            continue
        identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        title = str(result.get("title") or url).strip()
        chunks = result.get("chunks")
        chunk_texts: list[str] = []
        chunk_scores: list[float] = []
        if isinstance(chunks, list):
            for raw_chunk in chunks:
                chunk = _mapping(raw_chunk)
                if chunk is None:
                    continue
                text_value = chunk.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    chunk_texts.append(text_value.strip())
                score = chunk.get("score")
                if isinstance(score, int | float):
                    chunk_scores.append(float(score))
        text_value = result.get("text")
        content_value = (
            "\n\n".join(chunk_texts)
            or (text_value if isinstance(text_value, str) else "")
            or result.get("snippet")
        )
        content = str(content_value or "").strip()
        if not content:
            continue
        metadata: dict[str, Any] = {
            "content_format": "markdown" if chunk_texts or text_value else "text",
            "provider": "kimi",
            "provider_api": f"tools_search_{mode}",
            "provider_request_id": request_id,
            "query": query,
            "trust_level": "untrusted_external",
        }
        for source_key, metadata_key in (
            ("site_name", "site_name"),
            ("date", "published_at"),
            ("mime", "content_type"),
            ("authority", "authority"),
        ):
            value = result.get(source_key)
            if isinstance(value, str) and value.strip():
                metadata[metadata_key] = value.strip()
        if chunk_scores:
            metadata["chunk_scores"] = chunk_scores
        documents.append(
            SourceDocument(
                id=f"search-{identity}",
                source_type="web_search",
                title=title,
                content=content,
                url=url,
                metadata=metadata,
                citations=(SourceCitation(id=f"{identity}-citation", title=title, url=url),),
            )
        )
    if not documents:
        raise ValueError("Kimi Web Search returned no usable public results.")
    return documents


class KimiWebSearchAdapter:
    """Kimi official Tools Search adapter, defaulting to Search Pro for LLM input."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
        limit: int = SEARCH_RESULT_LIMIT,
        include_content: bool = True,
        mode: str | None = None,
        timeout_seconds: int = 30,
        max_response_bytes: int = 5_000_000,
    ) -> None:
        if not 1 <= limit <= 20:
            raise ValueError("Kimi Web Search limit must be between 1 and 20.")
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        self._limit = limit
        self._include_content = include_content
        self._mode = mode
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("Kimi Web Search timeout_seconds must be between 1 and 60.")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    async def resolve(self, source: QuerySourceInput) -> list[SourceDocument]:
        api_key = (
            self._api_key
            or os.environ.get("KIMI_KEY", "")
            or os.environ.get("MOONSHOT_API_KEY", "")
        )
        if not api_key:
            raise RuntimeError("KIMI_KEY (or MOONSHOT_API_KEY) is required for Kimi Tools Search.")
        mode = (self._mode or os.environ.get("KIMI_WEB_SEARCH_MODE", "pro")).strip().lower()
        if mode not in {"basic", "pro"}:
            raise ValueError("KIMI_WEB_SEARCH_MODE must be either 'basic' or 'pro'.")
        base_url = _https_service_url(
            self._base_url
            or f"{os.environ.get('KIMI_BASE', 'https://api.moonshot.cn/v1').rstrip('/')}"
            f"/tools/{'search_pro' if mode == 'pro' else 'search'}",
            "Kimi Tools Search",
        )
        payload = {
            "text_query": source.query,
            "limit": self._limit,
            "timeout_seconds": self._timeout_seconds,
        }
        if mode == "basic":
            payload["include_content"] = self._include_content
        track_id = str(uuid.uuid4())
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(180.0, connect=15.0), trust_env=False
        )
        try:
            response = await client.post(
                base_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "X-Msh-Track-Id": track_id,
                },
            )
            response.raise_for_status()
            if len(response.content) > self._max_response_bytes:
                raise ValueError("Kimi Web Search response exceeded the configured size limit.")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Kimi Web Search returned an invalid response object.")
            return normalize_kimi_search_response(
                data,
                source.query,
                mode=mode,
                request_id=response.headers.get("X-Msh-Track-Id", track_id),
            )
        finally:
            if owns_client:
                await client.aclose()


def normalize_gemini_search_response(response: Any, query: str) -> list[SourceDocument]:
    """Map a Google GenAI grounded response to provider-neutral documents."""

    answer_value = getattr(response, "text", None)
    answer = answer_value.strip() if isinstance(answer_value, str) else ""
    if not answer:
        raise ValueError("Gemini Web Search returned no readable answer.")

    response_id_value = getattr(response, "response_id", None)
    response_id = str(response_id_value or "")
    sources: dict[str, dict[str, Any]] = {}
    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list):
        for candidate in candidates:
            metadata = getattr(candidate, "grounding_metadata", None)
            chunks = getattr(metadata, "grounding_chunks", None)
            if isinstance(chunks, list):
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    url = _public_result_url(getattr(web, "uri", None))
                    if not url:
                        continue
                    sources.setdefault(
                        url,
                        {
                            "title": getattr(web, "title", None),
                            "snippets": [],
                        },
                    )
            supports = getattr(metadata, "grounding_supports", None)
            if not isinstance(supports, list) or not isinstance(chunks, list):
                continue
            for support in supports:
                segment = getattr(support, "segment", None)
                snippet_value = getattr(segment, "text", None)
                snippet = snippet_value.strip() if isinstance(snippet_value, str) else ""
                indices = getattr(support, "grounding_chunk_indices", None)
                if not snippet or not isinstance(indices, list):
                    continue
                for index in indices:
                    if not isinstance(index, int) or not 0 <= index < len(chunks):
                        continue
                    web = getattr(chunks[index], "web", None)
                    url = _public_result_url(getattr(web, "uri", None))
                    if url and url in sources:
                        sources[url]["snippets"].append(snippet)

    if not sources:
        identity = hashlib.sha256(query.encode("utf-8")).hexdigest()[:20]
        return [
            SourceDocument(
                id=f"search-{identity}",
                source_type="web_search",
                title=f"Web search: {query}",
                content=answer,
                metadata={
                    "content_format": "markdown",
                    "provider": "google",
                    "provider_response_id": response_id,
                    "query": query,
                    "trust_level": "untrusted_external",
                },
            )
        ]

    documents: list[SourceDocument] = []
    for url, entry in sources.items():
        identity = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        title = str(entry.get("title") or url)
        snippets = [item for item in entry["snippets"] if item]
        content = "\n\n".join(dict.fromkeys(snippets)) or answer
        documents.append(
            SourceDocument(
                id=f"search-{identity}",
                source_type="web_search",
                title=title,
                content=content,
                url=url,
                metadata={
                    "content_format": "markdown",
                    "provider": "google",
                    "provider_response_id": response_id,
                    "query": query,
                    "trust_level": "untrusted_external",
                    "synthesized": True,
                },
                citations=(SourceCitation(id=f"{identity}-citation", title=title, url=url),),
            )
        )
    return documents


class GeminiWebSearchAdapter:
    """Google GenAI SDK adapter using Google Search grounding."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    async def resolve(self, source: QuerySourceInput) -> list[SourceDocument]:
        api_key = self._api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini Web Search.")
        model = self._model or os.environ.get("GEMINI_WEB_SEARCH_MODEL", "gemini-2.5-flash")
        owns_client = self._client is None
        client = self._client or genai.Client(api_key=api_key)
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=source.query,
                config=types.GenerateContentConfig(
                    system_instruction=FOCUSED_SEARCH_INSTRUCTION,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            return normalize_gemini_search_response(response, source.query)
        finally:
            if owns_client:
                await client.aio.aclose()
