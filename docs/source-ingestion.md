# Unified source ingestion

## Architecture

```text
query -> Gemini/OpenAI/Kimi Search -----------┐
url   -> local or Kimi single-page Reader     |
text  -> TextAdapter                          |-> SourceDocument[] -> DocumentIRBuilder
file  -> FileAdapter                          |
explicit dynamic/multi-page -> Crawl4AIAdapter┘
```

`SourceResolver` uses deterministic routing. An LLM never chooses the ingestion tool. Direct URLs
are read as pages; they are not passed to search as fake queries. Acquisition adapters return only
Animate Agent models, never provider SDK responses.

## Domain boundary

`sources/models.py` defines strict Pydantic v2 models. Pydantic is the single source of truth for
runtime validation, Python typing, and generated JSON Schema; there is no separately maintained
TypeScript interface or handwritten JSON schema.

```python
class SourceDocument:
    id: str
    source_type: Literal["web_search", "web_page", "text", "file", "pdf"]
    title: str | None
    content: str
    url: str | None
    metadata: dict[str, JsonValue]
    citations: tuple[SourceCitation, ...]
```

`DocumentIRBuilder` only accepts a sequence of these objects. It does not fetch, search, or import
Crawl4AI. `DocumentIR.sources[]` retains each source record, and every generated block has a
`source_id`, preserving the chain `Storyboard -> Lesson source_refs -> DocumentIR block -> source`.

## Web Search

The default adapter uses the official Google GenAI SDK and Gemini Google Search grounding. Set
`GEMINI_API_KEY`; optionally override `GEMINI_WEB_SEARCH_MODEL`. It normalizes grounded chunks,
support segments, titles, URLs, and citations into `SourceDocument[]`. Raw SDK responses never
cross the adapter boundary.

OpenAI hosted Web Search remains available by setting `WEB_SEARCH_PROVIDER=openai`,
`OPENAI_API_KEY`, and optionally `OPENAI_WEB_SEARCH_MODEL`. That adapter calls the Responses API
with `web_search` and requests `web_search_call.action.sources`.

Kimi's official Tools API is available with `WEB_SEARCH_PROVIDER=kimi`. It reuses the existing
`KIMI_KEY` and `KIMI_BASE`; no separate web-service key is required. The default
`KIMI_WEB_SEARCH_MODE=pro` calls `/v1/tools/search_pro`, because its ranked `chunks` are intended
for RAG, agents, and LLM input. Set the mode to `basic` to call `/v1/tools/search`; Basic sends
`include_content=true` in this application so DocumentIR receives useful source text. Both response
shapes are normalized into `SourceDocument[]`, and provider payloads do not cross the boundary.

All adapters mark retrieved material as untrusted. Unit tests mock external SDKs/APIs and do not
access the internet.

```python
from animate_agent.sources.models import QuerySourceInput
from animate_agent.sources.resolver import SourceResolver

sources = await SourceResolver().resolve(QuerySourceInput(query="Pydantic runtime validation"))
```

The equivalent API is `POST /api/documents/from-query` with `{"query": "..."}`.

## Web Reader and security

The default local Reader fetches one page only. It validates `http`/`https`, rejects credentials, localhost,
private/link-local/reserved/metadata addresses, validates every redirect, disables proxy environment
inheritance, bounds redirect count, timeout and payload size, restricts content types, and extracts
the main `main`/`article`/`role=main` content while removing navigation, scripts, forms, cookie UI,
sidebars, and similar noise.

Kimi's official Tools Fetch API is optional. Set `WEB_READER_PROVIDER=kimi`; the adapter reuses
`KIMI_KEY`/`KIMI_BASE` and calls `/v1/tools/fetch`. It validates the URL locally before sending it
to Kimi, sends exactly one URL, bounds timeout and response size, validates the JSON response, and
normalizes its title, final URL, and Markdown into one `SourceDocument`.

All external content is marked untrusted. Knowledge/fidelity prompts delimit source content and
explicitly forbid following instructions embedded in it. The application does not grant source
text tool permissions, shell/file access, secret access, or renderer policy control. Production
deployments still need process/container isolation and outbound network controls.

## Optional Crawl4AI

Crawl4AI is no longer a core dependency. Install it only when required:

```powershell
uv sync --extra dev --extra crawl4ai
uv run crawl4ai-setup
```

Then explicitly instantiate `animate_agent.sources.crawl4ai.Crawl4AIAdapter`. The existing
`NormalizedDocument` and crawler compatibility DTOs remain as internal legacy infrastructure.

## DeepSeek and Kimi

Gemini, OpenAI, or Kimi Tools API performs Web Search. The same Kimi project key may also power the
later Knowledge and Storyboard LLM stages through the existing OpenAI-compatible client.
Configure one provider in `.env` (never commit real keys):

```dotenv
DEEPSEEK_KEY=...
DEEPSEEK_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro

# Or Kimi takes precedence when KIMI_KEY is set:
KIMI_KEY=...
KIMI_BASE=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.6
```

The application loads the selected model provider in `llm.load_llm_config()`. Kimi Tools requests
reuse the same project API credential without exposing it to source content or downstream IR.
