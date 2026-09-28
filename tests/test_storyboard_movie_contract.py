from __future__ import annotations

import json

from animate_agent.paths import STORYBOARD_SAMPLES_DIR
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.validation import StoryboardLimits, validate_storyboard


def _storyboard() -> StoryboardIR:
    return StoryboardIR.model_validate_json(
        (STORYBOARD_SAMPLES_DIR / "controller.json").read_text(encoding="utf-8")
    )


def test_step_limit_applies_to_the_whole_movie() -> None:
    storyboard = _storyboard()
    assert sum(len(scene.steps) for scene in storyboard.scenes) == 7
    assert not any(
        issue.code == "step_count_invalid"
        for issue in validate_storyboard(storyboard, limits=StoryboardLimits())
    )

    payload = json.loads(storyboard.model_dump_json())
    payload["scenes"][1]["steps"].append(payload["scenes"][1]["steps"][-1])
    payload["scenes"][1]["steps"][-1]["id"] = "one-step-too-many"
    too_many = StoryboardIR.model_validate(payload)

    issues = validate_storyboard(too_many, limits=StoryboardLimits())
    assert any(issue.code == "step_count_invalid" and issue.where == "scenes" for issue in issues)


def test_each_step_must_use_evidence_bound_to_its_scene() -> None:
    storyboard = _storyboard().model_copy(deep=True)
    storyboard.scenes[0].steps[0].source_refs = ["invented-source"]

    issues = validate_storyboard(storyboard, limits=StoryboardLimits())

    assert any(issue.code == "step_source_ref_outside_scene" for issue in issues)
