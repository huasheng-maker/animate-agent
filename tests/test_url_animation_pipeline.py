from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pytest import LogCaptureFixture, MonkeyPatch, importorskip

import animate_agent.animation.service as animation_service
from animate_agent.documents.models import DocumentBlock, DocumentIR, DocumentSource, Section
from animate_agent.documents.normalized import normalized_document_to_ir
from animate_agent.documents.service import ingest_url
from animate_agent.ingestion.exceptions import BlockedAddress, RobotsDenied
from animate_agent.ingestion.models import (
    CrawlInfo,
    NormalizedDocument,
    RawHtmlInput,
    SourceType,
    UrlInput,
    WebIngestionConfig,
)
from animate_agent.ingestion.security import URLSecurityPolicy
from animate_agent.ingestion.web import Crawl4AIWebDocumentAdapter
from animate_agent.ingestion.web.contracts import CrawlSnapshot
from animate_agent.knowledge.models import LessonIR, LessonScene
from animate_agent.llm import LLMConfig
from animate_agent.paths import STORYBOARD_SAMPLES_DIR
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.rendering.models import RenderSpec
from animate_agent.sources.adapters import FileAdapter
from animate_agent.sources.models import (
    FileSourceInput,
    QuerySourceInput,
    SourceDocument,
    UrlSourceInput,
)
from animate_agent.sources.resolver import SourceResolver
from animate_agent.storyboard.models import StoryboardIR


def _normalized_document() -> NormalizedDocument:
    return NormalizedDocument(
        document_id="safe-document",
        source_type=SourceType.URL,
        source_url="https://example.com/requested",
        canonical_url="http://127.0.0.1/private",
        title="Safe title",
        cleaned_html="<main><h2>Install</h2><p>Run the safe command.</p></main>",
        text_content="Run the safe command.",
        crawl_timestamp=datetime.now(UTC),
        content_hash="abc",
        crawl=CrawlInfo(
            crawl_id="crawl-1",
            requested_url="https://example.com/requested",
            final_url="https://example.com/final",
            javascript_enabled=True,
            content_filter_applied=True,
            duration_ms=1,
        ),
    )


def _document() -> DocumentIR:
    return DocumentIR(
        document_id="safe-document",
        title="Safe title",
        source=DocumentSource(type="url", url="https://example.com/final"),
        sections=[
            Section(
                id="section-install",
                title="Install",
                level=2,
                blocks=[
                    DocumentBlock(
                        id="section-install-block-1",
                        type="paragraph",
                        text="Run the safe command.",
                    )
                ],
            )
        ],
    )


def _lesson() -> LessonIR:
    return LessonIR(
        lesson_id="lesson-safe",
        document_id="safe-document",
        title="Safe lesson",
        subject="Testing",
        summary="A deterministic test lesson.",
        learning_objectives=["Understand the flow", "Inspect the output"],
        scenes=[
            LessonScene(
                id="lesson-scene",
                title="The flow",
                objective="Understand the complete safe animation flow.",
                narration=(
                    "Follow the validated document through each controlled stage until it "
                    "becomes a render specification."
                ),
                key_points=["Validated input", "Controlled output"],
                source_refs=["section-install-block-1"],
            )
        ],
    )


def _sample_storyboard() -> StoryboardIR:
    source = STORYBOARD_SAMPLES_DIR / "robot_obstacle_avoidance.json"
    return StoryboardIR.model_validate_json(source.read_text(encoding="utf-8"))


def test_normalized_document_maps_to_document_ir_without_trusting_canonical_url() -> None:
    document = normalized_document_to_ir(_normalized_document())

    assert document.document_id == "safe-document"
    assert document.source.url == "https://example.com/final"
    assert document.sections[0].blocks[0].text == "Run the safe command."


def test_url_ingestion_uses_the_source_resolver(tmp_path: Path) -> None:
    class FakeReader:
        async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
            assert source.url == "https://example.com/requested"
            return [
                SourceDocument(
                    id="safe-document",
                    source_type="web_page",
                    title="Safe title",
                    content="# Install\n\nRun the safe command.",
                    url="https://example.com/final",
                    metadata={"content_format": "markdown"},
                )
            ]

    document = asyncio.run(
        ingest_url(
            "https://example.com/requested",
            output_dir=tmp_path,
            resolver=SourceResolver(web_reader=FakeReader()),
        )
    )

    assert document.source.url == "https://example.com/final"
    assert (tmp_path / "safe-document.json").is_file()


def test_security_policy_blocks_loopback_without_resolving_dns() -> None:
    async def check() -> None:
        try:
            await URLSecurityPolicy().validate("http://127.0.0.1/private")
        except BlockedAddress:
            return
        raise AssertionError("loopback URL was not blocked")

    asyncio.run(check())


def test_crawler_reports_robots_denial_as_a_specific_safe_error() -> None:
    class RobotsDeniedInvoker:
        async def crawl(
            self, source: UrlInput | RawHtmlInput, config: WebIngestionConfig
        ) -> CrawlSnapshot:
            return CrawlSnapshot(
                success=False,
                requested_url=source.url,
                final_url=source.url,
                status_code=403,
                error_message="Access denied by robots.txt",
            )

        async def close(self) -> None:
            return None

    async def check() -> None:
        adapter = Crawl4AIWebDocumentAdapter(invoker=RobotsDeniedInvoker())
        try:
            await adapter.ingest(UrlInput(url="https://example.com/guide"))
        except RobotsDenied as exc:
            assert "raw/source URL" in str(exc)
            return
        raise AssertionError("robots denial was not surfaced")

    asyncio.run(check())


def test_generic_animation_service_runs_all_stages_and_persists_render_spec(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None:
    calls: list[str] = []
    progress: list[tuple[str, dict[str, object]]] = []

    def observe(kind: str, **data: object) -> None:
        progress.append((kind, data))

    monkeypatch.setattr(animation_service, "report_progress", observe)
    storyboard = _sample_storyboard()

    class FakeReader:
        async def resolve(self, source: UrlSourceInput) -> list[SourceDocument]:
            calls.append(f"ingest:{source.url}")
            return [
                SourceDocument(
                    id="safe-document",
                    source_type="web_page",
                    title="Safe title",
                    content="# Install\n\nRun the safe command.",
                    url="https://example.com/final",
                    metadata={"content_format": "markdown"},
                )
            ]

    async def fake_lesson(document: DocumentIR, *, output_dir: Path) -> LessonIR:
        calls.append(f"lesson:{document.document_id}:{output_dir.name}")
        return _lesson()

    async def fake_storyboard(
        lesson: LessonIR, document: DocumentIR, *, output_dir: Path
    ) -> StoryboardIR:
        calls.append(f"storyboard:{lesson.lesson_id}:{document.document_id}:{output_dir.name}")
        return storyboard

    monkeypatch.setattr(animation_service, "generate_lesson", fake_lesson)
    monkeypatch.setattr(animation_service, "generate_storyboard", fake_storyboard)
    monkeypatch.setattr(
        animation_service,
        "require_llm_config",
        lambda: LLMConfig(base_url="https://example.com", api_key="test", model="test"),
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.animate_agent.animation"):
        spec = asyncio.run(
            animation_service.generate_animation(
                UrlSourceInput(url="https://example.com/requested"),
                output_dir=tmp_path,
                resolver=SourceResolver(web_reader=FakeReader()),
            )
        )

    assert [item.split(":", 1)[0] for item in calls] == ["ingest", "lesson", "storyboard"]
    assert spec.scenes
    assert [data["name"] for kind, data in progress if kind == "artifact"] == [
        "document",
        "lesson",
        "storyboard",
    ]
    assert [data["stage"] for kind, data in progress if kind == "stage"] == [
        "source_ingestion",
        "lesson_generation",
        "storyboard_generation",
        "layout",
        "animation_ir_compile",
        "persist",
    ]
    run_directories = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_directories) == 1
    run_directory = run_directories[0]
    assert {path.name for path in run_directory.iterdir()} == {
        "01-source-document.json",
        "02-document-ir.json",
        "03-lesson-ir.json",
        "04-storyboard-ir.json",
        "05-animation-ir.json",
        "06-render-spec.json",
    }
    persisted_sources = json.loads(
        (run_directory / "01-source-document.json").read_text(encoding="utf-8")
    )
    assert [source["id"] for source in persisted_sources] == ["safe-document"]
    messages = [record.getMessage() for record in caplog.records]
    for stage in (
        "configuration",
        "source_ingestion",
        "lesson_generation",
        "storyboard_generation",
        "layout",
        "persist",
    ):
        assert any(f"stage={stage} status=started" in message for message in messages)
        assert any(f"stage={stage} status=completed" in message for message in messages)
    assert any("stage=pipeline status=completed" in message for message in messages)


def test_animation_logs_the_stage_that_failed(
    monkeypatch: MonkeyPatch, tmp_path: Path, caplog: LogCaptureFixture
) -> None:
    async def fake_ingest(source: UrlSourceInput, **_: object) -> DocumentIR:
        assert source.url == "https://example.com/requested"
        return _document()

    async def broken_lesson(document: DocumentIR, *, output_dir: Path) -> LessonIR:
        assert document.document_id == "safe-document"
        assert output_dir.parent == tmp_path
        raise RuntimeError("model transport stopped")

    monkeypatch.setattr(animation_service, "ingest_source", fake_ingest)
    monkeypatch.setattr(animation_service, "generate_lesson", broken_lesson)
    monkeypatch.setattr(
        animation_service,
        "require_llm_config",
        lambda: LLMConfig(base_url="https://example.com", api_key="test", model="test"),
    )

    with caplog.at_level(logging.INFO, logger="uvicorn.error.animate_agent.animation"):
        try:
            asyncio.run(
                animation_service.generate_animation(
                    UrlSourceInput(url="https://example.com/requested"), output_dir=tmp_path
                )
            )
        except RuntimeError as exc:
            assert str(exc) == "model transport stopped"
        else:
            raise AssertionError("animation failure was not raised")

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "stage=lesson_generation status=failed" in message
        and "error_type=RuntimeError" in message
        for message in messages
    )


def test_animation_api_returns_render_spec(monkeypatch: MonkeyPatch) -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    spec = layout_storyboard(_sample_storyboard())

    async def fake_generate(url: str) -> RenderSpec:
        assert url == "https://example.com/"
        return spec

    monkeypatch.setattr(api_module, "generate_animation_from_url", fake_generate)
    response = TestClient(api_module.app).post(
        "/api/animations/from-url", json={"url": "https://example.com"}
    )

    assert response.status_code == 200
    assert response.json()["storyboard_id"] == spec.storyboard_id


def test_query_api_routes_through_source_ingestion(monkeypatch: MonkeyPatch) -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    async def fake_ingest(source: QuerySourceInput) -> DocumentIR:
        assert source.query == "runtime validation"
        return _document()

    monkeypatch.setattr(api_module, "ingest_source", fake_ingest)
    response = TestClient(api_module.app).post(
        "/api/documents/from-query", json={"query": "runtime validation"}
    )

    assert response.status_code == 200
    assert response.json()["document_id"] == "safe-document"


def test_query_animation_api_uses_generic_orchestrator(monkeypatch: MonkeyPatch) -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    spec = layout_storyboard(_sample_storyboard())

    async def fake_generate(source: QuerySourceInput) -> RenderSpec:
        assert source.query == "runtime validation"
        return spec

    monkeypatch.setattr(api_module, "generate_animation", fake_generate)
    response = TestClient(api_module.app).post(
        "/api/animations/from-query", json={"query": "runtime validation"}
    )

    assert response.status_code == 200
    assert response.json()["storyboard_id"] == spec.storyboard_id


def test_uploaded_file_can_be_inspected_as_document_ir() -> None:
    importorskip("multipart", reason="python-multipart is required by the file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    response = TestClient(api_module.app).post(
        "/api/documents/from-file",
        files={"file": ("lesson.md", b"# Lesson\n\nA real fact.", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["sections"][0]["blocks"][0]["text"] == "A real fact."


def test_uploaded_file_animation_uses_generic_orchestrator(monkeypatch: MonkeyPatch) -> None:
    importorskip("multipart", reason="python-multipart is required by the file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    spec = layout_storyboard(_sample_storyboard())
    temporary_path: Path | None = None

    async def fake_generate(source: FileSourceInput) -> RenderSpec:
        nonlocal temporary_path
        temporary_path = source.path
        assert source.path.suffix == ".md"
        assert source.path.read_text(encoding="utf-8") == "# Lesson\n\nA real fact."
        return spec

    monkeypatch.setattr(api_module, "generate_animation", fake_generate)
    response = TestClient(api_module.app).post(
        "/api/animations/from-file",
        files={"file": ("lesson.md", b"# Lesson\n\nA real fact.", "text/markdown")},
    )

    assert response.status_code == 200
    assert response.json()["storyboard_id"] == spec.storyboard_id
    assert temporary_path is not None
    assert not temporary_path.exists()


def test_controller_example_uses_allowlisted_file_source(monkeypatch: MonkeyPatch) -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    spec = layout_storyboard(_sample_storyboard())

    async def fake_generate(source: FileSourceInput) -> RenderSpec:
        assert source.path.name == "controller.md"
        assert source.path.is_absolute()
        return spec

    monkeypatch.setattr(api_module, "generate_animation", fake_generate)
    response = TestClient(api_module.app).post(
        "/api/animations/from-example", json={"example_id": "controller"}
    )

    assert response.status_code == 200
    assert response.json()["storyboard_id"] == spec.storyboard_id


def test_unknown_animation_example_cannot_select_a_filesystem_path() -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    response = TestClient(api_module.app).post(
        "/api/animations/from-example", json={"example_id": "../../controller"}
    )

    assert response.status_code == 404


def test_controller_preview_is_a_drawable_reviewed_storyboard() -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    response = TestClient(api_module.app).get(
        "/api/animations/examples/controller/preview"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["storyboard_id"] == "storyboard-kubernetes-controller-loop"
    assert len(payload["scenes"]) == 2
    assert all(scene["elements"] for scene in payload["scenes"])


def test_latest_controller_animation_recovers_a_persisted_result(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    importorskip("multipart", reason="python-multipart is required by the existing file API")
    from fastapi.testclient import TestClient

    import animate_agent.api as api_module

    source_path = api_module.EXAMPLE_DOCUMENTS["controller"]
    source = FileAdapter().resolve_sync(FileSourceInput(path=source_path))[0]
    storyboard_id = f"storyboard-lesson-{source.id}"
    spec = layout_storyboard(_sample_storyboard()).model_copy(
        update={"document_id": source.id, "storyboard_id": storyboard_id}
    )
    run_directory = tmp_path / "test-run"
    run_directory.mkdir()
    (run_directory / "06-render-spec.json").write_text(
        spec.model_dump_json(indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(api_module, "DEFAULT_RUNS_DIR", tmp_path)

    response = TestClient(api_module.app).get(
        "/api/animations/examples/controller/latest"
    )

    assert response.status_code == 200
    assert response.json()["document_id"] == source.id
    assert response.json()["storyboard_id"] == storyboard_id
