"""NumPy preflight of the same bounded graph evaluated by math.js in the browser."""
from __future__ import annotations

from typing import Any

import numpy as np

from animate_agent.composition import CompositionPlan


def evaluate_program(
    plan: CompositionPlan, *, time: float = 0, progress: float = 0, phase: int = 0,
    sample: float = 0, parameters: dict[str, float] | None = None,
) -> dict[str, Any]:
    nodes = {n.id: n for n in plan.nodes}
    values: dict[str, Any] = {}
    clocks = dict(time=time, progress=progress, phase=phase, sample=sample)

    def run(node_id: str) -> Any:
        if node_id in values:
            return values[node_id]
        node = nodes[node_id]
        args = [run(arg) for arg in node.args]
        op = node.op
        if op == "constant":
            result = np.asarray(node.value, dtype=float)
        elif op == "parameter":
            result = np.asarray((parameters or {}).get(node.id, node.value), dtype=float)
        elif op in clocks:
            result = np.asarray(clocks[op], dtype=float)
        elif op in {"row", "item"}:
            i = float(args[1])
            if not i.is_integer() or not 0 <= i < len(args[0]):
                raise ValueError(f"{node.id}: lookup index out of range")
            result = args[0][int(i)]
        elif op == "softmax":
            exp = np.exp(args[0] - np.max(args[0]))
            result = exp / np.sum(exp)
        elif op == "sigmoid":
            x = float(args[0])
            result = 1 / (1 + np.exp(-x)) if x >= 0 else np.exp(x) / (1 + np.exp(x))
        elif op == "normalize":
            result = args[0] / np.linalg.norm(args[0])
        elif op == "lerp":
            result = args[0] + (args[1] - args[0]) * args[2]
        elif op == "select":
            result = args[1] if args[0] else args[2]
        elif op in {"vector", "stack", "concat"}:
            result = np.concatenate(args) if op == "concat" else np.stack(args)
        else:
            operations: dict[str, Any] = {
                "add": np.add, "subtract": np.subtract, "multiply": np.multiply,
                "divide": np.divide, "matmul": np.matmul, "dot": np.dot, "norm": np.linalg.norm,
                "sin": np.sin, "cos": np.cos, "exp": np.exp, "tanh": np.tanh,
                "transpose": np.transpose, "sum": np.sum, "floor": np.floor,
                "argmax": np.argmax,
                "less": np.less, "clamp": np.clip,
            }
            result = operations[op](*args)
        result = np.asarray(result, dtype=float)
        if not np.all(np.isfinite(result)) or np.any(np.abs(result) > 1e12):
            raise ValueError(f"{node.id}: nonfinite/oversized calculation")
        values[node_id] = result
        return result

    with np.errstate(divide="raise", over="raise", invalid="raise", under="ignore"):
        try:
            for node in plan.nodes:
                run(node.id)
        except (FloatingPointError, IndexError) as exc:
            raise ValueError(f"composition numeric failure: {exc}") from exc
    return {key: value.tolist() for key, value in values.items()}


def preflight_program(plan: CompositionPlan) -> None:
    """Sample phase boundaries, curves, and parameter extremes (not a formal proof)."""
    cases: list[dict[str, float]] = [{}]
    for node in plan.nodes:
        if node.op == "parameter":
            assert node.min is not None and node.max is not None
            cases.extend([{node.id: node.min}, {node.id: node.max}])
    samples = {0.0}
    for view in plan.visuals:
        if view.kind == "curve":
            samples.update([view.sample_range[0], sum(view.sample_range) / 2, view.sample_range[1]])
    for phase in range(len(plan.phases)):
        for progress in (0., .5, 1.):
            for parameters in cases:
                for sample in samples:
                    values = evaluate_program(
                        plan, time=(phase + progress) * 4, progress=progress,
                        phase=phase, sample=sample, parameters=parameters,
                    )
                    for view in plan.visuals:
                        if view.active_index is not None:
                            active = float(values[view.active_index])
                            if not active.is_integer() or not 0 <= active < len(values[view.data]):
                                raise ValueError(f"{view.id}: active_index outside data rows/items")
                        if view.reveal_count is not None:
                            count = float(values[view.reveal_count])
                            if not count.is_integer() or not 0 <= count <= len(values[view.data]):
                                raise ValueError(f"{view.id}: reveal_count outside token sequence")
                        if view.kind == "circle" and values[view.data] < 0:
                            raise ValueError(f"{view.id}: circle radius is negative")
                        if view.kind == "tokens" and any(
                            not float(i).is_integer() or not 0 <= i < len(view.labels)
                            for i in values[view.data]
                        ):
                            raise ValueError(f"{view.id}: token ID outside labels vocabulary")
