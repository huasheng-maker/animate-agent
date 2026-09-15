"""Crawl4AI infrastructure adapter and its single compatibility boundary."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from time import monotonic
from typing import Any, cast
from uuid import uuid4

from animate_agent.ingestion.exceptions import (
    ContentTooLarge,
    CrawlFailed,
    CrawlTimeout,
    IngestionError,
    NetworkError,
)
from animate_agent.ingestion.models import (
    DocumentInput,
    NormalizedDocument,
    RawHtmlInput,
    UrlInput,
    WebIngestionConfig,
)
from animate_agent.ingestion.security import URLSecurityPolicy
from animate_agent.ingestion.web.contracts import CrawlInvoker, CrawlSnapshot
from animate_agent.ingestion.web.normalizer import normalize_snapshot

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


class Crawl4AIInvoker:
    """Own one reusable browser and translate all Crawl4AI types locally."""

    def __init__(self, security_policy: URLSecurityPolicy) -> None:
        self._security_policy = security_policy
        self._crawler: Any = None
        self._start_lock = asyncio.Lock()

    async def _start(self, config: WebIngestionConfig) -> Any:
        if self._crawler is not None:
            return self._crawler
        async with self._start_lock:
            if self._crawler is not None:
                return self._crawler
            try:
                os.environ.setdefault(
                    "CRAWL4_AI_BASE_DIRECTORY",
                    str(config.crawler_data_directory.resolve()),
                )
                crawl4ai = importlib.import_module("crawl4ai")
            except ImportError as exc:
                raise CrawlFailed(
                    "Crawl4AI is not installed. Install the project dependencies first.",
                    detail=str(exc),
                ) from exc
            browser_config = crawl4ai.BrowserConfig(
                browser_type="chromium",
                headless=True,
                java_script_enabled=config.javascript_enabled,
                accept_downloads=False,
                ignore_https_errors=False,
                verbose=False,
            )
            crawler = crawl4ai.AsyncWebCrawler(config=browser_config)

            async def on_page_context_created(page: Any, context: Any, **_: Any) -> Any:
                navigation_count = 0

                async def route_filter(route: Any) -> None:
                    nonlocal navigation_count
                    is_navigation = bool(route.request.is_navigation_request())
                    if is_navigation:
                        navigation_count += 1
                        if navigation_count > config.max_redirects + 1:
                            logger.warning(
                                "blocked redirect limit", extra={"event": "redirect_limit"}
                            )
                            await route.abort("blockedbyclient")
                            return
                    if await self._security_policy.permits_browser_request(
                        route.request.url, is_navigation=is_navigation
                    ):
                        await route.continue_()
                    else:
                        logger.warning("blocked browser request", extra={"event": "ssrf_blocked"})
                        await route.abort("blockedbyclient")

                await context.route("**/*", route_filter)
                return page

            crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context_created)
            await crawler.start()
            self._crawler = crawler
        return self._crawler

    async def crawl(
        self, source: UrlInput | RawHtmlInput, config: WebIngestionConfig
    ) -> CrawlSnapshot:
        crawler = await self._start(config)
        try:
            crawl4ai = importlib.import_module("crawl4ai")
            filters = importlib.import_module("crawl4ai.content_filter_strategy")
            markdown_module = importlib.import_module("crawl4ai.markdown_generation_strategy")
        except ImportError as exc:
            raise CrawlFailed("Crawl4AI could not be loaded.", detail=str(exc)) from exc
        cache_modes = {
            "enabled": crawl4ai.CacheMode.ENABLED,
            "bypass": crawl4ai.CacheMode.BYPASS,
            "disabled": crawl4ai.CacheMode.DISABLED,
        }
        content_filter = None
        if config.use_content_filter:
            content_filter = filters.PruningContentFilter(
                threshold=config.filter_threshold,
                min_word_threshold=config.filter_min_words,
            )
        run_config = crawl4ai.CrawlerRunConfig(
            cache_mode=cache_modes[config.cache_policy.value],
            page_timeout=round(config.timeout_seconds * 1000),
            excluded_tags=list(config.excluded_tags),
            excluded_selector=", ".join(config.excluded_selectors) or None,
            css_selector=config.content_selector,
            remove_forms=True,
            remove_overlay_elements=True,
            remove_consent_popups=True,
            check_robots_txt=config.respect_robots_txt,
            process_iframes=False,
            scan_full_page=False,
            screenshot=False,
            pdf=False,
            capture_mhtml=False,
            verbose=False,
            markdown_generator=markdown_module.DefaultMarkdownGenerator(
                content_filter=content_filter
            ),
        )
        target = source.url if source.kind == "url" else f"raw:{source.html}"
        try:
            result = await asyncio.wait_for(
                crawler.arun(url=target, config=run_config),
                timeout=config.timeout_seconds + 2.0,
            )
        except TimeoutError as exc:
            raise CrawlTimeout("The document could not be loaded before the timeout.") from exc
        except IngestionError:
            raise
        except Exception as exc:
            raise NetworkError("The document could not be loaded.", detail=str(exc)) from exc
        result_markdown = getattr(result, "markdown", None)
        final_url = getattr(result, "redirected_url", None) or getattr(result, "url", None)
        if source.kind == "url" and isinstance(final_url, str):
            await self._security_policy.validate(final_url)
        if isinstance(source, RawHtmlInput):
            snapshot_final_url = source.base_url
        else:
            snapshot_final_url = final_url if isinstance(final_url, str) else source.url
        return CrawlSnapshot(
            success=bool(getattr(result, "success", False)),
            requested_url=source.url if source.kind == "url" else source.base_url,
            final_url=snapshot_final_url,
            status_code=getattr(result, "status_code", None),
            raw_html=getattr(result, "html", "") or "",
            cleaned_html=getattr(result, "cleaned_html", "") or "",
            raw_markdown=getattr(result_markdown, "raw_markdown", "") or "",
            fit_markdown=getattr(result_markdown, "fit_markdown", "") or "",
            metadata=_as_dict(getattr(result, "metadata", None)),
            links=cast(dict[str, list[dict[str, Any]]], _as_dict(getattr(result, "links", None))),
            media=cast(dict[str, list[dict[str, Any]]], _as_dict(getattr(result, "media", None))),
            tables=cast(list[dict[str, Any]], getattr(result, "tables", None) or []),
            error_message=getattr(result, "error_message", None),
        )

    async def close(self) -> None:
        crawler, self._crawler = self._crawler, None
        if crawler is not None:
            await crawler.close()


class Crawl4AIWebDocumentAdapter:
    """High-level URL/raw-HTML adapter returning only NormalizedDocument."""

    def __init__(
        self,
        config: WebIngestionConfig | None = None,
        *,
        security_policy: URLSecurityPolicy | None = None,
        invoker: CrawlInvoker | None = None,
    ) -> None:
        self.config = config or WebIngestionConfig()
        self.security_policy = security_policy or URLSecurityPolicy(
            allowed_domains=self.config.allowed_domains
        )
        self._invoker = invoker or Crawl4AIInvoker(self.security_policy)

    def supports(self, source: DocumentInput) -> bool:
        return isinstance(source, (UrlInput, RawHtmlInput))

    async def ingest(self, source: UrlInput | RawHtmlInput) -> NormalizedDocument:
        started_at = monotonic()
        crawl_id = uuid4().hex
        crawl_source = source
        if source.kind == "url":
            validated = await self.security_policy.validate(source.url)
            crawl_source = UrlInput(url=validated.url)
        else:
            if source.base_url:
                validated_base = await self.security_policy.validate(source.base_url)
                crawl_source = RawHtmlInput(html=source.html, base_url=validated_base.url)
            if len(source.html.encode("utf-8")) > self.config.max_content_bytes:
                raise ContentTooLarge("The supplied HTML exceeded the configured maximum size.")
        try:
            snapshot = await self._invoker.crawl(crawl_source, self.config)
            if not snapshot.success:
                raise CrawlFailed(
                    "The page could not be crawled successfully.",
                    detail=snapshot.error_message,
                )
            if source.kind == "url" and snapshot.final_url:
                await self.security_policy.validate(snapshot.final_url)
            return normalize_snapshot(
                snapshot,
                source,
                self.config,
                started_at=started_at,
                crawl_id=crawl_id,
            )
        except IngestionError:
            logger.info(
                "web ingestion failed",
                extra={"event": "ingestion_failed", "crawl_id": crawl_id},
            )
            raise

    async def close(self) -> None:
        """Release the reusable browser; suitable for a future app shutdown hook."""

        await self._invoker.close()

    async def __aenter__(self) -> Crawl4AIWebDocumentAdapter:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
