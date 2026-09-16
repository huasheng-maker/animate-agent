"""End-to-end animation orchestration for every supported source input."""

from __future__ import annotations

from pathlib import Path

from animate_agent.documents.builder import DocumentIRBuilder
from animate_agent.documents.service import ingest_source
from animate_agent.knowledge.service import generate_lesson
from animate_agent.llm import require_llm_config
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.rendering.models import RenderSpec
from animate_agent.sources.models import SourceInput, UrlSourceInput
from animate_agent.sources.resolver import SourceResolver
from animate_agent.storyboard.service import DEFAULT_GENERATED_DIR, generate_storyboard


async def generate_animation(
    source: SourceInput,
    *,
    output_dir: Path = DEFAULT_GENERATED_DIR,
    resolver: SourceResolver | None = None,
    document_builder: DocumentIRBuilder | None = None,
) -> RenderSpec:
    """Run SourceInput -> DocumentIR -> LessonIR -> StoryboardIR -> RenderSpec."""

    # Fail before any external acquisition when the two model-backed stages
    # cannot run. Query inputs still validate their separate Web Search key in
    # OpenAIWebSearchAdapter.
    require_llm_config()
    document = await ingest_source(
        source,
        resolver=resolver,
        builder=document_builder,
    )
    lesson = await generate_lesson(document, output_dir=output_dir)
    storyboard = await generate_storyboard(lesson, document, output_dir=output_dir)
    spec = layout_storyboard(storyboard)

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"render-{storyboard.storyboard_id}.json"
    destination.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return spec


async def generate_animation_from_url(
    url: str,
    *,
    output_dir: Path = DEFAULT_GENERATED_DIR,
) -> RenderSpec:
    """Backward-compatible URL wrapper around the generic orchestrator."""

    return await generate_animation(UrlSourceInput(url=url), output_dir=output_dir)
