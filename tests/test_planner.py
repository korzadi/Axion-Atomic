import json
import unittest
from unittest.mock import AsyncMock, patch

from agent.planner import (
    MAX_FIELD_CHARS,
    MAX_GOAL_CHARS,
    MAX_RESPONSE_CHARS,
    create_plan,
    validate_plan,
)


def valid_steps():
    return [
        {
            "title": f"Paso {index}",
            "rationale": "Motivo verificable",
            "risk": "low",
            "proposed_action": "Inspeccionar el alcance sin modificar archivos",
        }
        for index in range(1, 4)
    ]


class PlannerValidationTests(unittest.TestCase):
    def test_accepts_three_to_eight_well_formed_steps(self):
        for count in (3, 4, 8):
            with self.subTest(count=count):
                result = validate_plan(json.dumps(valid_steps()[:count]))
                self.assertEqual(len(result), count)

    def test_rejects_wrong_top_level_or_step_count(self):
        for value in ({}, "texto", [], valid_steps()[:2], valid_steps() * 3):
            with self.subTest(value=value):
                self.assertIsNone(validate_plan(json.dumps(value)))

    def test_rejects_missing_or_unexpected_fields(self):
        missing = valid_steps()
        del missing[0]["rationale"]
        extra = valid_steps()
        extra[0]["command"] = "rm -rf /"
        for value in (missing, extra):
            with self.subTest(value=value):
                self.assertIsNone(validate_plan(json.dumps(value)))

    def test_rejects_invalid_risk_and_non_string_fields(self):
        invalid_risk = valid_steps()
        invalid_risk[0]["risk"] = "critical"
        invalid_type = valid_steps()
        invalid_type[0]["title"] = ["Paso malicioso"]
        for value in (invalid_risk, invalid_type):
            with self.subTest(value=value):
                self.assertIsNone(validate_plan(json.dumps(value)))

    def test_rejects_oversized_fields_and_responses(self):
        oversized_field = valid_steps()
        oversized_field[0]["proposed_action"] = "x" * (MAX_FIELD_CHARS["proposed_action"] + 1)
        self.assertIsNone(validate_plan(json.dumps(oversized_field)))
        self.assertIsNone(validate_plan(" " * (MAX_RESPONSE_CHARS + 1)))

    def test_rejects_non_json_and_non_string_model_output(self):
        self.assertIsNone(validate_plan("not json"))
        self.assertIsNone(validate_plan(None))


class PlannerExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_model_plan_returns_safe_fallback_without_echoing_output(self):
        with patch("agent.planner.chat", new=AsyncMock(return_value='[{"command":"danger"}]')):
            result = await create_plan("Revisar el proyecto con cuidado")
        self.assertEqual(len(result), 1)
        self.assertIn("Revisar el objetivo", result[0]["title"])
        self.assertNotIn("danger", json.dumps(result))

    async def test_inference_failure_returns_safe_fallback(self):
        with patch("agent.planner.chat", new=AsyncMock(side_effect=RuntimeError("private provider detail"))):
            result = await create_plan("Revisar el proyecto con cuidado")
        self.assertEqual(len(result), 1)
        self.assertNotIn("private provider detail", json.dumps(result))

    async def test_rejects_invalid_goal_before_inference(self):
        chat = AsyncMock(return_value=json.dumps(valid_steps()))
        with patch("agent.planner.chat", new=chat):
            with self.assertRaises(ValueError):
                await create_plan("x" * (MAX_GOAL_CHARS + 1))
        chat.assert_not_awaited()

    async def test_returns_validated_plan(self):
        expected = valid_steps()
        with patch("agent.planner.chat", new=AsyncMock(return_value=json.dumps(expected))):
            self.assertEqual(await create_plan("Preparar una auditoría segura"), expected)


if __name__ == "__main__":
    unittest.main()
