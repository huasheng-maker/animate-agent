"""Knowledge Agent: turn a DocumentIR into a structured LessonIR."""

from animate_agent.knowledge.agent import KnowledgeAgent
from animate_agent.knowledge.models import (
    KnowledgeComparison,
    KnowledgeConcept,
    KnowledgeEntity,
    KnowledgeEquation,
    KnowledgeExample,
    KnowledgeProcess,
    KnowledgeProcessStep,
    KnowledgeRelationship,
    KnowledgeState,
    LessonIR,
    LessonScene,
)

__all__ = [
    "KnowledgeAgent",
    "KnowledgeComparison",
    "KnowledgeConcept",
    "KnowledgeEntity",
    "KnowledgeEquation",
    "KnowledgeExample",
    "KnowledgeProcess",
    "KnowledgeProcessStep",
    "KnowledgeRelationship",
    "KnowledgeState",
    "LessonIR",
    "LessonScene",
]
