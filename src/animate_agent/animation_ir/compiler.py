"""Deterministically compile StoryboardIR into renderer-neutral AnimationIR."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from animate_agent.animation_ir.models import (
    AnimatableProperty,
    AnimatableValue,
    AnimationBeat,
    AnimationCamera,
    AnimationCitation,
    AnimationClaim,
    AnimationGroup,
    AnimationIR,
    AnimationKeyframe,
    AnimationMetadata,
    AnimationNode,
    AnimationScene,
    AnimationStage,
    AnimationTarget,
    AnimationTimeline,
    AnimationTrack,
    Easing,
    NodeSemanticState,
    NodeStyle,
    NodeTransform,
    SceneMetadata,
    TimelineItem,
    Vector2,
)
from animate_agent.config import AnimationSettings, load_animation_settings
from animate_agent.documents.models import DocumentIR, DocumentSource
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.rendering.models import RenderScene, RenderSpec, RenderStage, RenderStep
from animate_agent.storyboard.models import StoryboardIR

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class BeatTimingPolicy:
    cjk_chars_per_second: float = 8.0
    latin_words_per_minute: float = 180.0
    min_beat_seconds: float = 3.0
    max_reading_seconds: float = 12.0
    beat_end_hold_seconds: float = 0.6

    @classmethod
    def from_settings(cls, settings: AnimationSettings) -> BeatTimingPolicy:
        return cls(
            cjk_chars_per_second=settings.cjk_chars_per_second,
            latin_words_per_minute=settings.latin_words_per_minute,
            min_beat_seconds=settings.min_beat_seconds,
            max_reading_seconds=settings.max_reading_seconds,
            beat_end_hold_seconds=settings.beat_end_hold_seconds,
        )


def compile_storyboard(
    storyboard: StoryboardIR,
    *,
    document: DocumentIR | None = None,
    stage: RenderStage | None = None,
    render_spec: RenderSpec | None = None,
    timing: BeatTimingPolicy | None = None,
) -> AnimationIR:
    """Compile a semantic storyboard; layout remains a deterministic sub-pass."""

    spec = render_spec or layout_storyboard(storyboard, stage=stage)
    if spec.storyboard_id != storyboard.storyboard_id:
        raise ValueError("render_spec does not belong to the storyboard being compiled")
    return compile_render_spec(
        spec,
        document=document,
        source_format="storyboard-compiler-v1",
        timing=timing,
    )


def compile_storyboard_render_spec(
    storyboard: StoryboardIR,
    *,
    document: DocumentIR | None = None,
    stage: RenderStage | None = None,
    timing: BeatTimingPolicy | None = None,
) -> RenderSpec:
    """Return the compatibility RenderSpec carrying canonical AnimationIR."""

    spec = layout_storyboard(storyboard, stage=stage)
    spec.animation_ir = compile_storyboard(
        storyboard,
        document=document,
        render_spec=spec,
        timing=timing,
    )
    return spec


def compile_render_spec(
    spec: RenderSpec,
    *,
    document: DocumentIR | None = None,
    source_format: Literal["storyboard-compiler-v1", "render-spec-v1"] = "render-spec-v1",
    timing: BeatTimingPolicy | None = None,
) -> AnimationIR:
    """Adapt a validated RenderSpec without introducing renderer decisions."""

    if source_format not in {"storyboard-compiler-v1", "render-spec-v1"}:
        raise ValueError(f"unsupported AnimationIR source format: {source_format}")
    resolved_timing = timing or BeatTimingPolicy.from_settings(load_animation_settings())
    fps = 60.0
    return AnimationIR(
        fps=fps,
        stage=AnimationStage(width=spec.stage.width, height=spec.stage.height),
        metadata=AnimationMetadata(
            storyboardId=spec.storyboard_id,
            lessonId=spec.lesson_id,
            documentId=spec.document_id,
            learningIntent=spec.learning_intent,
            title=spec.title,
            subject=spec.subject,
            eyebrow=spec.eyebrow,
            sourceFormat=source_format,
        ),
        citations=_build_citations(spec, document),
        scenes=[
            _compile_scene(scene, spec.stage, fps=fps, timing=resolved_timing)
            for scene in spec.scenes
        ],
    )


def _compile_scene(
    scene: RenderScene,
    stage: RenderStage,
    *,
    fps: float,
    timing: BeatTimingPolicy,
) -> AnimationScene:
    scene_data = scene.model_dump(mode="json")
    elements = [element.model_dump(mode="json") for element in scene.elements]
    element_by_id = {str(element["id"]): element for element in elements}
    nodes = [_compile_node(element, element_by_id) for element in elements]
    return AnimationScene(
        id=scene.id,
        mechanism=scene.mechanism,
        metadata=SceneMetadata(
            title=scene.title,
            teachingGoal=scene.teaching_goal,
            learningQuestion=scene.learning_question,
            visualPattern=scene.visual_pattern,
            claims=[AnimationClaim.model_validate(claim.model_dump()) for claim in scene.claims],
            preset=scene.preset,
        ),
        nodes=nodes,
        camera=AnimationCamera(),
        beats=[
            _compile_beat(step, nodes, stage, fps=fps, timing=timing)
            for step in scene.steps
        ],
        timeline=AnimationTimeline(),
        interactions=[control.model_dump(mode="json") for control in scene.controls],
        legacy=scene_data,
    )


def _compile_node(
    element: dict[str, object],
    element_by_id: dict[str, dict[str, object]],
) -> AnimationNode:
    element_id = _required_string(element, "id")
    kind = _required_string(element, "kind")
    x = _required_number(element, "x")
    y = _required_number(element, "y")
    heading = element.get("heading", 0)
    if not isinstance(heading, int | float) or isinstance(heading, bool):
        raise ValueError(f"element {element_id} heading must be numeric")

    path = element.get("path", element.get("points", []))
    if kind == "traveler" and not path:
        path_id = element.get("path_id")
        referenced = element_by_id.get(path_id) if isinstance(path_id, str) else None
        if referenced is not None:
            path = referenced.get("path", referenced.get("points", []))
    text = element.get("text", "")
    if not isinstance(text, str):
        text = ""
    visual = dict(element)
    visual.update(
        {
            "path": path,
            "originalText": text,
            "visibleText": text,
            "drawProgress": 1.0,
            "trimStart": 0.0,
            "trimEnd": 1.0,
            "revealProgress": 1.0,
            "cursorVisible": False,
        }
    )
    return AnimationNode(
        id=element_id,
        kind=kind,
        transform=NodeTransform(
            position=Vector2(x=x, y=y),
            rotation=float(heading),
        ),
        style=NodeStyle(tone=str(element.get("tone", "normal"))),
        visual=visual,
        semantic=NodeSemanticState(),
        legacy=dict(element),
    )


def _compile_beat(
    step: RenderStep,
    nodes: list[AnimationNode],
    stage: RenderStage,
    *,
    fps: float,
    timing: BeatTimingPolicy,
) -> AnimationBeat:
    """Direct one semantic step with a small, deterministic visual grammar.

    Storyboard authors still say *what* changes. This pass decides *how* the
    change is staged, so richer motion does not require model-authored timing,
    easing, colours, coordinates, or executable renderer code.
    """

    node_by_id = {node.id: node for node in nodes}
    target_ids = list(dict.fromkeys([*step.highlights, *step.states]))
    tracks: list[AnimationTrack] = []
    for target_index, target_id in enumerate(target_ids):
        node = node_by_id.get(target_id)
        if node is None:
            continue
        node_path = node.visual.get("path")
        target = AnimationTarget(type="node", id=target_id)
        stagger = target_index * 0.055
        tracks.append(
            _track(
                target,
                "style.glowIntensity",
                [(0.0, 0.0), (0.22, 1.0, "expoOut"), (0.86, 0.32, "easeInOut"), (1.28, 0.0)],
                delay=stagger,
            )
        )
        tracks.append(
            _track(
                target,
                "semantic.phase",
                [(0.0, "entering"), (0.12, "active"), (1.28, "settled")],
                delay=stagger,
            )
        )

        if node.kind in {"link", "trace", "vector"}:
            tracks.append(
                _track(
                    target,
                    "visual.drawProgress",
                    [(0.0, 0.0), (0.9, 1.0, "expoOut")],
                    delay=stagger,
                )
            )
        elif node.kind == "traveler" and isinstance(node_path, list) and len(node_path) >= 2:
            tracks.append(
                _track(
                    target,
                    "transform.pathProgress",
                    [(0.0, 0.0), (1.18, 1.0, "easeInOut")],
                    delay=stagger,
                )
            )
        elif node.kind == "readout":
            tracks.append(
                _track(
                    target,
                    "visual.revealProgress",
                    [(0.0, 0.0), (0.82, 1.0, "expoOut")],
                    delay=stagger,
                )
            )
        else:
            tracks.append(
                _track(
                    target,
                    "transform.scale",
                    [
                        (0.0, Vector2(x=1.0, y=1.0)),
                        (0.34, Vector2(x=1.09, y=1.09), "backOut"),
                        (0.92, Vector2(x=1.0, y=1.0), "easeInOut"),
                    ],
                    delay=stagger,
                )
            )

    if target_ids:
        focus_nodes = [node_by_id[target_id] for target_id in target_ids if target_id in node_by_id]
        if focus_nodes:
            focus_x = sum(node.transform.position.x for node in focus_nodes) / len(focus_nodes)
            focus_y = sum(node.transform.position.y for node in focus_nodes) / len(focus_nodes)
            camera = AnimationTarget(type="camera", id="main")
            tracks.extend(
                [
                    _track(
                        camera,
                        "camera.position",
                        [
                            (0.0, Vector2(x=0.0, y=0.0)),
                            (
                                0.42,
                                Vector2(
                                    x=(focus_x - stage.width / 2) * 0.16,
                                    y=(focus_y - stage.height / 2) * 0.16,
                                ),
                                "expoOut",
                            ),
                            (1.28, Vector2(x=0.0, y=0.0), "easeInOut"),
                        ],
                        delay=0.03,
                    ),
                    _track(
                        camera,
                        "camera.zoom",
                        [(0.0, 1.0), (0.42, 1.055, "expoOut"), (1.28, 1.0, "easeInOut")],
                        delay=0.03,
                    ),
                ]
            )

    timeline = AnimationTimeline(items=[])
    if tracks:
        children: list[TimelineItem] = list(tracks)
        timeline.items.append(AnimationGroup(type="parallel", children=children))
    duration_seconds = max(
        _timeline_duration(timeline),
        _reading_duration(step.narration, timing),
    )
    return AnimationBeat(
        id=step.id,
        title=step.title,
        narration=step.narration,
        sourceRefs=list(step.source_refs),
        durationInFrames=max(1, math.ceil(duration_seconds * fps)),
        timeline=timeline,
    )


def _reading_duration(text: str, timing: BeatTimingPolicy) -> float:
    cjk_seconds = len(_CJK.findall(text)) / timing.cjk_chars_per_second
    latin_seconds = len(_LATIN_WORD.findall(text)) / (timing.latin_words_per_minute / 60)
    estimated = min(
        cjk_seconds + latin_seconds + timing.beat_end_hold_seconds,
        timing.max_reading_seconds,
    )
    return max(timing.min_beat_seconds, estimated)


def _timeline_duration(timeline: AnimationTimeline) -> float:
    item_duration = max((_timeline_item_duration(item) for item in timeline.items), default=0.0)
    effect_duration = max(
        (effect.delay + effect.duration for effect in timeline.effects),
        default=0.0,
    )
    return max(item_duration, effect_duration)


def _timeline_item_duration(item: TimelineItem) -> float:
    if isinstance(item, AnimationTrack):
        duration = item.duration if item.duration is not None else item.keyframes[-1].time
        return item.delay + duration
    child_durations = [_timeline_item_duration(child) for child in item.children]
    content = sum(child_durations) if item.type == "sequence" else max(child_durations, default=0.0)
    return item.delay + content


def _build_citations(spec: RenderSpec, document: DocumentIR | None) -> list[AnimationCitation]:
    if document is None:
        return []
    wanted = {
        ref
        for scene in spec.scenes
        for step in scene.steps
        for ref in step.source_refs
    }
    sources = {source.id: source for source in document.sources if source.id}
    primary = document.source
    citations: list[AnimationCitation] = []
    resolved: set[str] = set()

    for section in document.sections:
        if section.id in wanted:
            source = (
                _source_for_block(section.blocks[0].source_id, sources, primary)
                if section.blocks
                else primary
            )
            citations.append(
                AnimationCitation(
                    id=section.id,
                    title=source.title or document.title,
                    locator=section.title,
                    excerpt=_excerpt(" ".join(block.text for block in section.blocks)),
                    url=source.url,
                )
            )
            resolved.add(section.id)
        for block in section.blocks:
            if block.id not in wanted:
                continue
            source = _source_for_block(block.source_id, sources, primary)
            citations.append(
                AnimationCitation(
                    id=block.id,
                    title=source.title or document.title,
                    locator=section.title,
                    excerpt=_excerpt(block.text),
                    url=source.url,
                )
            )
            resolved.add(block.id)

    for ref in sorted(wanted - resolved):
        citations.append(
            AnimationCitation(
                id=ref,
                title=primary.title or document.title,
                locator=ref,
                url=primary.url,
            )
        )
    return citations


def _source_for_block(
    source_id: str | None,
    sources: dict[str, DocumentSource],
    primary: DocumentSource,
) -> DocumentSource:
    return sources.get(source_id, primary) if source_id else primary


def _excerpt(text: str, limit: int = 240) -> str:
    normalized = _SPACE.sub(" ", text).strip()
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 1].rstrip()}…"


def _track(
    target: AnimationTarget,
    property_name: AnimatableProperty,
    frames: list[tuple[float, AnimatableValue] | tuple[float, AnimatableValue, Easing]],
    *,
    delay: float = 0.0,
) -> AnimationTrack:
    return AnimationTrack(
        target=target,
        property=property_name,
        delay=delay,
        keyframes=[
            AnimationKeyframe(
                time=frame[0],
                value=frame[1],
                easing=(frame[2] if len(frame) == 3 else ("easeInOut" if index else "linear")),
                interpolation="discrete" if isinstance(frame[1], str | bool) else None,
            )
            for index, frame in enumerate(frames)
        ],
    )


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"compiled element requires a non-empty {key}")
    return value


def _required_number(data: dict[str, object], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"compiled element requires numeric {key}")
    return float(value)
