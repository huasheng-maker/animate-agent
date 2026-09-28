"""Small experimental planning contract; not a new production pipeline stage."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from animate_agent.documents.models import DocumentIR

Text = Annotated[str, Field(min_length=1, max_length=400)]
Parameter = Literal["obstacleY", "radius", "margin", "range", "mode", "preset"]


class PlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeRelation(PlanRecord):
    cause: Text
    effect: Text


class VisualModel(PlanRecord):
    id: Literal["lidar-grid-v1"]
    assumptions: list[Text] = Field(min_length=1, max_length=8)


class VisualBeat(PlanRecord):
    id: Literal["sense", "inflate", "search", "execute"]
    title: Text
    change: Text
    explanation: Text
    source_ref: Text


class VisualInteraction(PlanRecord):
    parameter: Parameter
    observe: Text


class UnderstandingCheck(PlanRecord):
    question: Text
    answer: Text
    experiment: Parameter


class VisualPlan(PlanRecord):
    version: Literal[1]
    goal: Text
    source_refs: list[Text] = Field(min_length=1, max_length=8)
    relations: list[KnowledgeRelation] = Field(min_length=1, max_length=6)
    model: VisualModel
    beats: list[VisualBeat] = Field(min_length=4, max_length=4)
    interactions: list[VisualInteraction] = Field(min_length=1, max_length=6)
    checks: list[UnderstandingCheck] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_bindings(self) -> VisualPlan:
        if [beat.id for beat in self.beats] != ["sense", "inflate", "search", "execute"]:
            raise ValueError("lidar-grid-v1 requires sense/inflate/search/execute in order")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("source_refs must be unique")
        if any(beat.source_ref not in self.source_refs for beat in self.beats):
            raise ValueError("beat evidence must belong to source_refs")
        parameters = [item.parameter for item in self.interactions]
        if len(set(parameters)) != len(parameters):
            raise ValueError("interaction parameters must be unique")
        if any(check.experiment not in parameters for check in self.checks):
            raise ValueError("a check must name an available interaction")
        return self


def validate_plan_evidence(plan: VisualPlan, document: DocumentIR) -> None:
    """Use existing DocumentIR block IDs; do not duplicate source text in the plan."""
    available = {block.id for section in document.sections for block in section.blocks}
    missing = set(plan.source_refs) - available
    if missing:
        raise ValueError(f"Visual Plan references missing document blocks: {sorted(missing)}")
