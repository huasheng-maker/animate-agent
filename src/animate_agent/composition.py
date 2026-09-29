"""A subject-independent, bounded dataflow language for explanation animations.

The graph is a declaration of library operations, not model-authored source code.
Dimensions and references are checked before any plan reaches the browser.
"""
from __future__ import annotations

import json
import math
import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=48)]
Num = Annotated[float, Field(ge=-10000, le=10000, allow_inf_nan=False)]
Value = Num | list[Num] | list[list[Num]]
Op = Literal[
    "constant", "parameter", "time", "progress", "phase", "sample",
    "add", "subtract", "multiply", "divide", "matmul", "dot", "norm", "normalize",
    "sin", "cos", "exp", "sigmoid", "tanh", "softmax", "transpose", "vector", "stack",
    "row", "item", "concat", "lerp", "less", "select", "floor", "clamp", "sum", "argmax",
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DataNode(Record):
    id: Id
    op: Op
    args: list[Id] = Field(
        default_factory=list, max_length=16,
        description="Node ID references, not expressions. time/progress/phase/sample use args=[]. "
        "vector(x,y) joins scalar nodes; stack joins equal-length row vectors.",
    )
    value: Value | None = None
    label: str = Field(default="", max_length=24)
    min: Num | None = None
    max: Num | None = None
    step: Annotated[float, Field(gt=0, le=1000, allow_inf_nan=False)] = .1


class Visual(Record):
    id: Id
    kind: Literal[
        "point", "vector", "curve", "trail", "circle", "matrix", "tokens", "bars", "readout",
        "ball", "particle", "vector_arrow", "vehicle", "cart",
    ]
    data: Id = Field(description="Node ID for visual data. curve/point/trail require [x,y], "
                    "never a scalar. curve coordinates must be computed from the sample node.")
    radius: Annotated[float, Field(gt=0, le=5, allow_inf_nan=False)] = .15
    mass: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)] = 1
    glow: bool = False
    origin: Id | None = None
    active_index: Id | None = Field(
        default=None, description="Scalar node: highlighted row/item index")
    reveal_count: Id | None = Field(
        default=None, description="Scalar node: number of visible tokens")
    label: str = Field(min_length=1, max_length=24)
    labels: list[Annotated[str, Field(max_length=24)]] = Field(default_factory=list, max_length=32)
    color: Literal["teal", "gold", "violet", "red", "blue"] = "teal"
    source_refs: list[str] = Field(min_length=1, max_length=12)
    sample_range: tuple[Num, Num] = (-3, 3)
    trail_seconds: Annotated[float, Field(gt=0, le=10, allow_inf_nan=False)] = 2


class Phase(Record):
    focus: list[Id] = Field(min_length=1, max_length=8)
    visible: list[Id] = Field(min_length=1, max_length=8)


Shape = tuple[int, ...]


def value_shape(value: Value | None) -> Shape:
    if value is None:
        raise ValueError("constant/parameter requires value")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("values must be finite")
        return ()
    if not 1 <= len(value) <= 32:
        raise ValueError("vectors/matrices require 1..32 entries")
    rows = [value_shape(row) for row in value]
    if len(set(rows)) != 1 or len(rows[0]) > 1:
        raise ValueError("data must be a rectangular scalar/vector/matrix")
    if rows[0] and len(value) * rows[0][0] > 256:
        raise ValueError("matrix exceeds 256 cells")
    return (len(value), *rows[0])


def output_shape(node: DataNode, shapes: dict[str, Shape]) -> Shape:
    args = [shapes[arg] for arg in node.args]
    op = node.op
    arities = {"constant": 0, "parameter": 0, "time": 0, "progress": 0, "phase": 0,
               "sample": 0, "lerp": 3, "select": 3, "clamp": 3}
    binary = {"add", "subtract", "multiply", "divide", "matmul", "dot", "row", "item", "less"}
    count = arities.get(op, 2 if op in binary else 1)
    if op in {"vector", "stack", "concat"}:
        if not args:
            raise ValueError(f"{node.id}: {op} needs inputs")
    elif len(args) != count:
        raise ValueError(f"{node.id}: {op} requires {count} args")
    if op in {"constant", "parameter"}:
        shape = value_shape(node.value)
        if op == "parameter" and (
            shape or node.min is None or node.max is None or node.min >= node.max
            or not isinstance(node.value, (float, int))
            or not node.min <= node.value <= node.max
        ):
            raise ValueError(f"{node.id}: parameter requires scalar value within min < max")
        return shape
    if node.value is not None or node.min is not None or node.max is not None:
        raise ValueError(f"{node.id}: only constants/parameters may declare value/bounds")
    if op in {"time", "progress", "phase", "sample"}:
        return ()
    if op in {"add", "subtract", "multiply"}:
        if args[0] != args[1] and () not in args:
            raise ValueError(f"{node.id}: elementwise operands must have matching shapes")
        return args[0] or args[1]
    if op == "divide":
        if args[1]:
            raise ValueError(f"{node.id}: divisor must be scalar")
        return args[0]
    if op == "matmul":
        a, b = args
        if len(a) != 2 or len(b) not in (1, 2) or a[1] != b[0]:
            raise ValueError(f"{node.id}: matmul incompatible dimensions {a}, {b}")
        return (a[0], *b[1:])
    if op == "dot":
        if args[0] != args[1] or len(args[0]) != 1:
            raise ValueError(f"{node.id}: dot requires equal vectors")
        return ()
    if op in {"norm", "normalize", "softmax", "sum", "argmax"}:
        if len(args[0]) != 1:
            raise ValueError(f"{node.id}: {op} requires a vector")
        return args[0] if op in {"normalize", "softmax"} else ()
    if op == "transpose":
        if len(args[0]) != 2:
            raise ValueError(f"{node.id}: transpose requires matrix")
        return tuple(reversed(args[0]))
    if op == "vector":
        if any(args):
            raise ValueError(
                f"{node.id}: vector requires scalar inputs, got {args}; "
                "use stack for equal-length vectors, or item to select scalar components"
            )
        return (len(args),)
    if op == "stack":
        if len(args[0]) != 1 or len(set(args)) != 1:
            raise ValueError(f"{node.id}: stack requires equal vectors")
        return (len(args), args[0][0])
    if op in {"row", "item"}:
        if len(args[0]) != (2 if op == "row" else 1) or args[1]:
            raise ValueError(f"{node.id}: invalid lookup dimensions")
        return args[0][1:]
    if op == "concat":
        if any(len(s) != 1 for s in args):
            raise ValueError(f"{node.id}: concat requires vectors")
        return (sum(s[0] for s in args),)
    if op == "lerp":
        if args[0] != args[1] or args[2]:
            raise ValueError(f"{node.id}: lerp requires same-shaped endpoints and scalar progress")
        return args[0]
    if op == "select":
        if args[0] or args[1] != args[2]:
            raise ValueError(f"{node.id}: select requires scalar condition, same-shaped branches")
        return args[1]
    if op in {"sin", "cos", "exp", "sigmoid", "tanh", "floor", "less", "clamp"}:
        if any(args):
            raise ValueError(f"{node.id}: {op} requires scalars")
        return ()
    raise ValueError(f"unimplemented operation {op}")


class CompositionPlan(Record):
    kind: Literal["composition"]
    goal: str = Field(min_length=4, max_length=160)
    observable_change: str = Field(min_length=4, max_length=200)
    example_label: str = Field(default="教学示例 · 可组合计算", max_length=40)
    source_refs: list[str] = Field(min_length=1, max_length=12)
    nodes: list[DataNode] = Field(min_length=1, max_length=64)
    visuals: list[Visual] = Field(min_length=1, max_length=8)
    phases: list[Phase] = Field(min_length=1, max_length=12)
    x_range: tuple[Num, Num] = (-4, 4)
    y_range: tuple[Num, Num] = (-3, 3)

    @model_validator(mode="before")
    @classmethod
    def lift_numeric_arguments(cls, value: Any) -> Any:
        """Canonicalize literal operands; the renderer still receives only node IDs.

        This preserves numeric meaning without evaluating expressions or guessing
        missing references. All generated constants go through the normal limits.
        """
        if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
            return value
        nodes = value["nodes"]
        used = {n.get("id") for n in nodes if isinstance(n, dict)}
        constants: list[dict[str, Any]] = []
        literals: dict[float, str] = {}
        result = []
        for node in nodes:
            if not isinstance(node, dict) or not isinstance(node.get("args"), list):
                result.append(node)
                continue
            args = []
            for arg in node["args"]:
                numeric = type(arg) in (int, float) or (
                    isinstance(arg, str)
                    and re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", arg)
                )
                if not numeric:
                    args.append(arg)
                    continue
                number = float(arg)
                if not math.isfinite(number) or abs(number) > 10000:
                    raise ValueError("literal argument must be finite and within [-10000,10000]")
                if number not in literals:
                    index = len(constants)
                    identity = f"literal-{index}"
                    while identity in used:
                        index += 1
                        identity = f"literal-{index}"
                    used.add(identity)
                    literals[number] = identity
                    constants.append({"id": identity, "op": "constant", "value": number})
                args.append(literals[number])
            result.append({**node, "args": args})
        return {**value, "nodes": [*constants, *result]}

    @model_validator(mode="after")
    def graph_contract(self) -> CompositionPlan:
        by_id = {n.id: n for n in self.nodes}
        visual_ids = {v.id for v in self.visuals}
        if len(by_id) != len(self.nodes) or len(visual_ids) != len(self.visuals):
            raise ValueError("duplicate computation/visual id")
        if sum(n.op == "parameter" for n in self.nodes) > 6:
            raise ValueError("at most 6 interactive parameters")
        if any(lo >= hi for lo, hi in [self.x_range, self.y_range]):
            raise ValueError("coordinate ranges must increase")
        shapes: dict[str, Shape] = {}
        errors: list[InitErrorDetails] = []

        def problem(location: tuple[str | int, ...], message: str) -> None:
            errors.append({"type": "value_error", "loc": location,
                           "input": None, "ctx": {"error": ValueError(message)}})

        def visit(node_id: str, visiting: set[str]) -> None:
            if node_id in shapes:
                return
            if node_id not in by_id or node_id in visiting:
                raise ValueError(f"missing reference or cycle at {node_id}")
            node = by_id[node_id]
            for arg in node.args:
                visit(arg, visiting | {node_id})
            shape = output_shape(node, shapes)
            if math.prod(shape) > 256 or any(dim > 32 for dim in shape):
                raise ValueError(f"{node_id}: output exceeds data budget")
            shapes[node_id] = shape

        for index, node in enumerate(self.nodes):
            try:
                visit(node.id, set())
            except ValueError as exc:
                problem(("nodes", index), str(exc))
        # source_refs is a summary, not an independently authored evidence layer.
        # Union only existing declarations; real source validation still runs against DocumentIR.
        refs = list(dict.fromkeys([*self.source_refs,
                                  *(ref for view in self.visuals for ref in view.source_refs)]))
        if len(refs) > 12:
            problem(("source_refs",), "combined visual/plan evidence exceeds 12 references")
        else:
            self.source_refs = refs
        for index, view in enumerate(self.visuals):
            for field in ("active_index", "reveal_count"):
                reference = getattr(view, field)
                if reference is not None and shapes.get(reference) != ():
                    problem(("visuals", index, field), f"{view.id}: {field} needs scalar node")
            if view.reveal_count is not None and view.kind != "tokens":
                problem(("visuals", index, "reveal_count"), "reveal_count only applies to tokens")
            if view.active_index is not None and view.kind not in {"matrix", "tokens", "bars"}:
                problem(("visuals", index, "active_index"), "active_index needs matrix/tokens/bars")
            shape = shapes.get(view.data)
            if shape is None:
                problem(("visuals", index, "data"),
                        f"{view.id}: missing or invalid data node {view.data}")
                continue
            expected: dict[str, Shape] = {key: (2,) for key in (
                "point", "vector", "curve", "trail", "ball", "particle",
                "vector_arrow", "vehicle", "cart",
            )}
            expected["circle"] = ()
            if view.kind in expected and shape != expected[view.kind]:
                problem(("visuals", index, "data"),
                        f"{view.id}: {view.kind} needs shape {expected[view.kind]}, "
                        f"but data={view.data} has shape {shape}. "
                        "For a 2D position, create vector with two scalar node IDs [x,y]. "
                        "A curve uses sample (args=[]) as its independent variable, "
                        "computes y from sample, and binds vector(sample,y). "
                        "A moving point separately binds vector(current_x,current_y).")
            if view.origin is not None and shapes.get(view.origin) != (2,):
                problem(("visuals", index, "origin"), f"{view.id}: origin must be a 2D point")
            if view.kind in {"tokens", "bars"} and len(shape) != 1:
                problem(("visuals", index, "data"), f"{view.id}: {view.kind} requires a vector")
            if view.kind == "matrix" and len(shape) not in (1, 2):
                problem(("visuals", index, "data"),
                        f"{view.id}: matrix requires vector/matrix data")
            if view.sample_range[0] >= view.sample_range[1]:
                problem(("visuals", index, "sample_range"),
                        f"{view.id}: sample range must increase")
        if errors:
            raise ValidationError.from_exception_data("CompositionPlan", errors)
        for phase in self.phases:
            if not set(phase.focus) <= set(phase.visible) <= visual_ids:
                raise ValueError("phase focus must be visible and reference real visuals")
        reachable: set[str] = set()

        def collect(node_id: str) -> None:
            if node_id not in reachable:
                reachable.add(node_id)
                for arg in by_id[node_id].args:
                    collect(arg)

        visible = {item for phase in self.phases for item in phase.visible}
        for view in self.visuals:
            if view.id not in visible:
                raise ValueError(f"{view.id}: visual is never visible")
            collect(view.data)
            if view.origin is not None:
                collect(view.origin)
            if view.active_index is not None:
                collect(view.active_index)
            if view.reveal_count is not None:
                collect(view.reveal_count)
        if any(n.op == "parameter" and n.id not in reachable for n in self.nodes):
            raise ValueError("interactive parameter must influence a visible calculation")
        return self


def composition_prompt() -> str:
    """Self-discoverable capability catalog, generated from the validated schema."""
    return (
        "\n# 可组合解释动画工具（默认生成方式）\n"
        "先理解用户想理解的机制，再决定需要展示的数据与变化，不按题目关键词选固定场景。"
        "每幕使用 mechanism.kind=composition。goal 写本幕解释目标，observable_change 写观众"
        "具体能观察到的变化。用 nodes 组成无环计算图，用 visuals 将计算结果绑定到画面，"
        "phases 与 steps 一一对应，focus/visible 引用 visual id。\n"
        "计算工具由 math.js 执行；几何工具由 JSXGraph 绘制。只能声明下面的算子，不能写 JS、"
        "Python、HTML、SVG 源码、表达式字符串或任意函数调用。\n"
        f"计算算子：{', '.join(get_args(Op))}。\n"
        "constant 的 value 为有限数字/向量/矩阵；parameter 是带 label/min/max/step/value 的"
        "标量滑杆；time 是本幕累计秒数，progress 是当前拍 0..1，phase 是从0起的拍号，"
        "sample 是 curve 采样自变量。其他算子 args 引用节点 id，不能携带 value。"
        "add/subtract/multiply 为逐元素（可标量缩放），divide 除标量；matmul 是矩阵乘法；"
        "row(矩阵,行号)、item(向量,索引)，索引必须在有效范围；vector(标量...)；"
        "stack(等长向量...)；concat(向量...)；lerp(同形起点,终点,0..1进度)；"
        '例如取向量第0项：先声明 {"id":"index-zero","op":"constant","value":0}，'
        '再写 {"id":"first","op":"item","args":["values","index-zero"]}。'
        "vector 只接收标量；把多个行向量组成矩阵必须用 stack，不能用 vector。"
        "less(a,b) 得到0/1；select(条件,真值,假值)；clamp(数值,下界,上界)。"
        "禁止除零和 normalize 零向量；softmax 用于向量概率；sin/cos 使用弧度。\n"
        "argmax(向量) 返回最大元素的索引（并列取第一个），可用于贪心选择，不能称为随机采样。"
        "matrix/tokens/bars 的 active_index 可绑定标量节点实现行或项高亮；"
        "tokens.reveal_count 绑定显示个数，后续token在该数量之外不会出现。\n"
        "重要：讲查表就展示表和选中的行，讲计算就展示变化的数值，讲序列追加就让序列变长。"
        "不要用几个移动小球代替查表、矩阵运算或token追加。物理运动才需要运动物体。"
        "自回归需要将上次生成的结果反馈到下次计算；可以展开少量节点示范几步，"
        "不能把固定序列的显示伪装成模型实际预测；简化模型须明确标注。\n"
        "输入图元必须绑定输入节点，不能误绑预测结果。若简化计算只依赖最后一个状态，"
        "旁白不得声称画面计算了全部历史、Attention或FFN；明确区分演示与真实机制。\n"
        "新增图元：ball/particle(data为二维位置,radius为坐标单位半径,mass为质量,glow为光晕);"
        "vector_arrow(data绑定二维向量[dx,dy],origin绑定起点);vehicle/cart(data绑定二维位置)。"
        "所有图元支持label/color。mass仅为物理属性，不自动求解运动；力必须由计算图显式计算。\n"
        "视觉工具：point(二维位置)、vector(二维方向，origin可绑定位置)、circle(半径，"
        "origin为圆心)、curve(二维位置由sample驱动)、trail(二维位置随time变化的历史轨迹)、"
        "matrix(数值向量/矩阵)、tokens(ID向量，labels是词表)、bars(数值向量)、readout(数值)。"
        "tokens 的 data 每一项都必须是 0..len(labels)-1 的整数ID，不能绑定坐标或概率。"
        "每条 claim 的所有证据必须由至少一个 visual.source_refs 携带，"
        "后端会把 visuals.source_refs 合并到 mechanism.source_refs；"
        "额外声明的 mechanism.source_refs 仍须由 visuals 覆盖，不能仅在 claims 中列来源。"
        "视觉的 data/origin 引用计算节点，不是像素坐标；x_range/y_range 是数学坐标范围。"
        "每个视觉必须有 label 和真实 source_refs。布局、字体和颜色由库与适配器控制。\n"
        "scene_type 固定 chain，objects=[]（服务器从 visuals 派生语义对象），controls=[]"
        "（从 parameter 节点生成）；steps.highlights 引用 visual id。claims/steps 仍引用真实证据。"
        "保留一条连续的数据变化主线，不要每讲一个词就新建一幕；动画必须展现计算/几何/状态"
        "变化，不能只显示名词。尽量使用参数让观众做对比。数字例子必须标为教学示例。"
        "工具无法表达的内容应明确说明边界，使用可表达的局部机制，不得虚构工具或物理结果。\n"
        "参数结构（JSON Schema，包含全部可用字段和约束）：\n"
        + json.dumps(CompositionPlan.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
        + "\nFew-Shot：用户问质点圆周运动时，以下是 mechanism 子对象。"
        "它不是所有问题的模板；根据意图组合图元。证据ID需替换为本次真实ID。"
        "配套steps与phases一一对应，objects/controls留空由服务器派生。\n"
        + json.dumps(circular_motion_example(), ensure_ascii=False)
        + "\n曲线工具 Few-Shot：y=k*x²，曲线使用 sample、当前点使用 time。"
        "sample 是无参数的输入节点，不是采样函数；curve/point 的 data 都必须是二维向量。"
        "这只是坐标绑定示例，不是训练损失定律；不得把任意示意曲线声称为真实训练结果。\n"
        + json.dumps(curve_example(), ensure_ascii=False)
        + "\n离散符号查表 Few-Shot（通用查表工具，不是固定主题模板）：\n"
        + json.dumps(symbol_lookup_example(), ensure_ascii=False)
        + "\n迭代反馈 Few-Shot：每一步用上次计算出的编号查表、计算概率、选择并追加，"
        "不是预写答案再逐字显示。此例是简化的一阶状态模型，不是完整Transformer；"
        "实际讲解须注明简化边界。phase/progress控制展示，parameter控制初始状态。\n"
        + json.dumps(feedback_example(), ensure_ascii=False)
    )


def circular_motion_example() -> dict[str, object]:
    """Executable few-shot; never selected by a topic/keyword router."""
    nodes: list[dict[str, object]] = [
        {"id": "r", "op": "parameter", "value": 2, "min": 1, "max": 3,
         "step": .1, "label": "轨道半径"},
        {"id": "w", "op": "constant", "value": .8},
        {"id": "t", "op": "time"},
        {"id": "theta", "op": "multiply", "args": ["w", "t"]},
        {"id": "c", "op": "cos", "args": ["theta"]},
        {"id": "s", "op": "sin", "args": ["theta"]},
        {"id": "unit", "op": "vector", "args": ["c", "s"]},
        {"id": "position", "op": "multiply", "args": ["r", "unit"]},
        {"id": "negative", "op": "constant", "value": -1},
        {"id": "minus-s", "op": "multiply", "args": ["negative", "s"]},
        {"id": "tangent", "op": "vector", "args": ["minus-s", "c"]},
        {"id": "speed", "op": "multiply", "args": ["r", "w"]},
        {"id": "velocity", "op": "multiply", "args": ["speed", "tangent"]},
        {"id": "w2", "op": "multiply", "args": ["w", "w"]},
        {"id": "minus-w2", "op": "multiply", "args": ["negative", "w2"]},
        {"id": "acceleration", "op": "multiply", "args": ["minus-w2", "position"]},
    ]
    views: list[dict[str, Any]] = [
        {"id": "body", "kind": "ball", "data": "position", "radius": .18,
         "mass": 1, "glow": True, "label": "质点 m=1 kg", "color": "teal"},
        {"id": "velocity-arrow", "kind": "vector_arrow", "data": "velocity",
         "origin": "position", "label": "速度 v（切向）", "color": "gold"},
        {"id": "acceleration-arrow", "kind": "vector_arrow", "data": "acceleration",
         "origin": "position", "label": "加速度 a（指向圆心）", "color": "red"},
        {"id": "orbit", "kind": "circle", "data": "r", "label": "轨道", "color": "blue"},
    ]
    for view in views:
        view["source_refs"] = ["motion-evidence"]
    visible = [str(view["id"]) for view in views]
    return {"kind": "composition", "goal": "观察圆周运动的速度与加速度方向",
            "observable_change": "质点沿圆周运动，速度保持切向，加速度始终指向圆心",
            "source_refs": ["motion-evidence"], "nodes": nodes, "visuals": views,
            "x_range": [-5, 5], "y_range": [-4, 4],
            "phases": [{"visible": visible, "focus": ["body", "velocity-arrow"]},
                       {"visible": visible, "focus": ["acceleration-arrow"]}]}


def curve_example() -> dict[str, Any]:
    return {
        "kind": "composition", "goal": "观察函数曲线与当前采样点",
        "observable_change": "点沿曲线移动，改变系数会同时改变曲线和点的位置",
        "source_refs": ["function-evidence"],
        "nodes": [
            {"id": "k", "op": "parameter", "value": .5, "min": .1, "max": 1,
             "step": .1, "label": "系数"},
            {"id": "x", "op": "sample", "args": []},
            {"id": "xx", "op": "multiply", "args": ["x", "x"]},
            {"id": "y", "op": "multiply", "args": ["k", "xx"]},
            {"id": "xy", "op": "vector", "args": ["x", "y"]},
            {"id": "t", "op": "time"},
            {"id": "tx", "op": "sin", "args": ["t"]},
            {"id": "txx", "op": "multiply", "args": ["tx", "tx"]},
            {"id": "ty", "op": "multiply", "args": ["k", "txx"]},
            {"id": "point-xy", "op": "vector", "args": ["tx", "ty"]},
        ],
        "visuals": [
            {"id": "curve", "kind": "curve", "data": "xy", "sample_range": [-2, 2],
             "label": "y=kx²", "source_refs": ["function-evidence"]},
            {"id": "point", "kind": "point", "data": "point-xy", "label": "当前点",
             "source_refs": ["function-evidence"]},
        ],
        "phases": [{"visible": ["curve", "point"], "focus": ["point"]}],
    }


def symbol_lookup_example() -> dict[str, Any]:
    return {
        "kind": "composition", "goal": "观察离散编号如何查表得到数值向量",
        "observable_change": "改变编号时，表中高亮行、当前符号和输出向量同步变化",
        "source_refs": ["lookup-evidence"],
        "nodes": [
            {"id": "index", "op": "parameter", "value": 0, "min": 0, "max": 2,
             "step": 1, "label": "符号编号"},
            {"id": "table", "op": "constant", "value": [[.2,.8,-.1],[.7,-.3,.4],[-.2,.5,.9]]},
            {"id": "selected", "op": "row", "args": ["table", "index"]},
            {"id": "ids", "op": "vector", "args": ["index"]},
        ],
        "visuals": [
            {"id": "symbol", "kind": "tokens", "data": "ids", "labels": ["猫", "狗", "跑"],
             "label": "当前符号", "source_refs": ["lookup-evidence"]},
            {"id": "lookup", "kind": "matrix", "data": "table", "active_index": "index",
             "label": "查找表", "labels": ["猫", "狗", "跑"], "source_refs": ["lookup-evidence"]},
            {"id": "result", "kind": "matrix", "data": "selected", "label": "输出向量",
             "source_refs": ["lookup-evidence"]},
        ],
        "phases": [{"visible": ["symbol", "lookup", "result"], "focus": ["lookup", "result"]}],
    }


def feedback_example() -> dict[str, Any]:
    """A bounded unrolled feedback computation; no topic router or executable model code."""
    nodes: list[dict[str, Any]] = [
        {"id": "seed", "op": "parameter", "value": 0, "min": 0, "max": 2,
         "step": 1, "label": "初始符号"},
        {"id": "scores", "op": "constant", "value": [[0, 3, 1], [1, 0, 3], [3, 1, 0]]},
        {"id": "prefix", "op": "vector", "args": ["seed"]},
        {"id": "beat", "op": "phase"},
        {"id": "one", "op": "constant", "value": 1},
        {"id": "two", "op": "constant", "value": 2},
        {"id": "count", "op": "add", "args": ["beat", "two"]},
    ]
    last = "seed"
    vectors = ["prefix"]
    for i in range(3):
        nodes.extend([
            {"id": f"logits-{i}", "op": "row", "args": ["scores", last]},
            {"id": f"probs-{i}", "op": "softmax", "args": [f"logits-{i}"]},
            {"id": f"choice-{i}", "op": "argmax", "args": [f"probs-{i}"]},
            {"id": f"token-{i}", "op": "vector", "args": [f"choice-{i}"]},
        ])
        last = f"choice-{i}"
        vectors.append(f"token-{i}")
    nodes.extend([
        {"id": "sequence", "op": "concat", "args": vectors},
        {"id": "distributions", "op": "stack", "args": [f"probs-{i}" for i in range(3)]},
        {"id": "current", "op": "row", "args": ["distributions", "beat"]},
        {"id": "winner", "op": "argmax", "args": ["current"]},
    ])
    refs = ["feedback-evidence"]
    return {
        "kind": "composition", "goal": "观察预测结果如何成为下一次计算的输入",
        "observable_change": "改变初始符号会改变整条生成序列，每一拍追加本轮计算结果",
        "source_refs": refs, "nodes": nodes,
        "visuals": [
            {"id": "history", "kind": "tokens", "data": "sequence", "reveal_count": "count",
             "labels": ["A", "B", "C"], "label": "简化模型的生成历史", "source_refs": refs},
            {"id": "probabilities", "kind": "bars", "data": "current", "active_index": "winner",
             "labels": ["A", "B", "C"], "label": "本轮概率与贪心选择", "source_refs": refs},
        ],
        "phases": [{"visible": ["history", "probabilities"], "focus": ["history"]}
                   for _ in range(3)],
    }
