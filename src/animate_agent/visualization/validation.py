"""Intent-specific quality checks layered on the existing Storyboard validator."""

from __future__ import annotations

from animate_agent.documents.models import DocumentIR
from animate_agent.storyboard.models import StoryboardIR
from animate_agent.storyboard.validation import (
    StoryboardLimits,
    ValidationIssue,
    validate_storyboard,
)
from animate_agent.visualization.models import VisualizationIntent


def validate_intent_storyboard(
    storyboard: StoryboardIR,
    *,
    intent: VisualizationIntent,
    document: DocumentIR,
    limits: StoryboardLimits,
) -> list[ValidationIssue]:
    """Validate renderability plus evidence grounding without full-document coverage."""

    issues = validate_storyboard(storyboard, document=document, limits=limits)
    valid_refs = {
        block.id for section in document.sections for block in section.blocks
    } | {section.id for section in document.sections}

    if storyboard.learning_intent != intent.question:
        issues.append(
            ValidationIssue(
                "intent_mismatch",
                "learning_intent",
                "Storyboard 的 learning_intent 必须与用户问题一致",
            )
        )

    for scene_index, scene in enumerate(storyboard.scenes):
        where = f"scenes[{scene_index}]"
        if not scene.learning_question.strip():
            issues.append(
                ValidationIssue(
                    "learning_question_missing",
                    f"{where}.learning_question",
                    "intent 模式的场景必须声明要回答的具体问题",
                )
            )
        if scene.visual_pattern is None:
            issues.append(
                ValidationIssue(
                    "visual_pattern_missing",
                    f"{where}.visual_pattern",
                    "场景必须选择一种受控的可视化知识结构",
                )
            )
        if not scene.claims:
            issues.append(
                ValidationIssue(
                    "claims_missing",
                    f"{where}.claims",
                    "场景至少需要一条有出处的事实 claim",
                )
            )
            continue

        object_refs = {ref for obj in scene.objects for ref in obj.source_refs}
        for claim_index, claim in enumerate(scene.claims):
            claim_where = f"{where}.claims[{claim_index}]"
            unknown = sorted(set(claim.source_refs) - valid_refs)
            if unknown:
                issues.append(
                    ValidationIssue(
                        "claim_source_ref_unknown",
                        f"{claim_where}.source_refs",
                        f"claim 引用了不存在的 evidence id：{'、'.join(unknown)}",
                    )
                )
            missing_on_objects = sorted(set(claim.source_refs) - object_refs)
            if missing_on_objects:
                issues.append(
                    ValidationIssue(
                        "claim_not_visualized",
                        claim_where,
                        "claim 的证据没有绑定到任何可视对象："
                        + "、".join(missing_on_objects),
                    )
                )
    return issues
