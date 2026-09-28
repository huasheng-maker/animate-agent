from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pytest import MonkeyPatch, raises

import animate_agent.animation.service as animation_service
from animate_agent.documents.models import DocumentBlock, DocumentIR, DocumentSource, Section
from animate_agent.llm import LLMConfig
from animate_agent.paths import STORYBOARD_SAMPLES_DIR
from animate_agent.sources.models import QuerySourceInput
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.service import build_limits
from animate_agent.storyboard.validation import StoryboardLimits
from animate_agent.visualization.agent import (
    IntentStoryboardAgent,
    StoryboardGenerationError,
    _merge_scene_repairs,
)
from animate_agent.visualization.models import EvidencePack, VisualizationIntent
from animate_agent.visualization.prompts import build_intent_storyboard_prompt
from animate_agent.visualization.service import generate_intent_storyboard


def _document() -> DocumentIR:
    return DocumentIR(
        document_id="tcp-evidence",
        title="TCP connection lifecycle",
        source=DocumentSource(
            id="search-result",
            type="web_search",
            title="TCP evidence",
            url="https://example.com/tcp",
        ),
        sections=[
            Section(
                id="section-handshake",
                title="Connection establishment",
                level=1,
                blocks=[
                    DocumentBlock(
                        id="tcp-handshake-evidence",
                        type="paragraph",
                        text=(
                            "The client sends SYN, the server replies with SYN and ACK, "
                            "and the client acknowledges the server response."
                        ),
                        source_id="search-result",
                        source_ref="citation-1",
                    )
                ],
            ),
            Section(
                id="section-unrelated",
                title="Unrelated appendix",
                level=1,
                blocks=[
                    DocumentBlock(
                        id="unrelated-evidence",
                        type="paragraph",
                        text="This appendix is not needed to answer the learning question.",
                    )
                ],
            ),
        ],
    )


def _intent() -> VisualizationIntent:
    return VisualizationIntent(
        question="TCP 三次握手发生了什么？",
        audience="网络初学者",
        focus=["消息流", "端点状态"],
    )


def _storyboard_payload() -> dict[str, object]:
    payload = json.loads((STORYBOARD_SAMPLES_DIR / "controller.json").read_text(encoding="utf-8"))
    payload["title"] = "TCP 三次握手"
    payload["subject"] = "Computer Networking"
    payload["eyebrow"] = "SYN · SYN-ACK · ACK"
    payload["scenes"] = payload["scenes"][:1]
    scene = payload["scenes"][0]
    scene["lesson_scene_ids"] = []
    scene["learning_question"] = "客户端和服务器如何确认连接可以建立？"
    scene["visual_pattern"] = "state_transition"
    scene["claims"] = [
        {
            "id": "claim-handshake",
            "text": "客户端发送 SYN，服务器返回 SYN 和 ACK，客户端再发送 ACK。",
            "source_refs": ["tcp-handshake-evidence"],
        }
    ]
    for obj in scene["objects"]:
        obj["source_refs"] = ["tcp-handshake-evidence"]
    for step in scene["steps"]:
        step["source_refs"] = ["tcp-handshake-evidence"]
    scene["controls"] = []
    phases = ["send", "travel", "ack", "deliver"]
    scene["mechanism"] = {
        "kind": "packet_network", "protocol": "tcp_handshake", "drop_first": False,
        "source_refs": ["tcp-handshake-evidence"],
        "phases": phases[:len(scene["steps"])],
    }
    return payload


class FakeLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[list[dict[str, str]]] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        assert temperature >= 0
        assert max_tokens > 0
        self.calls.append(messages)
        return json.dumps(self.payload, ensure_ascii=False)


class SequenceLLM:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads
        self.calls: list[list[dict[str, str]]] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        assert temperature >= 0
        assert max_tokens > 0
        self.calls.append(messages)
        return json.dumps(self.payloads[len(self.calls) - 1], ensure_ascii=False)


def test_evidence_prompt_is_intent_led_and_does_not_require_full_coverage() -> None:
    evidence = EvidencePack.from_document(_document())
    prompt = build_intent_storyboard_prompt(_intent(), evidence)

    assert "TCP 三次握手发生了什么" in prompt
    assert "tcp-handshake-evidence" in prompt
    assert "unrelated-evidence" in prompt
    assert "不要求覆盖全部 evidence" in prompt or "无关材料必须舍弃" in prompt
    assert '"role": "node"' in prompt
    assert '"props":' in prompt
    assert '"object_states":' in prompt
    assert '"source_refs": ["evidence-block-id"]' in prompt
    assert "2+2+2" in prompt
    assert "禁止每个场景各写 3~4 拍" in prompt
    assert len(evidence.items) == 2


def test_prompt_uses_runtime_step_limits() -> None:
    evidence = EvidencePack.from_document(_document())
    prompt = build_intent_storyboard_prompt(
        _intent(),
        evidence,
        limits=StoryboardLimits(min_steps=2, max_steps=5),
    )

    assert "必须为 2~5" in prompt


def test_intent_agent_happy_path_uses_one_model_call_and_keeps_evidence_links() -> None:
    llm = FakeLLM(_storyboard_payload())
    agent = IntentStoryboardAgent(llm, limits=build_limits(), max_retries=3)  # type: ignore[arg-type]

    storyboard = asyncio.run(agent.generate(_intent(), _document()))

    assert len(llm.calls) == 1
    assert storyboard.learning_intent == _intent().question
    assert storyboard.lesson_id == "intent-tcp-evidence"
    assert storyboard.scenes[0].claims[0].source_refs == ["tcp-handshake-evidence"]
    assert storyboard.scenes[0].lesson_scene_ids == []


def test_overfull_scene_is_repaired_without_regenerating_document() -> None:
    valid = _storyboard_payload()
    invalid = json.loads(json.dumps(valid))
    scene = invalid["scenes"][0]
    scene["objects"] = (scene["objects"] * 13)[:13]
    patch = {"repaired_scenes": [{"index": 0, "scene": valid["scenes"][0]}]}  # type: ignore[index]
    llm = SequenceLLM([invalid, patch])
    agent = IntentStoryboardAgent(llm, limits=build_limits(), max_retries=2)  # type: ignore[arg-type]
    result = asyncio.run(agent.generate(_intent(), _document()))
    assert len(result.scenes[0].objects) <= 12
    assert len(llm.calls) == 2
    assert "repaired_scenes" in llm.calls[1][1]["content"]
    assert "flow、relation" in llm.calls[1][1]["content"]


def test_repair_preserves_unrequested_scenes_and_checks_patch_scope() -> None:
    base = {"title": "keep", "scenes": [{"id": "a"}, {"id": "b", "objects": []}]}
    patch = {"title": "overwrite", "scenes": [{"id": "a", "changed": True}, {"id": "b"}]}
    result = _merge_scene_repairs(base, patch, [1])
    assert result["title"] == "keep"
    assert result["scenes"][0] == {"id": "a"}
    assert base["scenes"][1] == {"id": "b", "objects": []}
    with raises(ValueError, match="未请求"):
        _merge_scene_repairs(base, {"repaired_scenes": [{"index": 0, "scene": {"id": "a"}}]}, [1])


def test_exhausted_object_limit_has_safe_actionable_failure() -> None:
    payload = json.loads(json.dumps(_storyboard_payload()))
    scene = payload["scenes"][0]
    scene["objects"] = (scene["objects"] * 13)[:13]
    agent = IntentStoryboardAgent(FakeLLM(payload), limits=build_limits(), max_retries=1)  # type: ignore[arg-type]
    with raises(StoryboardGenerationError) as failure:
        asyncio.run(agent.generate(_intent(), _document()))
    assert "13 个" in failure.value.summary
    assert "上限 12 个" in failure.value.summary


def test_intent_agent_rejects_an_invented_claim_reference() -> None:
    payload = _storyboard_payload()
    payload["scenes"][0]["claims"][0]["source_refs"] = ["invented-source"]  # type: ignore[index]
    llm = FakeLLM(payload)
    agent = IntentStoryboardAgent(llm, limits=build_limits(), max_retries=1)  # type: ignore[arg-type]

    with raises(ValueError, match="claim_source_ref_unknown"):
        asyncio.run(agent.generate(_intent(), _document()))
    assert len(llm.calls) == 1


def test_intent_agent_reserves_a_semantic_repair_after_schema_recovery() -> None:
    schema_invalid = _storyboard_payload()
    schema_invalid["scenes"][0]["objects"][0]["type"] = "body"  # type: ignore[index]
    semantic_invalid = _storyboard_payload()
    semantic_invalid["scenes"][0]["claims"][0]["source_refs"] = [  # type: ignore[index]
        "invented-source"
    ]
    valid = _storyboard_payload()
    llm = SequenceLLM([schema_invalid, semantic_invalid, valid])
    agent = IntentStoryboardAgent(llm, limits=build_limits(), max_retries=2)  # type: ignore[arg-type]

    storyboard = asyncio.run(agent.generate(_intent(), _document()))

    assert storyboard.scenes[0].claims[0].source_refs == ["tcp-handshake-evidence"]
    assert len(llm.calls) == 3
    assert "schema 不符" in llm.calls[1][1]["content"]
    assert "claim_source_ref_unknown" in llm.calls[2][1]["content"]


def test_intent_storyboard_service_persists_the_validated_storyboard(tmp_path: Path) -> None:
    llm = FakeLLM(_storyboard_payload())
    agent = IntentStoryboardAgent(llm, limits=build_limits(), max_retries=1)  # type: ignore[arg-type]

    storyboard = asyncio.run(
        generate_intent_storyboard(_intent(), _document(), agent=agent, output_dir=tmp_path)
    )

    saved = tmp_path / f"{storyboard.storyboard_id}.json"
    assert saved.is_file()
    assert StoryboardIR.model_validate_json(saved.read_text(encoding="utf-8")) == storyboard


def test_query_animation_uses_intent_storyboard_without_generating_lesson(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    storyboard = StoryboardIR.model_validate(
        {
            **_storyboard_payload(),
            "storyboard_id": "storyboard-intent-tcp-evidence",
            "lesson_id": "intent-tcp-evidence",
            "document_id": "tcp-evidence",
            "learning_intent": _intent().question,
        }
    )

    async def fake_ingest(source: QuerySourceInput, **_: object) -> DocumentIR:
        calls.append(f"search:{source.query}")
        return _document()

    async def fake_intent_storyboard(
        intent: VisualizationIntent,
        document: DocumentIR,
        *,
        output_dir: Path,
    ) -> StoryboardIR:
        calls.append(f"storyboard:{intent.question}:{document.document_id}:{output_dir.name}")
        return storyboard

    async def forbidden_lesson(*_: object, **__: object) -> None:
        raise AssertionError("query animation must not call the LessonIR generator")

    monkeypatch.setattr(animation_service, "ingest_source", fake_ingest)
    monkeypatch.setattr(
        animation_service,
        "generate_intent_storyboard",
        fake_intent_storyboard,
    )
    monkeypatch.setattr(animation_service, "generate_lesson", forbidden_lesson)
    monkeypatch.setattr(
        animation_service,
        "require_llm_config",
        lambda: LLMConfig(base_url="https://example.com", api_key="test", model="test"),
    )

    spec = asyncio.run(
        animation_service.generate_animation(
            QuerySourceInput(query=_intent().question),
            output_dir=tmp_path,
        )
    )

    assert [call.split(":", 1)[0] for call in calls] == ["search", "storyboard"]
    assert spec.storyboard_id == "storyboard-intent-tcp-evidence"
    assert spec.learning_intent == _intent().question
    assert spec.scenes[0].learning_question == "客户端和服务器如何确认连接可以建立？"
    assert spec.scenes[0].visual_pattern == "state_transition"
    assert spec.scenes[0].claims[0].source_refs == ["tcp-handshake-evidence"]
    assert spec.animation_ir is not None
    assert spec.animation_ir.metadata.learningIntent == _intent().question
    assert spec.animation_ir.scenes[0].metadata.claims[0].source_refs == ["tcp-handshake-evidence"]
    run_directories = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_directories) == 1
    run_directory = run_directories[0]
    assert {
        "02-document-ir.json",
        "03-lesson-ir.json",
        "04-storyboard-ir.json",
        "05-animation-ir.json",
        "06-render-spec.json",
    } <= {path.name for path in run_directory.iterdir()}
    skipped_lesson = json.loads((run_directory / "03-lesson-ir.json").read_text(encoding="utf-8"))
    assert skipped_lesson["status"] == "skipped"
