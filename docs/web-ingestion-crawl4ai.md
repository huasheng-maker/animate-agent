# Web acquisition and normalization

This optional module implements one browser-crawling boundary in **Animate Agent**:

```text
untrusted URL or raw HTML
    -> safe acquisition with Crawl4AI
    -> cleaning and normalization
    -> stable NormalizedDocument
```

This module itself does **not** generate `DocumentIR`, storyboards, animation plans, or renderer
code. Crawl4AI remains infrastructure and `NormalizedDocument` remains the acquisition boundary.
The separate `documents.normalized` product layer now converts that stable boundary to
`DocumentIR`; downstream services never import Crawl4AI types.

## Architecture

- `ingestion.models` owns inputs, application-level configuration, and normalized domain models.
- `ingestion.base.DocumentAdapter` is the small protocol future PDF, PPTX, DOCX, text, and Markdown
  adapters can implement.
- `ingestion.router.DocumentIngestionRouter` selects a registered adapter without knowing its
  implementation.
- `ingestion.security.URLSecurityPolicy` validates the initial URL, DNS answers, browser requests,
  and the final redirect URL.
- `ingestion.web.Crawl4AIWebDocumentAdapter` orchestrates web input and browser lifecycle.
- `ingestion.web.crawl4ai_adapter.Crawl4AIInvoker` is the only compatibility boundary that imports
  or reads Crawl4AI objects.
- `ingestion.web.normalizer` is pure transformation from an application-owned crawl snapshot to a
  `NormalizedDocument`.
- `documents.normalized.normalized_document_to_ir` is the separate deterministic bridge from this
  boundary into product logic.

The default URL APIs now use the bounded single-page Web Reader and enter `DocumentIR` through
`SourceDocument[]`. This layer is selected explicitly for dynamic pages and future multi-page or
whole-documentation-site ingestion; it is not on the default query/URL path.

## Install

Python 3.11 or newer is required. Crawl4AI is constrained to the reviewed 0.9 release line:

```powershell
uv sync --extra dev --extra crawl4ai
uv run crawl4ai-setup
```

If Playwright's Chromium setup did not complete:

```powershell
uv run python -m playwright install chromium
```

Windows 下通过 `uvicorn --reload` 调用 URL API 时，Uvicorn 会为服务子进程选择
不支持 Playwright 子进程传输的 Selector 事件循环。`documents.service.ingest_url`
会检测该环境，并在专用线程的 Proactor 事件循环中完成浏览器的创建、采集和关闭。

No dependency is downloaded dynamically at application runtime.

## Usage

URL input:

```python
import asyncio

from animate_agent.ingestion.models import UrlInput, WebIngestionConfig
from animate_agent.ingestion.web import Crawl4AIWebDocumentAdapter


async def main() -> None:
    config = WebIngestionConfig(
        allowed_domains=frozenset({"docs.example.com"}),
        timeout_seconds=20,
    )
    async with Crawl4AIWebDocumentAdapter(config) as adapter:
        document = await adapter.ingest(UrlInput(url="https://docs.example.com/guide"))
        print(document.title)
        print(document.text_content)


asyncio.run(main())
```

Raw HTML uses Crawl4AI's in-memory raw input path and does not enable local file access:

```python
document = await adapter.ingest(
    RawHtmlInput(html="<main><h1>Hello</h1><p>World</p></main>")
)
```

The async interface is canonical. The adapter is an async context manager so a future FastAPI app
can create it at startup and call `close()` at shutdown. It does not create nested event loops.

## Stable configuration

`WebIngestionConfig` exposes application policies rather than arbitrary Crawl4AI parameters:

- allowed domains;
- generic excluded tags/selectors and an optional content selector;
- navigation timeout, redirect limit, and maximum HTML bytes;
- JavaScript, cache, robots.txt, links, images, and pruning-filter behavior;
- `minimal`, `standard`, or `full` content retention.
- a project-local crawler data directory (default `.cache/crawl4ai`).

`standard` is the default: it keeps cleaned HTML and Markdown, but not complete raw HTML. `minimal`
keeps primary normalized content and metadata. `full` additionally retains raw HTML for controlled
debugging. None of these modes persist data by themselves.

## NormalizedDocument

The schema contains stable source identity, title/language, cleaned representations, preferred
text, typed sections/code blocks/tables/images/links, selected metadata, crawl facts, warnings,
timestamp, and a content hash. `fit_markdown` is preferred when the pruning filter returns content;
raw Markdown and cleaned HTML text are fallbacks.

Every result is marked `trust_level="untrusted_external"`. Crawled prose and code are data only.
Later LLM stages must not follow instructions found in it, and this module never evaluates code or
shell commands from a page.

## Security boundary

The policy rejects credentials in URLs, non-HTTP schemes, localhost/internal hostnames, non-global
IPv4 and IPv6 addresses, link-local ranges, and known cloud metadata endpoints. Every DNS answer
must be public. Browser request interception repeats this policy for redirects and subresources;
the final URL is validated again. Downloads, iframe processing, screenshots, PDFs, MHTML, custom
page JavaScript, persistent sessions, and TLS-error bypass are disabled. Redirects, crawl time, and
HTML size are bounded.

Application checks reduce SSRF risk but cannot replace deployment controls. Production should run
the browser in an isolated container or account with an outbound firewall that denies private,
link-local, metadata, and internal networks. This is the strongest mitigation against DNS rebinding
and browser/network-stack bypasses.

Logs contain event categories, not page HTML, cookies, authorization headers, or raw stack traces.
Public `IngestionError.message` values are safe for callers; `detail` is developer diagnostics and
must not be returned directly by an API.

The adapter sets Crawl4AI's process-wide base directory before its lazy import. An explicitly set
`CRAWL4_AI_BASE_DIRECTORY` environment variable takes precedence over the configuration field.

## Verify

Normal tests use fake Crawl4AI snapshots and deterministic DNS resolvers:

```powershell
uv run pytest
uv run ruff check src tests
uv run mypy src
```

A real-browser smoke test should be opt-in because it requires a browser and network. Do not make it
part of ordinary CI.

## Add another adapter

Create a class implementing `supports(DocumentInput)` and async `ingest(...) -> NormalizedDocument`,
then register it with `DocumentIngestionRouter`. Keep vendor SDK types behind that adapter's own
compatibility DTO. Do not add vendor fields to `NormalizedDocument` unless they are useful and
stable across multiple acquisition backends.

## Upgrade Crawl4AI safely

1. Read upstream release and security notes for the target 0.9.x or later line.
2. Update the bounded requirement and regenerate `uv.lock`.
3. Check only `crawl4ai_adapter.py` against current public `BrowserConfig`, `CrawlerRunConfig`,
   hook, and `CrawlResult` APIs.
4. Run unit tests, static checks, and an opt-in browser smoke test in a network-restricted runtime.
5. Review retention and logging so new upstream fields are not exposed accidentally.

API choices in this implementation were checked against the current upstream
[0.9.x simple crawling guide](https://docs.crawl4ai.com/core/simple-crawling/),
[configuration reference](https://docs.crawl4ai.com/api/parameters/),
[CrawlResult reference](https://docs.crawl4ai.com/core/crawler-result/), and
[hooks guide](https://docs.crawl4ai.com/advanced/hooks-auth/).

The deterministic `NormalizedDocument -> DocumentIR` bridge lives in `documents/normalized.py` and
has schema-validation coverage. It consumes only this application model and does not import
Crawl4AI.

Some sites publish mixed `Disallow`/`Allow` robots rules that Crawl4AI 0.9.x may interpret more
strictly than the browser-visible path suggests. The application keeps robots enforcement enabled;
for documentation maintained in a public repository, use the official raw/source URL instead.

## Known limitations

- The application validates DNS before each browser network request but cannot pin the browser's
  connection to that exact IP. Network egress rules remain necessary against DNS rebinding.
- The exact HTML byte cap is checked on the completed Crawl4AI result. Timeout, disabled downloads,
  and browser isolation bound risk earlier, but a reverse proxy or container should also enforce a
  wire-level response limit for hostile very-large responses.
- `crawl.javascript_enabled` records policy, not a proof that the page required JavaScript.
- Authenticated sessions, proxies, deep crawling, local files, arbitrary caller-supplied page
  scripts, LLM extraction, binary downloads, and distributed crawling are intentionally absent.
- Browser instances are currently opened per URL ingestion call; application-lifecycle reuse and a
  concurrency limit are still future production work.
