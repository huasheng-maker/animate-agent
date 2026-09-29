"""Bounded, executable teaching models shared by planning and rendering.

The model selects parameters and phases, never executable expressions or code.
Numerical examples are illustrative; evidence references support the mechanism.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from animate_agent.composition import CompositionPlan, composition_prompt

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
    | DerivativePlan | PacketNetworkPlan | CompositionPlan,
    Field(discriminator="kind"),
]


def mechanism_prompt() -> str:
    """Expose reusable operations; legacy plans remain readable but are not advertised."""
    return composition_prompt()
