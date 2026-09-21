"""End-to-end animation orchestration for every supported source input."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from animate_agent.animation.artifacts import (
    DEFAULT_RUNS_DIR,
    bind_run_directory,
    persist_animation_ir,
    persist_document_ir,
    persist_lesson_ir,
    persist_render_spec,
    persist_skipped_lesson_ir,
    persist_storyboard_ir,
    reset_run_directory,
)
from animate_agent.animation_ir.compiler import compile_storyboard
from animate_agent.documents.builder import DocumentIRBuilder
from animate_agent.documents.service import ingest_source
from animate_agent.knowledge.service import generate_lesson
from animate_agent.llm import require_llm_config
from animate_agent.observability import bind_animation_run_id, reset_animation_run_id
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.rendering.models import RenderSpec
from animate_agent.sources.models import QuerySourceInput, SourceInput, UrlSourceInput
from animate_agent.sources.resolver import SourceResolver
from animate_agent.storyboard.service import generate_storyboard
from animate_agent.visualization.models import VisualizationIntent
from animate_agent.visualization.service import generate_intent_storyboard

logger = logging.getLogger("uvicorn.error.animate_agent.animation")


def _elapsed_ms(started_at: float) -> int:
    return round((time.perf_counter() - started_at) * 1000)


async def generate_animation(
    source: SourceInput,
    *,
    output_dir: Path = DEFAULT_RUNS_DIR,
    resolver: SourceResolver | None = None,
    document_builder: DocumentIRBuilder | None = None,
) -> RenderSpec:
    """Run a source through evidence/lesson planning to StoryboardIR and RenderSpec."""

    run_id = uuid.uuid4().hex[:12]
    run_directory = output_dir / run_id
    directory_token = bind_run_directory(run_directory)
    context_token = bind_animation_run_id(run_id)
    run_started_at = time.perf_counter()
    stage = "configuration"
    source_type = source.type
    logger.info(
        "animation run=%s stage=pipeline status=started source_type=%s",
        run_id,
        source_type,
    )

    try:
        # Fail before acquisition when the generation model is unavailable.
        # Query inputs separately validate their configured Web Search provider.
        stage_started_at = time.perf_counter()
        logger.info("animation run=%s stage=%s status=started", run_id, stage)
        llm_config = require_llm_config()
        logger.info(
            "animation run=%s stage=%s status=completed elapsed_ms=%d model=%s "
            "timeout_seconds=%g",
            run_id,
            stage,
            _elapsed_ms(stage_started_at),
            llm_config.model,
            llm_config.timeout_seconds,
        )

        stage = "source_ingestion"
        stage_started_at = time.perf_counter()
        logger.info("animation run=%s stage=%s status=started", run_id, stage)
        document = await ingest_source(
            source,
            output_dir=run_directory,
            resolver=resolver,
            builder=document_builder,
        )
        persist_document_ir(document)
        logger.info(
            "animation run=%s stage=%s status=completed elapsed_ms=%d document_id=%s "
            "sections=%d",
            run_id,
            stage,
            _elapsed_ms(stage_started_at),
            document.document_id,
            len(document.sections),
        )

        if isinstance(source, QuerySourceInput):
            # Query inputs already passed through the controlled Web Search
            # adapter. Keep the user's question as the learning intent and make
            # one successful generation call directly against the evidence.
            stage = "intent_storyboard_generation"
            stage_started_at = time.perf_counter()
            logger.info(
                "animation run=%s stage=%s status=started document_id=%s",
                run_id,
                stage,
                document.document_id,
            )
            storyboard = await generate_intent_storyboard(
                VisualizationIntent(question=source.query),
                document,
                output_dir=run_directory,
            )
            persist_skipped_lesson_ir()
            persist_storyboard_ir(storyboard)
            logger.info(
                "animation run=%s stage=%s status=completed elapsed_ms=%d "
                "storyboard_id=%s scenes=%d",
                run_id,
                stage,
                _elapsed_ms(stage_started_at),
                storyboard.storyboard_id,
                len(storyboard.scenes),
            )
        else:
            # URL/file/text inputs retain the reviewed course-generation path
            # until they receive an explicit user focus contract.
            stage = "lesson_generation"
            stage_started_at = time.perf_counter()
            logger.info(
                "animation run=%s stage=%s status=started document_id=%s",
                run_id,
                stage,
                document.document_id,
            )
            lesson = await generate_lesson(document, output_dir=run_directory)
            persist_lesson_ir(lesson)
            logger.info(
                "animation run=%s stage=%s status=completed elapsed_ms=%d "
                "lesson_id=%s scenes=%d",
                run_id,
                stage,
                _elapsed_ms(stage_started_at),
                lesson.lesson_id,
                len(lesson.scenes),
            )

            stage = "storyboard_generation"
            stage_started_at = time.perf_counter()
            logger.info(
                "animation run=%s stage=%s status=started lesson_id=%s",
                run_id,
                stage,
                lesson.lesson_id,
            )
            storyboard = await generate_storyboard(
                lesson, document, output_dir=run_directory
            )
            persist_storyboard_ir(storyboard)
            logger.info(
                "animation run=%s stage=%s status=completed elapsed_ms=%d storyboard_id=%s "
                "scenes=%d",
                run_id,
                stage,
                _elapsed_ms(stage_started_at),
                storyboard.storyboard_id,
                len(storyboard.scenes),
            )

        stage = "layout"
        stage_started_at = time.perf_counter()
        logger.info(
            "animation run=%s stage=%s status=started storyboard_id=%s",
            run_id,
            stage,
            storyboard.storyboard_id,
        )
        spec = layout_storyboard(storyboard)
        logger.info(
            "animation run=%s stage=%s status=completed elapsed_ms=%d render_scenes=%d",
            run_id,
            stage,
            _elapsed_ms(stage_started_at),
            len(spec.scenes),
        )

        stage = "animation_ir_compile"
        stage_started_at = time.perf_counter()
        logger.info(
            "animation run=%s stage=%s status=started storyboard_id=%s",
            run_id,
            stage,
            storyboard.storyboard_id,
        )
        spec.animation_ir = compile_storyboard(storyboard, render_spec=spec)
        persist_animation_ir(spec.animation_ir)
        logger.info(
            "animation run=%s stage=%s status=completed elapsed_ms=%d animation_scenes=%d",
            run_id,
            stage,
            _elapsed_ms(stage_started_at),
            len(spec.animation_ir.scenes),
        )

        stage = "persist"
        stage_started_at = time.perf_counter()
        logger.info("animation run=%s stage=%s status=started", run_id, stage)
        destination = persist_render_spec(spec)
        if destination is None:  # pragma: no cover - bound for the entire pipeline
            raise RuntimeError("animation run directory is not bound")
        logger.info(
            "animation run=%s stage=%s status=completed elapsed_ms=%d output=%s",
            run_id,
            stage,
            _elapsed_ms(stage_started_at),
            destination.as_posix(),
        )
        logger.info(
            "animation run=%s stage=pipeline status=completed elapsed_ms=%d storyboard_id=%s",
            run_id,
            _elapsed_ms(run_started_at),
            storyboard.storyboard_id,
        )
        return spec
    except Exception as exc:
        logger.exception(
            "animation run=%s stage=%s status=failed elapsed_ms=%d error_type=%s",
            run_id,
            stage,
            _elapsed_ms(run_started_at),
            type(exc).__name__,
        )
        raise
    finally:
        reset_animation_run_id(context_token)
        reset_run_directory(directory_token)


async def generate_animation_from_url(
    url: str,
    *,
    output_dir: Path = DEFAULT_RUNS_DIR,
) -> RenderSpec:
    """Backward-compatible URL wrapper around the generic orchestrator."""

    return await generate_animation(UrlSourceInput(url=url), output_dir=output_dir)
