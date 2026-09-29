"""Offline regression checks for the exact JSON shipped with the gallery."""
import itertools
from pathlib import Path

import pytest

from animate_agent.composition_math import evaluate_program, preflight_program
from animate_agent.rendering.models import RenderSpec

DEMOS = Path(__file__).resolve().parents[1] / "frontend/public/demos"


@pytest.mark.parametrize("name", ["circular-motion", "llm"])
def test_published_demos_validate_and_compute_across_actual_movie_time(name):
    spec = RenderSpec.model_validate_json((DEMOS / f"{name}.json").read_text("utf-8"))
    assert spec.animation_ir is not None
    for scene in spec.animation_ir.scenes:
        plan = scene.mechanism
        assert plan is not None and plan.kind == "composition"
        preflight_program(plan)
        parameters = [node for node in plan.nodes if node.op == "parameter"]
        for settings in itertools.product(*[(n.min, n.value, n.max) for n in parameters]):
            values = dict(zip((n.id for n in parameters), settings, strict=True))
            elapsed = 0.0
            for phase, beat in enumerate(scene.beats):
                duration = beat.durationInFrames / spec.animation_ir.fps
                for progress in (0.0, .25, .5, .75, 1.0):
                    computed = evaluate_program(
                        plan, time=elapsed + progress * duration, phase=phase,
                        progress=progress, parameters=values,
                    )
                    for view in plan.visuals:
                        if view.kind == "tokens":
                            assert all(0 <= i < len(view.labels) for i in computed[view.data])
                        if view.reveal_count:
                            assert 0 <= computed[view.reveal_count] <= len(computed[view.data])
                elapsed += duration


def test_llm_demo_computes_lookup_and_feedback_from_changed_input():
    spec = RenderSpec.model_validate_json((DEMOS / "llm.json").read_text("utf-8"))
    lookup, prediction, feedback = [s.mechanism for s in spec.scenes]
    assert evaluate_program(lookup, parameters={"token-index": 2})["selected-vec"] == [-.2,.5,.9]
    assert next(v for v in prediction.visuals if v.id == "state-input").data == "input-state"
    a = evaluate_program(feedback, parameters={"seed-token": 0})
    b = evaluate_program(feedback, parameters={"seed-token": 2})
    assert a["sequence"] == [0, 1, 0, 1]
    assert b["sequence"] == [2, 2, 2, 2]
