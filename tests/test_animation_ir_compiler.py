from __future__ import annotations

import json

from animate_agent.animation_ir.compiler import (
    compile_render_spec,
    compile_storyboard,
    compile_storyboard_render_spec,
)
from animate_agent.animation_ir.quality import evaluate_animation_ir
from animate_agent.documents.models import DocumentBlock, DocumentIR, DocumentSource, Section
from animate_agent.paths import STORYBOARD_SAMPLES_DIR
from animate_agent.storyboard.models import StoryboardIR


def _storyboard() -> StoryboardIR:
    payload = json.loads(
        (STORYBOARD_SAMPLES_DIR / "controller.json").read_text(encoding="utf-8")
    )
    payload["learning_intent"] = "How does a controller reconcile desired and actual state?"
    scene = payload["scenes"][0]
    scene["learning_question"] = "How does observed state trigger the next action?"
    scene["visual_pattern"] = "causal_chain"
    scene["claims"] = [
        {
            "id": "claim-reconcile",
            "text": "The controller compares desired and observed state before acting.",
            "source_refs": ["controller-source"],
        }
    ]
    return StoryboardIR.model_validate(payload)


def test_storyboard_compiles_to_deterministic_renderer_neutral_animation_ir() -> None:
    storyboard = _storyboard()

    first = compile_storyboard(storyboard)
    second = compile_storyboard(storyboard)

    assert first == second
    assert first.metadata.sourceFormat == "storyboard-compiler-v1"
    assert first.metadata.learningIntent == storyboard.learning_intent
    assert first.scenes[0].metadata.visualPattern == "causal_chain"
    assert first.scenes[0].metadata.claims[0].source_refs == ["controller-source"]
    node = first.scenes[0].nodes[0]
    assert node.transform.position.x == node.legacy["x"]
    assert node.transform.position.y == node.legacy["y"]
    assert first.scenes[0].timeline.items == []
    assert len(first.scenes[0].beats) == len(storyboard.scenes[0].steps)
    first_beat = first.scenes[0].beats[0]
    assert first_beat.id == storyboard.scenes[0].steps[0].id
    assert first_beat.sourceRefs == ["controller-source"]
    assert first_beat.durationInFrames >= 180
    assert first_beat.timeline.items
    properties = {
        track.property
        for group in first_beat.timeline.items
        for track in group.children
    }
    assert "style.glowIntensity" in properties
    assert "transform.scale" in properties
    assert "camera.zoom" in properties

    encoded = first.model_dump(mode="json")
    assert encoded["irVersion"] == 1
    assert encoded["fps"] == 60
    assert encoded["scenes"][0]["nodes"][0]["parentId"] is None
    assert "pathProgress" in encoded["scenes"][0]["nodes"][0]["transform"]


def test_compiler_embeds_safe_per_beat_citations_from_document_ir() -> None:
    document = DocumentIR(
        document_id="sample-controller-document",
        title="Controller notes",
        source=DocumentSource(type="file", title="controller.md"),
        sections=[
            Section(
                id="controller-source",
                title="Reconciliation loop",
                level=1,
                blocks=[
                    DocumentBlock(
                        id="controller-block",
                        type="paragraph",
                        text="A controller observes desired and current state, then acts.",
                    )
                ],
            )
        ],
    )

    animation = compile_storyboard(_storyboard(), document=document)

    assert animation.citations[0].id == "controller-source"
    assert animation.citations[0].title == "controller.md"
    assert animation.citations[0].locator == "Reconciliation loop"
    assert "observes desired" in animation.citations[0].excerpt
    assert animation.citations[0].url is None


def test_compatibility_render_spec_embeds_the_same_canonical_ir() -> None:
    storyboard = _storyboard()

    spec = compile_storyboard_render_spec(storyboard)

    assert spec.animation_ir == compile_storyboard(storyboard, render_spec=spec)
    assert spec.animation_ir is not None
    assert spec.animation_ir == compile_render_spec(spec, source_format="storyboard-compiler-v1")
    persisted = json.loads(spec.model_dump_json())
    assert persisted["animation_ir"]["irVersion"] == 1
    assert persisted["animation_ir"]["metadata"]["sourceFormat"] == "storyboard-compiler-v1"


def test_expression_quality_reports_active_diverse_beats() -> None:
    animation = compile_storyboard(_storyboard())

    report = evaluate_animation_ir(animation)

    assert report.metrics["active_beats"] == 1
    assert report.metrics["action_diversity"] >= 0.6
    assert report.metrics["camera_usage"] == 1
    assert report.score >= 70
    assert not any("没有可执行" in warning for warning in report.warnings)
