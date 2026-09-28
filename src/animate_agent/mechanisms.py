"""Bounded, executable teaching models shared by planning and rendering.

The model selects parameters and phases, never executable expressions or code.
Numerical examples are illustrative; evidence references support the mechanism.
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(ge=-10, le=10, allow_inf_nan=False)]
Row = Annotated[list[Number], Field(min_length=2, max_length=8)]
Label = Annotated[str, Field(min_length=1, max_length=24)]


class MechanismBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_refs: list[str] = Field(min_length=1, max_length=12)
    example_label: Literal["教学示例 · 简化计算模型"] = "教学示例 · 简化计算模型"


class LanguageModelPlan(MechanismBase):
    kind: Literal["language_model"]
    phases: list[Literal["tokens", "embedding", "attention", "predict", "append"]] = Field(
        min_length=1, max_length=12
    )
    vocabulary: list[Label] = Field(
        default_factory=lambda: ["The", "cat", "sat", "on", "mat"], min_length=3, max_length=8,
    )
    token_ids: list[int] = Field(default_factory=lambda: [0, 1], min_length=1, max_length=5)
    embeddings: list[Row] = Field(
        default_factory=lambda: [[1, 0, .2], [.2, 1, .5], [.8, .4, 1], [.3, .5, -.2], [.5, .8, .1]],
        min_length=3, max_length=8,
    )
    temperature: float = Field(default=1, ge=.1, le=2, allow_inf_nan=False)

    @model_validator(mode="after")
    def dimensions(self) -> LanguageModelPlan:
        if not 3 <= len(self.vocabulary) <= 8 or len(set(self.vocabulary)) != len(self.vocabulary):
            raise ValueError("vocabulary must contain 3..8 distinct tokens")
        if len(self.embeddings) != len(self.vocabulary):
            raise ValueError("one embedding row is required per vocabulary token")
        if len({len(row) for row in self.embeddings}) != 1:
            raise ValueError("embedding rows must have equal dimensions")
        if any(index < 0 or index >= len(self.vocabulary) for index in self.token_ids):
            raise ValueError("token_ids must index the vocabulary")
        if len(self.token_ids) + self.phases.count("append") > 8:
            raise ValueError("teaching context is limited to 8 visible tokens")
        return self


class NeuralNetworkPlan(MechanismBase):
    kind: Literal["neural_network"]
    phases: list[Literal["inputs", "weighted_sum", "activation", "loss", "update"]] = Field(
        min_length=1, max_length=12
    )
    inputs: tuple[Number, Number] = (1, .5)
    weights: tuple[Number, Number] = (.8, -.4)
    bias: Number = .1
    target: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    learning_rate: float = Field(default=.5, gt=0, le=1, allow_inf_nan=False)


class LinearTransformPlan(MechanismBase):
    kind: Literal["linear_transform"]
    phases: list[Literal["basis", "transform", "vector", "determinant"]] = Field(
        min_length=1, max_length=12
    )
    matrix: tuple[tuple[Number, Number], tuple[Number, Number]] = ((1, 1), (0, 1))
    vector: tuple[Number, Number] = (1, 1)


class DerivativePlan(MechanismBase):
    kind: Literal["derivative"]
    phases: list[Literal["curve", "secant", "limit", "tangent"]] = Field(
        min_length=1, max_length=12
    )
    coefficients: tuple[Number, Number, Number] = (1, 0, 0)
    x: float = Field(default=1, ge=-2, le=2, allow_inf_nan=False)
    h: float = Field(default=1, ge=.05, le=2, allow_inf_nan=False)


class PacketNetworkPlan(MechanismBase):
    kind: Literal["packet_network"]
    phases: list[Literal["send", "travel", "ack", "timeout", "retransmit", "deliver"]] = Field(
        min_length=1, max_length=12
    )
    protocol: Literal["tcp_handshake", "stop_and_wait"] = "stop_and_wait"
    latency: float = Field(default=1, ge=.2, le=2, allow_inf_nan=False)
    drop_first: bool = True
    payload: Label = "Hello"


MechanismPlan = Annotated[
    LanguageModelPlan | NeuralNetworkPlan | LinearTransformPlan
    | DerivativePlan | PacketNetworkPlan,
    Field(discriminator="kind"),
]


def required_mechanism(question: str) -> str | None:
    """Guard only supported, focused intents; never map every math/network topic to a demo."""
    patterns = (
        ("language_model", r"embedding|嵌入|自回归|下一个\s*token|"
         r"how\s+(?:does|do)\s+(?:an?\s+)?(?:llms?|large language models?)\s+work|"
         r"(?:llm|大语言模型).*工作原理"),
        ("neural_network", r"神经元|neuron|神经网络.*(?:工作原理|前向传播|反向传播)|"
         r"how\s+does\s+(?:a\s+)?neural network\s+work"),
        ("linear_transform", r"线性变换|linear transformation|matrix.*transform"),
        ("derivative", r"导数.*(?:原理|割线|切线)|(?:割线|切线).*导数|"
         r"derivative.*(?:secant|tangent)|how.*derivative.*work"),
        ("packet_network", r"三次握手|tcp\s+handshake|停止等待|stop.and.wait"),
    )
    return next((kind for kind, pattern in patterns if re.search(pattern, question, re.I)), None)


def mechanism_prompt() -> str:
    """Examples are serialized from the executable contract, not a second schema."""
    examples: list[MechanismBase] = [
        LanguageModelPlan(kind="language_model", source_refs=["真实证据ID"],
                          phases=["tokens", "embedding", "attention", "predict", "append",
                                  "predict", "append"]),
        NeuralNetworkPlan(kind="neural_network", source_refs=["真实证据ID"],
                          phases=["inputs", "weighted_sum", "activation", "loss", "update"]),
        LinearTransformPlan(kind="linear_transform", source_refs=["真实证据ID"],
                            phases=["basis", "transform", "vector", "determinant"]),
        DerivativePlan(kind="derivative", source_refs=["真实证据ID"],
                       phases=["curve", "secant", "limit", "tangent"]),
        PacketNetworkPlan(kind="packet_network", source_refs=["真实证据ID"],
                          phases=["send", "travel", "timeout", "retransmit", "deliver"]),
    ]
    return (
        "\n可计算机制：scene 可添加 mechanism，替代通用框线画面。以下能力适用时必须优先使用，"
        "不适用的主题继续使用原有图元，不得强行套用。\n"
        "language_model 用于 token、embedding、因果注意力和逐 token 推理（简化单头模型）；"
        "neural_network 用于单神经元加权、sigmoid、平方损失与梯度更新；"
        "linear_transform 用于二维线性变换；derivative 用于二次多项式的割线趋近切线；"
        "packet_network 用于 TCP 三次握手或停止等待协议的丢包重传。\n"
        "phases 必须与本幕 steps 一一对应，步骤描述必须讲述对应计算；"
        "解释自回归时至少重复两轮 predict/append，让追加后的 token 参与下一轮。"
        "保留 objects/highlights 与 claims 的证据关联，"
        "但不要把矩阵的单元格拆为 objects。机制场景 controls 固定为空，编译器提供实际计算控件。"
        "source_refs 必须引用本幕已有的真实证据。数值是明确标注的教学示例，"
        "不代表网页或真实模型测量值。"
        "How does LLM work 优先解释推理生成，不要用训练定制流程替代。"
        "网络 protocol=tcp_handshake 时使用 send/travel/ack/deliver；"
        "stop_and_wait 使用 send/travel/timeout/retransmit/deliver。"
        "仅输出下列字段，不能输出代码、表达式字符串或新 kind。\n"
        + "\n".join(json.dumps(example.model_dump(), ensure_ascii=False) for example in examples)
    )
