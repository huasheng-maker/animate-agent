"""Prompt templates for the Storyboard Agent.

The vocabulary section is **generated from `rendering/registry.py`**, never
hand-copied. A name the renderer does not know must not be offered to the model,
and a name the renderer does know must not be forgotten here; rendering it means
the two cannot disagree, and a test asserts every registered name shows up.
"""

from __future__ import annotations

from typing import get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from animate_agent.knowledge.models import LessonIR
from animate_agent.mechanisms import mechanism_prompt
from animate_agent.storyboard.models import (
    StoryboardClaim,
    StoryboardControl,
    StoryboardObject,
    StoryboardScene,
    StoryboardStep,
)

#: Fields the model authors, paired with the model that declares them. Only this
#: list lives here; the bounds are read off the declarations at call time, so a
#: changed bound cannot leave the prompt behind.
_CONSTRAINED_FIELDS: tuple[tuple[str, type[BaseModel], str], ...] = (
    ("scene.id", StoryboardScene, "id"),
    ("scene.teaching_goal", StoryboardScene, "teaching_goal"),
    ("scene.learning_question", StoryboardScene, "learning_question"),
    ("scene.claims", StoryboardScene, "claims"),
    ("scene.lesson_scene_ids", StoryboardScene, "lesson_scene_ids"),
    ("scene.objects", StoryboardScene, "objects"),
    ("scene.controls", StoryboardScene, "controls"),
    ("scene.renderer_hint", StoryboardScene, "renderer_hint"),
    ("object.id", StoryboardObject, "id"),
    ("object.label", StoryboardObject, "label"),
    ("claim.id", StoryboardClaim, "id"),
    ("claim.text", StoryboardClaim, "text"),
    ("claim.source_refs", StoryboardClaim, "source_refs"),
    ("step.id", StoryboardStep, "id"),
    ("step.title", StoryboardStep, "title"),
    ("step.description", StoryboardStep, "description"),
    ("step.highlights", StoryboardStep, "highlights"),
    ("step.key_points", StoryboardStep, "key_points"),
    ("control.id", StoryboardControl, "id"),
    ("control.label", StoryboardControl, "label"),
    ("control.target_property", StoryboardControl, "target_property"),
    ("control.unit", StoryboardControl, "unit"),
)


def _read_bounds(field: FieldInfo) -> tuple[int | None, int | None, str | None]:
    """Pull length bounds and a regex out of a field's constraint metadata.

    Duck-typed on attribute names rather than isinstance-checked against
    `annotated_types`: those attribute names have been stable across pydantic
    versions, the concrete classes have not.
    """
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    for meta in field.metadata:
        value = getattr(meta, "min_length", None)
        if value is not None:
            min_length = value
        value = getattr(meta, "max_length", None)
        if value is not None:
            max_length = value
        value = getattr(meta, "pattern", None)
        if value is not None:
            pattern = value
    return min_length, max_length, pattern


def render_field_constraints(*, composition: bool = False) -> str:
    """Render the schema's own bounds as prompt text.

    Generated from the models, for the same reason the vocabulary is generated
    from the registry: **a bound that lives only in the schema is a bound the
    model has never been told, and it will violate it.** That is how the first
    real run failed — every step came back with a description under a
    20-character floor the prompt had never mentioned.
    """
    lines = ["## 字段长度约束（由 schema 生成，请严格遵守）"]
    for label, model, field_name in _CONSTRAINED_FIELDS:
        if composition and (label.startswith(("object.", "control."))
                            or label in {"scene.objects", "scene.controls"}):
            continue
        field = model.model_fields[field_name]
        min_length, max_length, pattern = _read_bounds(field)
        unit = "个" if get_origin(field.annotation) is list else "字"
        if min_length is None:
            bound = f"最多 {max_length} {unit}"
        elif max_length is None:
            bound = f"至少 {min_length} {unit}"
        else:
            bound = f"{min_length}~{max_length} {unit}"
        if pattern is not None:
            bound += f"，必须匹配 `{pattern}`"
        lines.append(f"- `{label}`：{bound}")
    return "\n".join(lines)


STORYBOARD_SYSTEM_PROMPT = """你是一位动画分镜师。
用户会给你一份已经审核通过的教学课程大纲（LessonIR，包含若干场景，
每个场景有 id、标题、教学目标、讲解文案、关键词和原文出处）。

你的任务是把它转成一份「动画分镜」（StoryboardIR）——一个 JSON 对象，
描述每一幕画面上有哪些对象、按什么节拍动、有哪些可交互控件。
JSON 结构如下（不要输出 JSON 以外的任何文字）：

{
  "title": "圆周运动教学示例",
  "subject": "运动学",
  "eyebrow": "质点与矢量",
  "scenes": [
    {
      "id": "motion",
      "scene_type": "chain",
      "teaching_goal": "观察速度与加速度的方向",
      "learning_question": "圆周运动为何需要指向圆心的加速度？",
      "visual_pattern": "spatial_relation",
      "claims": [
        {
          "id": "motion-claim",
          "text": "匀速圆周运动的速度沿切线，加速度指向圆心。",
          "source_refs": [
            "motion-evidence"
          ]
        }
      ],
      "lesson_scene_ids": [
        "lesson-scene-id"
      ],
      "objects": [],
      "controls": [],
      "params": {},
      "renderer_hint": null,
      "mechanism": {
        "kind": "composition",
        "goal": "观察圆周运动的速度与加速度方向",
        "observable_change": "质点沿圆周运动，速度保持切向，加速度始终指向圆心",
        "source_refs": [
          "motion-evidence"
        ],
        "nodes": [
          {
            "id": "r",
            "op": "parameter",
            "value": 2,
            "min": 1,
            "max": 3,
            "step": 0.1,
            "label": "轨道半径"
          },
          {
            "id": "w",
            "op": "constant",
            "value": 0.8
          },
          {
            "id": "t",
            "op": "time"
          },
          {
            "id": "theta",
            "op": "multiply",
            "args": [
              "w",
              "t"
            ]
          },
          {
            "id": "c",
            "op": "cos",
            "args": [
              "theta"
            ]
          },
          {
            "id": "s",
            "op": "sin",
            "args": [
              "theta"
            ]
          },
          {
            "id": "unit",
            "op": "vector",
            "args": [
              "c",
              "s"
            ]
          },
          {
            "id": "position",
            "op": "multiply",
            "args": [
              "r",
              "unit"
            ]
          },
          {
            "id": "negative",
            "op": "constant",
            "value": -1
          },
          {
            "id": "minus-s",
            "op": "multiply",
            "args": [
              "negative",
              "s"
            ]
          },
          {
            "id": "tangent",
            "op": "vector",
            "args": [
              "minus-s",
              "c"
            ]
          },
          {
            "id": "speed",
            "op": "multiply",
            "args": [
              "r",
              "w"
            ]
          },
          {
            "id": "velocity",
            "op": "multiply",
            "args": [
              "speed",
              "tangent"
            ]
          },
          {
            "id": "w2",
            "op": "multiply",
            "args": [
              "w",
              "w"
            ]
          },
          {
            "id": "minus-w2",
            "op": "multiply",
            "args": [
              "negative",
              "w2"
            ]
          },
          {
            "id": "acceleration",
            "op": "multiply",
            "args": [
              "minus-w2",
              "position"
            ]
          }
        ],
        "visuals": [
          {
            "id": "body",
            "kind": "ball",
            "data": "position",
            "radius": 0.18,
            "mass": 1,
            "glow": true,
            "label": "质点 m=1 kg",
            "color": "teal",
            "source_refs": [
              "motion-evidence"
            ]
          },
          {
            "id": "velocity-arrow",
            "kind": "vector_arrow",
            "data": "velocity",
            "origin": "position",
            "label": "速度 v（切向）",
            "color": "gold",
            "source_refs": [
              "motion-evidence"
            ]
          },
          {
            "id": "acceleration-arrow",
            "kind": "vector_arrow",
            "data": "acceleration",
            "origin": "position",
            "label": "加速度 a（指向圆心）",
            "color": "red",
            "source_refs": [
              "motion-evidence"
            ]
          },
          {
            "id": "orbit",
            "kind": "circle",
            "data": "r",
            "label": "轨道",
            "color": "blue",
            "source_refs": [
              "motion-evidence"
            ]
          }
        ],
        "x_range": [
          -5,
          5
        ],
        "y_range": [
          -4,
          4
        ],
        "phases": [
          {
            "visible": [
              "body",
              "velocity-arrow",
              "acceleration-arrow",
              "orbit"
            ],
            "focus": [
              "body",
              "velocity-arrow"
            ]
          },
          {
            "visible": [
              "body",
              "velocity-arrow",
              "acceleration-arrow",
              "orbit"
            ],
            "focus": [
              "acceleration-arrow"
            ]
          }
        ]
      },
      "steps": [
        {
          "id": "step-0",
          "title": "切向速度",
          "description": "观察质点绕圆心运动，速度箭头始终沿切线方向。",
          "highlights": [
            "body",
            "velocity-arrow"
          ],
          "object_states": {},
          "key_points": [
            "切向速度"
          ],
          "source_refs": [
            "motion-evidence"
          ]
        },
        {
          "id": "step-1",
          "title": "向心加速度",
          "description": "观察加速度箭头随质点转动，始终指向圆心。",
          "highlights": [
            "acceleration-arrow"
          ],
          "object_states": {},
          "key_points": [
            "向心加速度"
          ],
          "source_refs": [
            "motion-evidence"
          ]
        }
      ]
    }
  ]
}

硬性要求：

- 使用 composition 数学坐标、枚举颜色和数据绑定；不要写像素样式或可执行代码。
- **场景覆盖**：`lesson_scene_ids` 必须覆盖 LessonIR 里的**每一个**场景 id，
  不多不少。一个 storyboard 场景可以覆盖 1~2 个课程场景（内容单薄的相邻场景合并成一幕），
  但**不允许新增**课程里没有的场景。
- **节拍数量**：整部动画合计写 3~7 个 `steps`；每个场景至少一个。
- **视觉推理**：每幕填写 `learning_question`、`visual_pattern` 和至少一个 `claims`。
  根据 KnowledgeIR 中的过程、状态、因果、比较、空间或时间关系选视觉模式，
  不要把所有主题都降级成同一种卡片/流程模板。
- **事实绑定**：`claims` 只写 LessonIR/KnowledgeIR 中有来源的事实，每条 claim 的
  `source_refs` 必须直接复制对应语义项或课程场景的来源 id。
- **每个节拍必须有视觉变化**：至少写一个 `highlights`，或至少改一个 `object_states`。
  只讲文字、画面上什么都没动的节拍不是节拍。
- **每个节拍必须有出处**：`source_refs` 至少一个，只能引用当前场景的 claim 或对象已经
  携带的真实来源 id。
- **关键词覆盖**：每个场景各节拍的 `key_points` 合起来，必须**逐字**包含它所覆盖的
  那些课程场景的**全部** `key_points`。请直接照抄，不要改写、不要合并近义词。
- **出处覆盖**：每个场景各对象的 `source_refs` 合起来，必须覆盖它所覆盖的课程场景的
  全部 `source_refs`，且只能引用源文档里真实存在的 id。
- **可视对象**：mechanism.visuals 的每个图元至少在一拍 visible；steps.highlights 引用图元ID。
- **交互**：至少一个场景有真正影响画面的 parameter 计算节点。
  scenes[].objects=[]、controls=[]、steps[].object_states={}，全部由编译器派生。
  不要自行生成 controls，不要将 parameter 节点复制到 controls 数组。
- 忠于课程大纲中的机制事实和命名；允许自拟演示机制的输入、矩阵和参数，
  必须标注“教学示例，非实测/训练参数”，不得声称这些具体数值来自原文。
- `title` / `subject` 会自动沿用课程大纲，你可以省略；其余字段必填。
- **`id` 只用小写 ASCII**：小写字母开头，之后只能是小写字母、数字、下划线、连字符。
  不要用大写字母、中文、空格或下标字符。物理量请写成 `v0` / `theta` / `range-r`，
  **不要**写 `V₀` / `θ` / `R`——这些会把 `id` 打回。中文请放到 `label` 里。

"""

# The constraint block is appended rather than retyped: see `render_field_constraints`.
STORYBOARD_SYSTEM_PROMPT = (
    STORYBOARD_SYSTEM_PROMPT + "\n" + render_field_constraints(composition=True)
    + mechanism_prompt() + "\n"
)


def build_storyboard_prompt(lesson: LessonIR, *, allowed_renderers: tuple[str, ...] = ()) -> str:
    """Serialize a LessonIR plus the generated vocabulary into the user message."""
    lines: list[str] = [
        f"课程标题：{lesson.title}",
        f"学科：{lesson.subject}",
        f"摘要：{lesson.summary}",
        "",
        "整体学习目标：",
    ]
    lines.extend(f"- {objective}" for objective in lesson.learning_objectives)
    lines.append("")

    lines.append("## 结构化知识（用于选择视觉模式，不得遗漏关系方向和步骤顺序）")
    for entity in lesson.entities:
        lines.append(
            f"- 实体 {entity.name}（{entity.kind}）：{entity.description}；"
            f"来源：{'、'.join(entity.source_refs)}"
        )
    for concept in lesson.concepts:
        lines.append(
            f"- 概念 {concept.name}：{concept.definition}；"
            f"来源：{'、'.join(concept.source_refs)}"
        )
    for relationship in lesson.relationships:
        lines.append(
            f"- 关系 {relationship.source} --{relationship.relation}--> "
            f"{relationship.target}：{relationship.explanation}；"
            f"来源：{'、'.join(relationship.source_refs)}"
        )
    for process in lesson.processes:
        lines.append(f"- 过程 {process.name}（{process.purpose}）：")
        for step in process.steps:
            lines.append(
                f"  {step.order}. {step.title}：{step.description}；"
                f"来源：{'、'.join(step.source_refs)}"
            )
    for state in lesson.states:
        transitions = "、".join(state.transitions_to) or "无"
        lines.append(
            f"- 状态 {state.entity}/{state.name}：{state.description}；转移到：{transitions}；"
            f"来源：{'、'.join(state.source_refs)}"
        )
    for example in lesson.examples:
        lines.append(
            f"- 示例 {example.title}：{example.description}；"
            f"来源：{'、'.join(example.source_refs)}"
        )
    for equation in lesson.equations:
        variables = "、".join(
            f"{name}={meaning}" for name, meaning in equation.variables.items()
        )
        lines.append(
            f"- 公式 {equation.expression}：{equation.explanation}；"
            f"变量：{variables or '无'}；来源：{'、'.join(equation.source_refs)}"
        )
    for comparison in lesson.comparisons:
        lines.append(
            f"- 比较 {comparison.left} vs {comparison.right}："
            f"{'、'.join(comparison.dimensions)}；结论：{comparison.conclusion}；"
            f"来源：{'、'.join(comparison.source_refs)}"
        )
    lines.append("")

    lines.append("## 课程场景（必须全部覆盖）")
    for scene in lesson.scenes:
        lines.append(f"### [{scene.id}] {scene.title}")
        lines.append(f"教学目标：{scene.objective}")
        lines.append(f"讲解文案：{scene.narration}")
        lines.append(f"关键词（必须逐字出现在 key_points 里）：{'、'.join(scene.key_points)}")
        refs = "、".join(scene.source_refs)
        lines.append(f"原文出处（必须被某个对象的 source_refs 覆盖）：{refs}")
        lines.append("")

    lines.append("# 生成契约")
    lines.append("使用系统消息中的 composition 能力目录。objects=[]、controls=[]；"
                 "只在 mechanism.nodes 中声明 parameter 交互。")

    return "\n".join(lines)
