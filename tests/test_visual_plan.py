import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from animate_agent.documents.models import DocumentIR
from animate_agent.visual_planning import VisualPlan, validate_plan_evidence

ROOT = Path(__file__).resolve().parents[1]


def payload() -> dict:
    return json.loads((ROOT / "frontend/player/lidar/visual-plan.json").read_text("utf-8"))


class VisualPlanTests(unittest.TestCase):
    def test_demo_plan_references_real_document_blocks(self) -> None:
        plan = VisualPlan.model_validate(payload())
        document = DocumentIR.model_validate_json(
            (ROOT / "data/samples/documents/lidar_navigation.document.json").read_text("utf-8")
        )
        validate_plan_evidence(plan, document)
        document.sections[0].blocks.pop()
        with self.assertRaisesRegex(ValueError, "missing document blocks"):
            validate_plan_evidence(plan, document)

    def test_invalid_plans_are_rejected(self) -> None:
        for mutation in ["code", "model", "evidence", "experiment", "order"]:
            with self.subTest(mutation=mutation):
                data = payload()
                if mutation == "code":
                    data["javascript"] = "arbitrary-code"
                elif mutation == "model":
                    data["model"]["id"] = "unimplemented-engine"
                elif mutation == "evidence":
                    data["beats"][0]["source_ref"] = "invented-block"
                elif mutation == "experiment":
                    data["interactions"] = [
                        item for item in data["interactions"] if item["parameter"] != "radius"
                    ]
                else:
                    data["beats"].reverse()
                with self.assertRaises(ValidationError):
                    VisualPlan.model_validate(data)
