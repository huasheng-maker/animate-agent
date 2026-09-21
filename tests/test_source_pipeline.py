from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from animate_agent.documents.builder import build_document_ir
from animate_agent.ingestion.models import WebIngestionConfig
from animate_agent.ingestion.security import URLSecurityPolicy
from animate_agent.knowledge.models import (
    KnowledgeConcept,
    KnowledgeProcess,
    KnowledgeProcessStep,
    KnowledgeRelationship,
    LessonIR,
    LessonScene,
)
from animate_agent.knowledge.prompts import build_knowledge_prompt
from animate_agent.paths import SAMPLES_DIR
from animate_agent.sources.adapters import (
    GeminiWebSearchAdapter,
    KimiWebReaderAdapter,
    KimiWebSearchAdapter,
    OpenAIWebSearchAdapter,
    WebReaderAdapter,
    normalize_kimi_search_response,
    normalize_web_search_response,
)
from animate_agent.sources.models import (
    QuerySourceInput,
    SourceAsset,
    SourceBlock,
    SourceDocument,
    UrlSourceInput,
)
from animate_agent.sources.resolver import (
    SourceResolver,
    default_web_reader_adapter,
    default_web_search_adapter,
)
from animate_agent.storyboard.prompts import build_storyboard_prompt


class RecordingSearch:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def resolve(self, source: QuerySourceInput) -> list[SourceDocument]:
        self.queries.append(source.query)
        return [
            SourceDocument(
                id="search-doc",
                source_type="web_search",
                content="Official answer",
            )
        ]


class RecordingReader:
    def __init__(self) -> None:
        self.urls: list[str] = []

    async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
        self.urls.append(source.url)
        return [
            SourceDocument(
                id="page-doc",
                source_type="web_page",
                content="Page content",
                url=source.url,
            )
        ]


def test_source_resolver_routes_query_url_and_text_deterministically() -> None:
    search = RecordingSearch()
    reader = RecordingReader()
    resolver = SourceResolver(web_search=search, web_reader=reader)

    query_documents = asyncio.run(resolver.resolve({"type": "query", "query": "Pydantic"}))
    url_documents = asyncio.run(
        resolver.resolve({"type": "url", "url": "https://example.com/guide"})
    )
    text_documents = asyncio.run(
        resolver.resolve({"type": "text", "text": "Local notes", "title": "Notes"})
    )

    assert search.queries == ["Pydantic"]
    assert reader.urls == ["https://example.com/guide"]
    assert query_documents[0].source_type == "web_search"
    assert url_documents[0].source_type == "web_page"
    assert text_documents[0].source_type == "text"


def test_source_resolver_rejects_unsupported_input() -> None:
    with pytest.raises(ValidationError):
        asyncio.run(SourceResolver().resolve({"type": "ftp", "url": "ftp://example.com"}))


def test_kimi_providers_are_selectable_without_llm_tool_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "kimi")
    monkeypatch.setenv("WEB_READER_PROVIDER", "kimi")

    assert isinstance(default_web_search_adapter(), KimiWebSearchAdapter)
    assert isinstance(default_web_reader_adapter(), KimiWebReaderAdapter)


def test_source_document_schema_is_strict_and_runtime_validated() -> None:
    schema = SourceDocument.model_json_schema()

    assert schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        SourceDocument.model_validate(
            {
                "id": "invalid-extra",
                "source_type": "text",
                "content": "content",
                "provider_payload": {},
            }
        )


def _search_payload() -> dict[str, Any]:
    return {
        "id": "resp_test",
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"title": "Official Pydantic docs", "url": "https://docs.pydantic.dev/"}
                    ]
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Pydantic validates Python data at runtime.",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "title": "Official Pydantic docs",
                                "url": "https://docs.pydantic.dev/",
                                "start_index": 0,
                                "end_index": 41,
                            }
                        ],
                    }
                ],
            },
        ],
    }


def test_web_search_response_normalizes_without_leaking_provider_response() -> None:
    documents = normalize_web_search_response(_search_payload(), "Pydantic validation")

    assert len(documents) == 1
    assert documents[0].url == "https://docs.pydantic.dev/"
    assert documents[0].source_type == "web_search"
    assert documents[0].citations[0].title == "Official Pydantic docs"
    assert "output" not in documents[0].metadata


def test_openai_web_search_adapter_uses_responses_hosted_tool() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["tools"] == [{"type": "web_search"}]
        assert body["tool_choice"] == {"type": "web_search"}
        assert body["include"] == ["web_search_call.action.sources"]
        return httpx.Response(200, json=_search_payload())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run() -> list[SourceDocument]:
        try:
            adapter = OpenAIWebSearchAdapter(api_key="test", model="test", client=client)
            return await adapter.resolve(QuerySourceInput(query="Pydantic validation"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].metadata["provider"] == "openai"


def test_gemini_web_search_adapter_normalizes_grounded_sources() -> None:
    chunk = SimpleNamespace(
        web=SimpleNamespace(uri="https://ai.google.dev/gemini-api/docs", title="Gemini docs")
    )
    metadata = SimpleNamespace(
        grounding_chunks=[chunk],
        grounding_supports=[
            SimpleNamespace(
                segment=SimpleNamespace(text="Gemini uses grounding."),
                grounding_chunk_indices=[0],
            )
        ],
    )
    response = SimpleNamespace(
        text="Gemini uses grounding.",
        response_id="gemini-response",
        candidates=[SimpleNamespace(grounding_metadata=metadata)],
    )

    class FakeModels:
        async def generate_content(self, **kwargs: Any) -> object:
            assert kwargs["model"] == "gemini-test"
            assert kwargs["contents"] == "Gemini grounding"
            assert kwargs["config"].tools[0].google_search is not None
            return response

    fake_client = SimpleNamespace(aio=SimpleNamespace(models=FakeModels()))
    adapter = GeminiWebSearchAdapter(
        api_key="test",
        model="gemini-test",
        client=fake_client,
    )

    documents = asyncio.run(adapter.resolve(QuerySourceInput(query="Gemini grounding")))

    assert documents[0].metadata["provider"] == "google"
    assert documents[0].url == "https://ai.google.dev/gemini-api/docs"
    assert documents[0].citations[0].title == "Gemini docs"


def _kimi_search_payload() -> dict[str, Any]:
    return {
        "search_results": [
            {
                "site_name": "Pydantic",
                "title": "Pydantic documentation",
                "url": "https://docs.pydantic.dev/latest/",
                "snippet": "Pydantic validates Python data.",
                "chunks": [
                    {
                        "text": "Pydantic validates Python data at runtime.",
                        "score": 1.25,
                    }
                ],
                "date": "2026-01-01",
                "mime": "text/html",
                "authority": "S",
            }
        ]
    }


def test_kimi_web_search_response_normalizes_without_provider_payload() -> None:
    documents = normalize_kimi_search_response(
        _kimi_search_payload(),
        "Pydantic validation",
        mode="pro",
        request_id="track-test",
    )

    assert len(documents) == 1
    assert documents[0].metadata["provider"] == "kimi"
    assert documents[0].url == "https://docs.pydantic.dev/latest/"
    assert documents[0].citations[0].title == "Pydantic documentation"
    assert documents[0].metadata["provider_api"] == "tools_search_pro"
    assert documents[0].metadata["provider_request_id"] == "track-test"
    assert documents[0].metadata["chunk_scores"] == [1.25]
    assert "search_results" not in documents[0].metadata


def test_kimi_web_search_adapter_uses_official_search_pro_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_KEY", "test")
    monkeypatch.setenv("KIMI_BASE", "https://api.kimi.test")

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://api.kimi.test/tools/search_pro"
        assert request.headers["authorization"] == "Bearer test"
        assert request.headers["x-msh-track-id"]
        assert body == {
            "text_query": "Pydantic validation",
            "limit": 5,
            "timeout_seconds": 30,
        }
        return httpx.Response(
            200,
            headers={"X-Msh-Track-Id": "track-pro"},
            json=_kimi_search_payload(),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run() -> list[SourceDocument]:
        try:
            adapter = KimiWebSearchAdapter(client=client)
            return await adapter.resolve(QuerySourceInput(query="Pydantic validation"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].metadata["provider"] == "kimi"
    assert documents[0].metadata["provider_request_id"] == "track-pro"


def test_kimi_web_search_adapter_supports_official_basic_api() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://api.kimi.test/tools/search"
        assert body["include_content"] is True
        payload = _kimi_search_payload()
        payload["search_results"][0].pop("chunks")
        payload["search_results"][0]["text"] = "Full page text."
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def run() -> list[SourceDocument]:
        try:
            adapter = KimiWebSearchAdapter(
                api_key="test",
                base_url="https://api.kimi.test/tools/search",
                client=client,
                mode="basic",
            )
            return await adapter.resolve(QuerySourceInput(query="Pydantic validation"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].content == "Full page text."
    assert documents[0].metadata["provider_api"] == "tools_search_basic"


def test_web_reader_reads_one_page_with_ssrf_and_size_policy() -> None:
    async def resolver(_hostname: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.com/guide"
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Guide</title></head><body><nav>Ignore</nav>"
                "<main><h1>Guide</h1><p>Safe body.</p></main></body></html>"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = WebReaderAdapter(
        WebIngestionConfig(javascript_enabled=False),
        security_policy=URLSecurityPolicy(resolver=resolver),
        client=client,
    )

    async def run() -> list[SourceDocument]:
        try:
            return await adapter.resolve(UrlSourceInput(url="https://example.com/guide"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].title == "Guide"
    assert "Safe body." in documents[0].content
    assert "Ignore" not in documents[0].content


def test_web_reader_detects_rst_from_url_when_server_uses_text_plain() -> None:
    async def resolver(_hostname: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="=====\nGuide\n=====\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = WebReaderAdapter(
        WebIngestionConfig(javascript_enabled=False),
        security_policy=URLSecurityPolicy(resolver=resolver),
        client=client,
    )

    async def run() -> list[SourceDocument]:
        try:
            return await adapter.resolve(UrlSourceInput(url="https://example.com/guide.rst"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].metadata["content_format"] == "rst"


def test_kimi_web_reader_validates_url_and_uses_official_fetch_api() -> None:
    async def resolver(_hostname: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://api.kimi.test/tools/fetch"
        assert request.headers["authorization"] == "Bearer test"
        assert request.headers["accept"] == "application/json"
        assert request.headers["x-msh-track-id"]
        assert body == {"url": "https://example.com/guide"}
        return httpx.Response(
            200,
            headers={"X-Msh-Track-Id": "track-fetch"},
            json={
                "url": "https://example.com/guide",
                "title": "Guide",
                "markdown": "# Guide\n\nManaged page content.",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = KimiWebReaderAdapter(
        WebIngestionConfig(javascript_enabled=False),
        api_key="test",
        base_url="https://api.kimi.test/tools/fetch",
        security_policy=URLSecurityPolicy(resolver=resolver),
        client=client,
    )

    async def run() -> list[SourceDocument]:
        try:
            return await adapter.resolve(UrlSourceInput(url="https://example.com/guide"))
        finally:
            await client.aclose()

    documents = asyncio.run(run())
    assert documents[0].metadata["provider"] == "kimi"
    assert documents[0].metadata["provider_api"] == "tools_fetch"
    assert documents[0].metadata["provider_request_id"] == "track-fetch"
    assert documents[0].title == "Guide"
    assert documents[0].metadata["content_format"] == "markdown"
    assert "Managed page content." in documents[0].content


def test_source_documents_build_document_ir_with_provenance() -> None:
    sources = [
        SourceDocument(
            id="official-guide",
            source_type="web_page",
            title="Guide",
            content="# Install\n\nRun the safe command.",
            url="https://example.com/guide",
            metadata={"content_format": "markdown"},
        )
    ]

    document = build_document_ir(sources)

    assert document.sources[0].id == "official-guide"
    assert document.sections[0].blocks[0].source_id == "official-guide"
    assert document.source.url == "https://example.com/guide"


def test_structured_source_blocks_and_assets_survive_document_boundary() -> None:
    source = SourceDocument(
        id="rich-guide",
        source_type="web_page",
        title="Rich guide",
        content="Structured fallback content.",
        blocks=(
            SourceBlock(id="section-model", type="heading", text="Model", level=2),
            SourceBlock(
                id="section-model-block-1",
                type="equation",
                text="y = f(x)",
                language="latex",
            ),
            SourceBlock(
                id="section-model-block-2",
                type="table",
                text="input | output\nx | y",
                metadata={"rows": [["input", "output"], ["x", "y"]]},
            ),
            SourceBlock(
                id="section-model-block-3",
                type="diagram",
                text="Input-to-output diagram",
                url="https://example.com/diagram.svg",
                asset_id="asset-diagram",
            ),
        ),
        assets=(
            SourceAsset(
                id="asset-diagram",
                type="diagram",
                url="https://example.com/diagram.svg",
                alt_text="Input-to-output diagram",
            ),
        ),
    )

    document = build_document_ir([source])

    assert [block.type for block in document.sections[0].blocks] == [
        "equation",
        "table",
        "diagram",
    ]
    assert document.sections[0].blocks[1].metadata["rows"][1] == ["x", "y"]
    assert document.sections[0].blocks[2].asset_id == "asset-diagram"
    assert document.sources[0].assets[0].id == "asset-diagram"
    assert all(block.source_id == "rich-guide" for block in document.sections[0].blocks)


def test_markdown_rich_blocks_are_not_flattened(tmp_path: Path) -> None:
    source = tmp_path / "rich.md"
    source.write_text(
        "# Rich\n\n> [!NOTE] Keep this condition.\n\n"
        "| Input | Output |\n| --- | --- |\n| x | y |\n\n"
        "```math\ny = f(x)\n```\n",
        encoding="utf-8",
    )

    documents = asyncio.run(SourceResolver().resolve({"type": "file", "path": source}))
    document = build_document_ir(documents)

    assert [block.type for block in document.sections[0].blocks] == [
        "callout",
        "table",
        "equation",
    ]
    assert "type=table" in build_knowledge_prompt(document)


def test_semantic_knowledge_is_available_to_storyboard_planning() -> None:
    lesson = LessonIR(
        lesson_id="lesson-rich",
        document_id="rich-guide",
        title="Rich lesson",
        subject="Systems",
        summary="A state drives a two-step process.",
        learning_objectives=["Understand the state", "Trace the process"],
        concepts=[
            KnowledgeConcept(
                name="Desired state",
                definition="The target configuration.",
                source_refs=["section-model-block-1"],
            )
        ],
        relationships=[
            KnowledgeRelationship(
                source="Observed state",
                target="Reconciliation",
                relation="causes",
                explanation="A difference triggers the control loop.",
                source_refs=["section-model-block-2"],
            )
        ],
        processes=[
            KnowledgeProcess(
                name="Control loop",
                purpose="Move actual state toward desired state.",
                source_refs=["section-model-block-2"],
                steps=[
                    KnowledgeProcessStep(
                        order=1,
                        title="Observe",
                        description="Read current state.",
                        source_refs=["section-model-block-2"],
                    ),
                    KnowledgeProcessStep(
                        order=2,
                        title="Act",
                        description="Apply the required change.",
                        source_refs=["section-model-block-3"],
                    ),
                ],
            )
        ],
        scenes=[
            LessonScene(
                id="scene-1",
                title="Control loop",
                objective="Understand how observation triggers action.",
                narration=(
                    "Compare the observed state with the desired state, then apply the "
                    "change required to bring the two states closer together."
                ),
                key_points=["Observed state", "Desired state"],
                source_refs=["section-model-block-1", "section-model-block-2"],
            )
        ],
    )

    prompt = build_storyboard_prompt(lesson)

    assert "Observed state --causes--> Reconciliation" in prompt
    assert "1. Observe" in prompt
    assert "2. Act" in prompt


def test_rst_source_promotes_adorned_title_without_teaching_markup() -> None:
    document = build_document_ir(
        [
            SourceDocument(
                id="rst-guide",
                source_type="web_page",
                title="quickstart.rst",
                content=(
                    "==========\nQuickstart\n==========\n\n.. note::\n\nInstall\n=======\n\nRun it."
                ),
                metadata={"content_format": "rst"},
            )
        ]
    )

    texts = [block.text for section in document.sections for block in section.blocks]
    assert document.sections[0].title == "Quickstart"
    assert "==========" not in texts
    assert ".. note::" not in texts


def test_file_input_routes_through_file_adapter(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nA local fact.", encoding="utf-8")

    documents = asyncio.run(SourceResolver().resolve({"type": "file", "path": source}))

    assert documents[0].source_type == "file"
    assert "A local fact." in documents[0].content


def test_kubernetes_markdown_shortcodes_do_not_leak_into_source_document() -> None:
    source = SAMPLES_DIR / "controller.md"

    documents = asyncio.run(SourceResolver().resolve({"type": "file", "path": source}))

    content = documents[0].content
    assert documents[0].title == "Controller pattern"
    assert "{{<" not in content
    assert "{{%" not in content
    assert not content.startswith("# \n")
    assert "API server" in content
    assert "objects" in content
    assert "For simplicity, this page omits" not in content
