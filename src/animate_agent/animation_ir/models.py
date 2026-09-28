"""Strict, renderer-neutral models consumed by the browser Animation Runtime.

The JSON field names intentionally match the JavaScript runtime contract. This
keeps persisted specs, FastAPI responses, and direct model dumps identical.
Animation data may contain declarative values only; executable code and
renderer APIs have no representation in this schema.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from animate_agent.mechanisms import MechanismPlan
from animate_agent.storyboard.models import VisualPattern

ANIMATION_IR_VERSION: Literal[1] = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)


class Vector2(_Model):
    x: float
    y: float


class AnimationStage(_Model):
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class AnimationClaim(_Model):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class AnimationCitation(_Model):
    id: str = Field(min_length=1)
    title: str = ""
    locator: str = ""
    excerpt: str = ""
    url: str | None = None


class AnimationMetadata(_Model):
    storyboardId: str = ""
    lessonId: str = ""
    documentId: str = ""
    learningIntent: str = ""
    title: str = ""
    subject: str = ""
    eyebrow: str = ""
    sourceFormat: Literal["storyboard-compiler-v1", "render-spec-v1"]


class SceneMetadata(_Model):
    title: str = ""
    teachingGoal: str = ""
    learningQuestion: str = ""
    visualPattern: VisualPattern | None = None
    claims: list[AnimationClaim] = Field(default_factory=list)
    preset: str = ""


class NodeTransform(_Model):
    position: Vector2
    rotation: float = 0
    scale: Vector2 = Field(default_factory=lambda: Vector2(x=1, y=1))
    opacity: float = Field(default=1, ge=0, le=1)
    pathProgress: float = Field(default=0, ge=0, le=1)


class NodeStyle(_Model):
    tone: str = "normal"
    highlight: bool = False
    glowIntensity: float = Field(default=0, ge=0, le=1)


class NodeSemanticState(_Model):
    progress: float = Field(default=0, ge=0, le=1)
    intensity: float = Field(default=0, ge=0, le=1)
    phase: str = "idle"


class AnimationNode(_Model):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    # Reserved until matrix inheritance is implemented by the runtime.
    parentId: None = None
    transform: NodeTransform
    style: NodeStyle = Field(default_factory=NodeStyle)
    # Geometry/content is data produced by deterministic layout. Timeline writes
    # remain restricted to the central property registry in the runtime.
    visual: dict[str, object] = Field(default_factory=dict)
    semantic: NodeSemanticState = Field(default_factory=NodeSemanticState)
    legacy: dict[str, object] = Field(default_factory=dict)


class AnimationCamera(_Model):
    id: Literal["main"] = "main"
    position: Vector2 = Field(default_factory=lambda: Vector2(x=0, y=0))
    zoom: float = Field(default=1, gt=0)
    rotation: float = 0


AnimatableProperty = Literal[
    "transform.position",
    "transform.rotation",
    "transform.scale",
    "transform.opacity",
    "transform.pathProgress",
    "style.fill",
    "style.stroke",
    "style.strokeWidth",
    "style.shadowBlur",
    "style.glowIntensity",
    "style.highlight",
    "visual.drawProgress",
    "visual.trimStart",
    "visual.trimEnd",
    "visual.pathOffset",
    "visual.revealProgress",
    "visual.cursorVisible",
    "camera.position",
    "camera.zoom",
    "camera.rotation",
    "semantic.progress",
    "semantic.intensity",
    "semantic.phase",
]
Easing = Literal[
    "linear",
    "easeIn",
    "easeOut",
    "easeInOut",
    "expoOut",
    "backOut",
    "elasticOut",
]
Interpolation = Literal["number", "normalized", "vector", "color", "discrete"]


class ColorRGBA(_Model):
    r: float = Field(ge=0, le=255)
    g: float = Field(ge=0, le=255)
    b: float = Field(ge=0, le=255)
    a: float = Field(default=1, ge=0, le=1)


AnimatableValue: TypeAlias = float | Vector2 | ColorRGBA | bool | str


class AnimationTarget(_Model):
    type: Literal["node", "camera"]
    id: str = Field(min_length=1)


class AnimationKeyframe(_Model):
    time: float = Field(ge=0)
    value: AnimatableValue
    easing: Easing = "linear"
    interpolation: Interpolation | None = None


class AnimationTrack(_Model):
    type: Literal["track"] = "track"
    target: AnimationTarget
    property: AnimatableProperty
    keyframes: list[AnimationKeyframe] = Field(min_length=2)
    delay: float = Field(default=0, ge=0)
    duration: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _increasing_keyframes(self) -> AnimationTrack:
        times = [frame.time for frame in self.keyframes]
        if any(right <= left for left, right in zip(times, times[1:], strict=False)):
            raise ValueError("animation keyframe times must increase")
        return self


class AnimationGroup(_Model):
    type: Literal["sequence", "parallel"]
    delay: float = Field(default=0, ge=0)
    children: list[TimelineItem] = Field(default_factory=list)


TimelineItem: TypeAlias = Annotated[
    AnimationTrack | AnimationGroup,
    Field(discriminator="type"),
]


class AnimationEffect(_Model):
    effect: Literal[
        "fadeIn",
        "moveTo",
        "drawPath",
        "highlight",
        "typeWriter",
        "cameraPan",
        "pulse",
        "followPath",
        "cameraZoom",
    ]
    target: str | None = None
    camera: str | None = None
    duration: float = Field(default=0.3, gt=0)
    delay: float = Field(default=0, ge=0)
    easing: Easing = "linear"
    interpolation: Interpolation | None = None
    from_: AnimatableValue | None = Field(default=None, alias="from")
    to: AnimatableValue | None = None


class AnimationTimeline(_Model):
    # Target-kind and exact value compatibility are validated by the central
    # property registry when the runtime loads the compiled scene.
    items: list[TimelineItem] = Field(default_factory=list)
    effects: list[AnimationEffect] = Field(default_factory=list)


class AnimationBeat(_Model):
    """A replayable visual beat selected by the player's semantic step control."""

    id: str = Field(min_length=1)
    title: str = ""
    narration: str = ""
    sourceRefs: list[str] = Field(default_factory=list)
    durationInFrames: int = Field(default=1, ge=1)
    timeline: AnimationTimeline = Field(default_factory=AnimationTimeline)


class AnimationScene(_Model):
    id: str = Field(min_length=1)
    mechanism: MechanismPlan | None = None
    metadata: SceneMetadata
    nodes: list[AnimationNode] = Field(min_length=1)
    camera: AnimationCamera = Field(default_factory=AnimationCamera)
    beats: list[AnimationBeat] = Field(default_factory=list)
    timeline: AnimationTimeline = Field(default_factory=AnimationTimeline)
    interactions: list[dict[str, object]] = Field(default_factory=list)
    legacy: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_node_ids(self) -> AnimationScene:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError(f"scene {self.id} contains duplicate node ids")
        return self


class AnimationIR(_Model):
    irVersion: Literal[1] = ANIMATION_IR_VERSION
    fps: float = Field(default=60, gt=0, le=240)
    stage: AnimationStage
    metadata: AnimationMetadata
    citations: list[AnimationCitation] = Field(default_factory=list)
    scenes: list[AnimationScene] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_scene_ids(self) -> AnimationIR:
        ids = [scene.id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("AnimationIR contains duplicate scene ids")
        return self


AnimationGroup.model_rebuild()
