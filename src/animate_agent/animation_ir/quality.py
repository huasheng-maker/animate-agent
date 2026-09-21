"""Observable quality checks for AnimationIR visual expression.

This is deliberately a structural evaluator, not a claim that JSON alone can
judge aesthetics. It catches the failure mode that motivated it: many semantic
steps compiling to the same one or two visual changes, or to no motion at all.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from animate_agent.animation_ir.models import AnimationGroup, AnimationIR, AnimationTrack


class AnimationQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=100)
    metrics: dict[str, float]
    warnings: list[str] = Field(default_factory=list)


def evaluate_animation_ir(ir: AnimationIR) -> AnimationQualityReport:
    """Score expression breadth, participation, rhythm, camera and beat activity."""

    beats = [beat for scene in ir.scenes for beat in scene.beats]
    nodes = [node for scene in ir.scenes for node in scene.nodes]
    tracks = [
        track
        for beat in beats
        for item in beat.timeline.items
        for track in _flatten(item)
    ]
    animated_nodes = {
        track.target.id for track in tracks if track.target.type == "node"
    }
    families = {_property_family(track.property) for track in tracks}
    active_beats = sum(
        any(True for item in beat.timeline.items for _ in _flatten(item)) for beat in beats
    )
    camera_beats = sum(
        any(
            track.target.type == "camera"
            for item in beat.timeline.items
            for track in _flatten(item)
        )
        for beat in beats
    )
    durations = {
        round(track.keyframes[-1].time + track.delay, 2)
        for track in tracks
        if track.keyframes
    }

    metrics = {
        "action_diversity": _ratio(len(families), 5),
        "object_participation": _ratio(len(animated_nodes), len(nodes)),
        "active_beats": _ratio(active_beats, len(beats)),
        "rhythm_layers": _ratio(len(durations), 3),
        "camera_usage": _ratio(camera_beats, len(beats)),
    }
    weights = {
        "action_diversity": 0.30,
        "object_participation": 0.25,
        "active_beats": 0.25,
        "rhythm_layers": 0.10,
        "camera_usage": 0.10,
    }
    score = round(sum(metrics[name] * weight for name, weight in weights.items()) * 100, 1)
    warnings: list[str] = []
    if active_beats < len(beats):
        warnings.append(f"{len(beats) - active_beats} 个节拍没有可执行的视觉变化")
    if len(families) < 3:
        warnings.append("动画动作族少于 3 类，表达容易退化为重复高亮")
    if nodes and len(animated_nodes) / len(nodes) < 0.6:
        warnings.append("参与动画的对象不足 60%，存在大量静态对象")
    if beats and camera_beats == 0:
        warnings.append("没有镜头调度，复杂场景缺少视觉聚焦")
    return AnimationQualityReport(score=score, metrics=metrics, warnings=warnings)


def _flatten(item: AnimationTrack | AnimationGroup) -> list[AnimationTrack]:
    if isinstance(item, AnimationTrack):
        return [item]
    return [track for child in item.children for track in _flatten(child)]


def _property_family(property_name: str) -> str:
    if property_name.startswith("camera."):
        return "camera"
    if property_name == "transform.pathProgress":
        return "path_motion"
    if property_name == "transform.scale":
        return "emphasis_motion"
    if property_name.startswith("visual."):
        return "reveal"
    if property_name.startswith("style."):
        return "style_emphasis"
    return property_name.split(".", 1)[0]


def _ratio(value: int, target: int) -> float:
    if target <= 0:
        return 0.0
    return round(min(value / target, 1.0), 3)
