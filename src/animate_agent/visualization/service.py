"""Intent-driven storyboard orchestration and persistence."""

from __future__ import annotations

import json
from pathlib import Path

from animate_agent.animation.artifacts import current_run_directory
from animate_agent.config import load_animation_settings, load_storyboard_settings
from animate_agent.documents.models import DocumentIR
from animate_agent.llm import LLMClient, require_llm_config
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.service import DEFAULT_GENERATED_DIR, build_limits
from animate_agent.visualization.agent import IntentStoryboardAgent
from animate_agent.visualization.models import VisualizationIntent


async def generate_intent_storyboard(
    intent: VisualizationIntent,
    document: DocumentIR,
    *,
    agent: IntentStoryboardAgent | None = None,
    output_dir: Path = DEFAULT_GENERATED_DIR,
) -> StoryboardIR:
    """Generate and persist StoryboardIR in one successful model round trip."""

    llm: LLMClient | None = None
    owns_client = False
    if agent is None:
        storyboard_settings = load_storyboard_settings()
        animation_settings = load_animation_settings()
        llm = LLMClient(require_llm_config())
        agent = IntentStoryboardAgent(
            llm,
            limits=build_limits(),
            allowed_renderers=animation_settings.allowed_renderers,
            max_retries=storyboard_settings.max_retries,
            semantic_repair_attempts=storyboard_settings.intent_semantic_repair_attempts,
            temperature=storyboard_settings.temperature,
            debug_dir=output_dir,
        )
        owns_client = True
    try:
        storyboard = await agent.generate(intent, document)
        if current_run_directory() is not None:
            return storyboard
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{storyboard.storyboard_id}.json"
        destination.write_text(
            json.dumps(storyboard.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return storyboard
    finally:
        if owns_client and llm is not None:
            await llm.aclose()
