"""The prompt example is executable through the real planning/compiler boundary."""
import copy
import math

import pytest
from pydantic import ValidationError

from animate_agent.composition import (
    CompositionPlan,
    circular_motion_example,
    composition_prompt,
    curve_example,
    feedback_example,
    symbol_lookup_example,
)
from animate_agent.composition_math import evaluate_program, preflight_program
from animate_agent.rendering.layout import layout_storyboard
from animate_agent.storyboard.models import StoryboardIR
from test_mechanisms import fixture_payload


def example_storyboard():
    payload = fixture_payload("composition", ["velocity", "acceleration"])
    scene = payload["scenes"][0]
    plan = circular_motion_example()
    plan["source_refs"] = ["mechanism-evidence"]
    for view in plan["visuals"]:
        view["source_refs"] = ["mechanism-evidence"]
    scene["mechanism"] = plan
    scene["objects"] = []
    for step, phase in zip(scene["steps"], plan["phases"], strict=True):
        step["highlights"] = phase["focus"]
        step["object_states"] = {}
    return StoryboardIR.model_validate(payload)


def test_circle_example_geometry_and_compilation():
    plan = CompositionPlan.model_validate(circular_motion_example())
    preflight_program(plan)
    for time in (0, .5, 2, 6):
        values = evaluate_program(plan, time=time)
        p, v, a = (values[key] for key in ("position", "velocity", "acceleration"))
        assert math.hypot(*p) == pytest.approx(2)
        assert sum(x*y for x, y in zip(p, v, strict=True)) == pytest.approx(0)
        assert a == pytest.approx([-.64*x for x in p])
    spec = layout_storyboard(example_storyboard())
    assert spec.scenes[0].mechanism.kind == "composition"
    assert spec.scenes[0].mechanism.visuals[0].glow
    assert "vector_arrow" in composition_prompt()
    assert len(spec.scenes[0].controls) == 1


@pytest.mark.parametrize("kind", ["ball", "particle", "vector_arrow", "vehicle", "cart"])
def test_new_element_types_require_two_dimensional_data(kind):
    raw = circular_motion_example()
    raw["visuals"][0]["kind"] = kind
    CompositionPlan.model_validate(raw)
    raw["visuals"][0]["data"] = "r"
    with pytest.raises(ValidationError, match="needs shape"):
        CompositionPlan.model_validate(raw)


@pytest.mark.parametrize("field,value", [("radius", 0), ("radius", -1), ("mass", 0),
                                         ("mass", float("inf"))])
def test_invalid_physical_attributes(field, value):
    raw = copy.deepcopy(circular_motion_example())
    raw["visuals"][0][field] = value
    with pytest.raises(ValidationError):
        CompositionPlan.model_validate(raw)


@pytest.mark.parametrize("index", [0, "0", "0.0", "0e0"])
def test_literal_lookup_arguments_are_lifted_without_mutating_input(index):
    raw = circular_motion_example()
    raw["nodes"].extend([
        {"id": "literal-0", "op": "constant", "value": 99},
        {"id": "first", "op": "item", "args": ["position", index]},
    ])
    original = copy.deepcopy(raw)
    plan = CompositionPlan.model_validate(raw)
    assert raw == original
    assert evaluate_program(plan)["first"] == pytest.approx(2)
    lookup = next(n for n in plan.nodes if n.id == "first")
    assert lookup.args[1] != "literal-0"
    assert CompositionPlan.model_validate(plan.model_dump()) == plan


@pytest.mark.parametrize("argument", [True, "p[0]", "1+2", "missing", "1e999", 10001])
def test_literal_normalization_never_executes_or_guesses_arguments(argument):
    raw = circular_motion_example()
    raw["nodes"].append({"id": "first", "op": "item", "args": ["position", argument]})
    with pytest.raises(ValidationError):
        CompositionPlan.model_validate(raw)


def test_normalized_literals_still_obey_graph_budget():
    raw = circular_motion_example()
    raw["nodes"].extend({"id": f"padding-{i}", "op": "constant", "value": 0}
                        for i in range(63 - len(raw["nodes"])))
    raw["nodes"].append({"id": "first", "op": "item", "args": ["position", "0"]})
    with pytest.raises(ValidationError, match="64"):
        CompositionPlan.model_validate(raw)


def test_reports_all_scalar_geometry_bindings_with_actionable_coordinates():
    raw = curve_example()
    raw["visuals"][0]["data"] = "x"
    raw["visuals"][1]["data"] = "tx"
    with pytest.raises(ValidationError) as failure:
        CompositionPlan.model_validate(raw)
    errors = failure.value.errors()
    assert len(errors) == 2
    assert {e["loc"] for e in errors} == {("visuals", 0, "data"), ("visuals", 1, "data")}
    assert all("has shape ()" in e["msg"] for e in errors)
    assert "vector(sample,y)" in errors[0]["msg"]


def test_evidence_summary_unions_without_fabricating_or_discarding_refs():
    raw = curve_example()
    raw["visuals"][1]["source_refs"] = ["another-real-source"]
    plan = CompositionPlan.model_validate(raw)
    assert plan.source_refs == ["function-evidence", "another-real-source"]
    assert raw["source_refs"] == ["function-evidence"]
    assert CompositionPlan.model_validate(plan.model_dump()) == plan


def test_curve_few_shot_has_real_coordinates_and_parameter_dependence():
    plan = CompositionPlan.model_validate(curve_example())
    preflight_program(plan)
    assert evaluate_program(plan, sample=2)["xy"] == [2, 2]
    assert evaluate_program(plan, sample=2, parameters={"k": 1})["xy"] == [2, 4]
    point = evaluate_program(plan, time=math.pi / 2)["point-xy"]
    assert point == pytest.approx([1, .5])


def test_evidence_union_does_not_bypass_reference_budget():
    raw = curve_example()
    raw["source_refs"] = [f"source-{i}" for i in range(12)]
    with pytest.raises(ValidationError, match="exceeds 12"):
        CompositionPlan.model_validate(raw)


def test_lookup_example_selects_actual_matrix_rows():
    plan = CompositionPlan.model_validate(symbol_lookup_example())
    preflight_program(plan)
    a = evaluate_program(plan, parameters={"index": 0})
    b = evaluate_program(plan, parameters={"index": 2})
    assert a["selected"] == [.2, .8, -.1]
    assert b["selected"] == [-.2, .5, .9]
    raw = plan.model_dump()
    raw["nodes"].append({"id": "choice", "op": "argmax", "args": ["selected"]})
    assert evaluate_program(CompositionPlan.model_validate(raw))["choice"] == 1


def test_feedback_predictions_depend_on_previous_output_and_seed():
    plan = CompositionPlan.model_validate(feedback_example())
    preflight_program(plan)
    for seed in range(3):
        for phase in range(3):
            values = evaluate_program(plan, phase=phase, parameters={"seed": seed})
            expected = [(seed + i) % 3 for i in range(4)]
            assert values["sequence"] == expected
            assert values["count"] == phase + 2
            assert values["winner"] == expected[phase + 1]
            assert sum(values["current"]) == pytest.approx(1)
