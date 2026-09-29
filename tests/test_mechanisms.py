"""Offline generated-plan -> strict validation -> compiler -> player payload checks."""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

import animate_agent.animation.service as animation_service
from animate_agent.animation_ir.compiler import compile_storyboard
from animate_agent.documents.models import DocumentBlock, DocumentIR, DocumentSource, Section
from animate_agent.knowledge.models import LessonIR, LessonScene
from animate_agent.llm import LLMConfig
from animate_agent.mechanisms import MechanismPlan, mechanism_prompt
from animate_agent.paths import STORYBOARD_SAMPLES_DIR
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.sources.models import (
    FileSourceInput,
    QuerySourceInput,
    TextSourceInput,
    UrlSourceInput,
)
from animate_agent.storyboard.agent import StoryboardAgent
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.prompts import STORYBOARD_SYSTEM_PROMPT
from animate_agent.storyboard.validation import StoryboardLimits, validate_storyboard
from animate_agent.visualization.agent import IntentStoryboardAgent
from animate_agent.visualization.models import VisualizationIntent

CASES = [
    ("language_model",
     ["tokens", "embedding", "attention", "predict", "append", "predict", "append"]),
    ("neural_network", ["inputs", "weighted_sum", "activation", "loss", "update"]),
    ("linear_transform", ["basis", "transform", "vector", "determinant"]),
    ("derivative", ["curve", "secant", "limit", "tangent"]),
    ("packet_network", ["send", "travel", "timeout", "retransmit", "deliver"]),
]

QUESTIONS = {
    "language_model": "How does LLM work?",
    "neural_network": "神经网络的工作原理",
    "linear_transform": "线性变换如何改变平面？",
    "derivative": "导数与割线、切线有什么关系？",
    "packet_network": "停止等待协议如何处理丢包？",
}


def fixture_document() -> DocumentIR:
    return DocumentIR(document_id="mechanism-fixture", title="机制教学资料",
        source=DocumentSource(id="fixture", type="text", title="Reviewed local example"),
        sections=[Section(id="section", title="机制", level=1, blocks=[DocumentBlock(
            id="mechanism-evidence", type="paragraph", source_id="fixture", source_ref="local",
            text="嵌入按 ID 查表。因果注意力不访问未来。神经元计算加权和与激活。"
                 "线性变换映射基向量；导数是割线斜率的极限。丢包后超时重传等待确认。",
        )])])


def fixture_payload(kind: str, phases: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        (STORYBOARD_SAMPLES_DIR / "controller.json").read_text(encoding="utf-8")
    )
    payload.update(title=f"机制演示 · {kind}", subject=kind, learning_intent=kind)
    scene = payload["scenes"][0]
    payload["scenes"] = [scene]
    scene.update(id="mechanism-scene", lesson_scene_ids=[], controls=[],
                 learning_question=f"如何理解 {kind} 的计算过程？", visual_pattern="system_process")
    scene["teaching_goal"] = "观察参数如何影响计算过程和最终结果"
    scene["claims"] = [{"id": "mechanism-claim",
                        "text": fixture_document().sections[0].blocks[0].text,
                        "source_refs": ["mechanism-evidence"]}]
    for obj in scene["objects"]:
        obj["source_refs"] = ["mechanism-evidence"]
    template = scene["steps"][0]
    scene["steps"] = []
    for i, phase in enumerate(phases):
        step = copy.deepcopy(template)
        step.update(id=f"phase-{i}", title=phase,
                    description=f"观察 {phase} 阶段的数据变化，比较输入与计算结果。",
                    source_refs=["mechanism-evidence"])
        # All semantic objects remain cited and accounted for in this fixture.
        step["highlights"] = [obj["id"] for obj in scene["objects"]]
        scene["steps"].append(step)
    scene["mechanism"] = {"kind": kind, "phases": phases, "source_refs": ["mechanism-evidence"]}
    return payload


class LocalLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        self.calls += 1
        assert "可组合解释动画工具" in messages[0]["content"]
        return json.dumps(self.payload, ensure_ascii=False)


@pytest.mark.parametrize(("kind", "phases"), CASES)
def test_generated_mechanism_reaches_compiled_player(kind: str, phases: list[str]) -> None:
    llm = LocalLLM(fixture_payload(kind, phases))
    agent = IntentStoryboardAgent(llm, limits=StoryboardLimits(), max_retries=1)  # type: ignore[arg-type]
    storyboard = asyncio.run(agent.generate(VisualizationIntent(question=kind), fixture_document()))
    spec = layout_storyboard(storyboard)
    ir = compile_storyboard(storyboard, document=fixture_document(), render_spec=spec)
    assert llm.calls == 1
    assert spec.scenes[0].mechanism is not None
    assert ir.scenes[0].mechanism == spec.scenes[0].mechanism
    assert spec.scenes[0].controls[0].target_property.startswith("mechanism-scene-mechanism.")
    assert ir.scenes[0].interactions
    assert all(beat.sourceRefs for beat in ir.scenes[0].beats)
    assert "composition" in STORYBOARD_SYSTEM_PROMPT and "matmul" in mechanism_prompt()


def test_schema_rejects_invalid_models_dimensions_phases_and_controls() -> None:
    adapter: TypeAdapter[MechanismPlan] = TypeAdapter(MechanismPlan)
    for patch in [{"kind": "execute_js"}, {"token_ids": [99]}, {"embeddings": [[1, 2]]},
                  {"temperature": float("nan")}, {"code": "alert(1)"}]:
        with pytest.raises(ValidationError):
            adapter.validate_python({"kind": "language_model", "phases": ["tokens"],
                                     "source_refs": ["ref"], **patch})
    payload = fixture_payload(*CASES[0])
    payload["scenes"][0]["mechanism"]["phases"] = ["tokens"]
    with pytest.raises(ValidationError, match="one-to-one"):
        StoryboardIR.model_validate(payload)


def test_mechanism_cannot_invent_evidence() -> None:
    payload = fixture_payload(*CASES[0])
    payload["scenes"][0]["mechanism"]["source_refs"] = ["invented"]
    issues = validate_storyboard(StoryboardIR.model_validate(payload), document=fixture_document(),
                                limits=StoryboardLimits())
    assert any(issue.code == "mechanism_evidence" for issue in issues)


@pytest.mark.parametrize(("kind", "phases"), CASES)
@pytest.mark.parametrize("source_type", ["query", "url", "file", "text"])
def test_normal_pipeline_persists_mechanisms(
    kind: str, phases: list[str], source_type: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    payload = fixture_payload(kind, phases)
    payload["learning_intent"] = QUESTIONS[kind]
    document = fixture_document()
    points = ["观察输入", "比较计算结果"]
    lesson = LessonIR(lesson_id="mechanism-lesson", document_id=document.document_id,
        title=QUESTIONS[kind], subject=kind, summary="计算机制", learning_objectives=points,
        scenes=[LessonScene(id="lesson-scene", title=QUESTIONS[kind], objective="观察计算",
                            narration="输入改变会影响计算过程，沿着每一步观察数据变化。" * 4,
                            key_points=points, source_refs=["mechanism-evidence"])])
    if source_type != "query":
        payload["scenes"][0]["lesson_scene_ids"] = ["lesson-scene"]
        payload["scenes"][0]["steps"][0]["key_points"] = points
    llm = LocalLLM(payload)

    async def ingest(*args: Any, **kwargs: Any) -> DocumentIR:
        return document

    async def knowledge(*args: Any, **kwargs: Any) -> LessonIR:
        assert source_type != "query"
        return lesson

    async def intent_plan(
        intent: VisualizationIntent, doc: DocumentIR, **kwargs: Any,
    ) -> StoryboardIR:
        agent = IntentStoryboardAgent(llm, limits=StoryboardLimits(), max_retries=1)  # type: ignore[arg-type]
        return await agent.generate(intent, doc)

    async def lesson_plan(course: LessonIR, doc: DocumentIR, **kwargs: Any) -> StoryboardIR:
        agent = StoryboardAgent(llm, limits=StoryboardLimits(), max_retries=1)  # type: ignore[arg-type]
        return await agent.generate(course, doc)

    monkeypatch.setattr(animation_service, "ingest_source", ingest)
    monkeypatch.setattr(animation_service, "generate_lesson", knowledge)
    monkeypatch.setattr(animation_service, "generate_intent_storyboard", intent_plan)
    monkeypatch.setattr(animation_service, "generate_storyboard", lesson_plan)
    monkeypatch.setattr(animation_service, "require_llm_config", lambda: LLMConfig(
        base_url="https://example.com", api_key="local-test", model="local-test"))
    sources = {
        "query": QuerySourceInput(query=QUESTIONS[kind]),
        "url": UrlSourceInput(url="https://example.com/lesson"),
        "text": TextSourceInput(text="local fixture"),
        "file": FileSourceInput(path=str(tmp_path / "lesson.txt")),
    }
    spec = asyncio.run(animation_service.generate_animation(
        sources[source_type], output_dir=tmp_path, job_id="mechanism-run"))
    assert llm.calls == 1
    assert spec.animation_ir is not None and spec.scenes[0].mechanism is not None
    assert spec.scenes[0].mechanism.kind == kind
    for name in ["04-storyboard-ir.json", "05-animation-ir.json", "06-render-spec.json"]:
        saved = json.loads((tmp_path / "mechanism-run" / name).read_text(encoding="utf-8"))
        assert saved["scenes"][0]["mechanism"]["kind"] == kind


if __name__ == "__main__":
    # Local browser fixtures; generation never invokes a paid or external model.
    import sys

    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    for kind, phases in CASES:
        story = StoryboardIR.model_validate(fixture_payload(kind, phases))
        spec = layout_storyboard(story)
        spec.animation_ir = compile_storyboard(story, document=fixture_document(), render_spec=spec)
        (destination / f"{kind}.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
