"""Reproduce reviewed gallery assets from local runs; never calls an API.

This review applies only to the published demo, not to generation. Raw runs stay
unchanged. Run `uv run python scripts/export_reviewed_demos.py` from the repo root
after obtaining the recorded local run artifacts. Playback needs no raw runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from animate_agent.animation_ir.compiler import compile_storyboard
from animate_agent.documents.models import DocumentIR
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.validation import StoryboardLimits, validate_storyboard

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "circular-motion": "a09e69a85b1e49ed87570a60ffffcce6",
    "llm": "ab4a96bab8614428a2a1a6a4bc9d0532",
}
REVIEW = [
    "Correct the input-state visual to bind to input-state, not the predicted token.",
    "Explain that the score table isolates softmax and does not implement Attention/FFN.",
    "Label the feedback example as a first-order model, not a full-context Transformer.",
]


def export() -> None:
    manifest = {}
    for name, run_id in RUNS.items():
        run = ROOT / "data" / "runs" / run_id
        raw = json.loads((run / "04-storyboard-ir.json").read_text(encoding="utf-8"))
        document = DocumentIR.model_validate_json((run / "02-document-ir.json").read_text("utf-8"))
        if name == "llm":
            scene = raw["scenes"][1]
            scene["mechanism"]["goal"] = "用简化评分表观察 softmax 概率与贪心选择"
            view = scene["mechanism"]["visuals"][0]
            view.update(kind="readout", data="input-state", label="当前输入状态编号", labels=[])
            scene["steps"][0]["description"] = (
                "真实模型通过 Attention 和 FFN 计算状态；这里用教学评分表代替这一过程，"
                "只观察不同状态的词表得分如何变成概率。"
            )
            loop = raw["scenes"][2]
            loop["mechanism"]["example_label"] = "教学示例 · 一阶反馈，非完整 Transformer"
            loop["steps"][1]["title"] = "第二轮预测"
            loop["steps"][2]["description"] = (
                "上一轮算出的 token 成为下一轮输入，序列继续增长。此简化模型只使用最后一个"
                " token；真实 LLM 会利用可见上下文，而不是只看最后一个 token。"
            )
            for scene in raw["scenes"]:
                scene["objects"] = []
        storyboard = StoryboardIR.model_validate(raw)
        issues = validate_storyboard(storyboard, document=document, limits=StoryboardLimits())
        if issues:
            raise ValueError(issues)
        spec = layout_storyboard(storyboard)
        spec.animation_ir = compile_storyboard(storyboard, document=document, render_spec=spec)
        output = ROOT / "frontend" / "public" / "demos" / f"{name}.json"
        output.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        manifest[name] = {
            "run_id": run_id, "model": "kimi-k2.6", "query": storyboard.learning_intent,
            "review_adjustments": REVIEW if name == "llm" else [],
            "source_artifacts": "Local data/runs/<run_id>; not needed to play the bundled demo.",
        }
    (ROOT / "frontend/public/demos/provenance.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )


if __name__ == "__main__":
    export()
