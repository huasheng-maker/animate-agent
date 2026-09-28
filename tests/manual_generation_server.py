"""Opt-in local browser fixture. No LLM or source network requests are made.

Run: uv run uvicorn manual_generation_server:app --app-dir tests --port 8017
POST /__test/advance/{run_id} advances one real fixture milestone.
This module is never imported by the production entrypoint.
"""

import asyncio
from typing import Any

import animate_agent.api as api
from animate_agent.animation import job_routes, xiaoyi
from animate_agent.animation.progress import report_progress
from animate_agent.animation_ir.compiler import compile_storyboard_render_spec
from animate_agent.paths import PROJECT_ROOT, STORYBOARD_SAMPLES_DIR
from animate_agent.rendering.models import RenderSpec
from animate_agent.storyboard.models import StoryboardIR

api.DEFAULT_RUNS_DIR = PROJECT_ROOT / "output" / "playwright" / "generation-jobs"
job_routes.RUNS_DIR = api.DEFAULT_RUNS_DIR
gates: dict[str, asyncio.Queue[bool]] = {}


async def fixture_generation(source: Any, *, job_id: str) -> RenderSpec:
    gate: asyncio.Queue[bool] = asyncio.Queue()
    gates[job_id] = gate
    report_progress("stage", stage="source_ingestion")
    await gate.get()
    report_progress(
        "artifact",
        stage="source_ingestion",
        name="document",
        value={
            "document_id": f"fixture-{job_id}",
            "title": "Controller：让实际状态接近期望状态",
            "sections": [
                {
                    "id": "observe",
                    "title": "观察当前状态",
                    "level": 1,
                    "blocks": [
                        {
                            "id": "b1",
                            "type": "paragraph",
                            "text": (
                                "Controller 持续观察系统，将实际状态与期望状态比较。"
                                "发现差异后采取动作，再观察结果。"
                            ),
                        },
                    ],
                },
                {
                    "id": "reconcile",
                    "title": "比较与协调",
                    "level": 1,
                    "blocks": [
                        {
                            "id": "b2",
                            "type": "paragraph",
                            "text": (
                                "协调循环不是一次性命令。环境变化后，控制器仍会持续调整，"
                                "让系统逐步接近期望状态。"
                            ),
                        },
                    ],
                },
            ],
        },
    )
    report_progress("stage", stage="intent_storyboard_generation")
    report_progress("model_call")
    await gate.get()
    if getattr(source, "query", "") == "failure":
        from animate_agent.visualization.agent import StoryboardGenerationError

        raise StoryboardGenerationError(
            "deliberate fixture schema failure",
            "第 2 幕对象过多：13 个，上限 12 个。自动修复仍未通过，请缩小讲解范围后重新生成。",
        )
    storyboard = StoryboardIR.model_validate_json(
        (STORYBOARD_SAMPLES_DIR / "controller.json").read_text(encoding="utf-8")
    )
    report_progress(
        "artifact",
        stage="intent_storyboard_generation",
        name="storyboard",
        value={
            "title": storyboard.title,
            "scenes": [
                {"id": scene.id, "title": scene.teaching_goal} for scene in storyboard.scenes
            ],
        },
    )
    report_progress("stage", stage="animation_ir_compile")
    await gate.get()
    return compile_storyboard_render_spec(storyboard)


job_routes.generate_animation = fixture_generation
xiaoyi.generate_animation = fixture_generation
app = api.app


@app.post("/__test/advance/{run_id}")
async def advance(run_id: str) -> dict[str, bool]:
    await gates[run_id].put(True)
    return {"ok": True}
