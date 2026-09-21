"""Validated semantic knowledge and lesson representation produced by the Knowledge Agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeItem(BaseModel):
    """Strict base for evidence-backed semantic units."""

    model_config = ConfigDict(extra="forbid")

    source_refs: list[str] = Field(default_factory=list, min_length=1, max_length=24)


class KnowledgeEntity(KnowledgeItem):
    name: str
    kind: str
    description: str


class KnowledgeConcept(KnowledgeItem):
    name: str
    definition: str


class KnowledgeRelationship(KnowledgeItem):
    source: str
    target: str
    relation: Literal[
        "causes",
        "depends_on",
        "part_of",
        "transforms_into",
        "precedes",
        "contrasts_with",
        "spatial",
        "associates_with",
    ]
    explanation: str


class KnowledgeProcessStep(KnowledgeItem):
    order: int = Field(ge=1)
    title: str
    description: str


class KnowledgeProcess(KnowledgeItem):
    name: str
    purpose: str
    steps: list[KnowledgeProcessStep] = Field(min_length=2, max_length=16)


class KnowledgeState(KnowledgeItem):
    entity: str
    name: str
    description: str
    transitions_to: list[str] = Field(default_factory=list, max_length=12)


class KnowledgeExample(KnowledgeItem):
    title: str
    description: str


class KnowledgeEquation(KnowledgeItem):
    expression: str
    explanation: str
    variables: dict[str, str] = Field(default_factory=dict)


class KnowledgeComparison(KnowledgeItem):
    left: str
    right: str
    dimensions: list[str] = Field(min_length=1, max_length=12)
    conclusion: str


class LessonScene(BaseModel):
    """One teachable scene in a generated lesson.

    `narration` carries a floor as well as a ceiling: a scene too thin to fill
    ~80 characters is a scene too thin to carry its own animation, and should
    have been merged with a neighbour (see the Knowledge Agent prompt).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    objective: str
    narration: str = Field(min_length=80, max_length=200)
    # The cap must stay above the longest single list the source can hand a
    # scene: a source block listing N items forces one scene to cover all N, and
    # a cap below N makes the model silently drop items (and then contradict its
    # own objective, which still says "N").
    key_points: list[str] = Field(default_factory=list, min_length=2, max_length=8)
    source_refs: list[str] = Field(default_factory=list)


class LessonIR(BaseModel):
    """Knowledge graph-like semantics plus a teachable scene plan."""

    model_config = ConfigDict(extra="forbid")

    lesson_id: str
    document_id: str
    title: str
    subject: str
    summary: str
    learning_objectives: list[str] = Field(default_factory=list, min_length=2, max_length=4)
    entities: list[KnowledgeEntity] = Field(default_factory=list, max_length=40)
    concepts: list[KnowledgeConcept] = Field(default_factory=list, max_length=40)
    relationships: list[KnowledgeRelationship] = Field(default_factory=list, max_length=60)
    processes: list[KnowledgeProcess] = Field(default_factory=list, max_length=20)
    states: list[KnowledgeState] = Field(default_factory=list, max_length=40)
    examples: list[KnowledgeExample] = Field(default_factory=list, max_length=20)
    equations: list[KnowledgeEquation] = Field(default_factory=list, max_length=20)
    comparisons: list[KnowledgeComparison] = Field(default_factory=list, max_length=20)
    scenes: list[LessonScene] = Field(default_factory=list, min_length=1)
