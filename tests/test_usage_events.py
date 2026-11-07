"""Unit tests for append-only shadow usage persistence."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.usage_events import _INSERT_USAGE, persist_shadow_usage_event


class ShadowUsagePersistenceTests(unittest.TestCase):
    def test_insert_is_idempotent_by_request_id(self):
        self.assertIn("ON CONFLICT (request_id) DO NOTHING", str(_INSERT_USAGE))


    def test_persists_provider_counters_without_conversation_content(self):
        connection = MagicMock()
        transaction = MagicMock()
        transaction.__enter__.return_value = connection
        result = SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model="atomic-code:16k-8k",
            prompt_eval_count=17,
            eval_count=9,
            total_duration_ns=100,
            load_duration_ns=10,
            prompt_eval_duration_ns=20,
            eval_duration_ns=30,
            usage_source="ollama_response",
            done=True,
        )

        with patch("api.usage_events.engine.begin", return_value=transaction):
            persist_shadow_usage_event(
                request_id="6a1e8e9a-52a1-45f6-9e19-7c7cb0c1e5a3",
                user_id="user-1",
                project_id="project-1",
                result=result,
            )

        connection.execute.assert_called_once()
        params = connection.execute.call_args.args[1]
        self.assertEqual(params["prompt_tokens"], 17)
        self.assertEqual(params["output_tokens"], 9)
        self.assertEqual(params["user_id"], "user-1")
        self.assertEqual(params["project_id"], "project-1")
        self.assertEqual(params["usage_source"], "ollama_response")
        self.assertNotIn("prompt", params)
        self.assertNotIn("content", params)

    def test_keeps_unavailable_counters_as_null_not_zero(self):
        connection = MagicMock()
        transaction = MagicMock()
        transaction.__enter__.return_value = connection
        result = SimpleNamespace(
            requested_model="atomic-code:16k-8k",
            returned_model=None,
            prompt_eval_count=None,
            eval_count=0,
            total_duration_ns=None,
            load_duration_ns=None,
            prompt_eval_duration_ns=None,
            eval_duration_ns=None,
            usage_source="unavailable",
            done=None,
        )

        with patch("api.usage_events.engine.begin", return_value=transaction):
            persist_shadow_usage_event(
                request_id="6a1e8e9a-52a1-45f6-9e19-7c7cb0c1e5a4",
                user_id="user-1",
                project_id="project-1",
                result=result,
            )

        params = connection.execute.call_args.args[1]
        self.assertIsNone(params["prompt_tokens"])
        self.assertEqual(params["output_tokens"], 0)
        self.assertEqual(params["usage_source"], "unavailable")


    def test_rejects_negative_or_non_integer_provider_counters(self):
        for field, value in (
            ("prompt_eval_count", -1),
            ("eval_count", -1),
            ("total_duration_ns", -1),
            ("load_duration_ns", -1),
            ("prompt_eval_duration_ns", -1),
            ("eval_duration_ns", -1),
            ("prompt_eval_count", True),
            ("eval_count", 1.5),
        ):
            result = SimpleNamespace(
                requested_model="atomic-code:16k-8k",
                returned_model="atomic-code:16k-8k",
                prompt_eval_count=1,
                eval_count=1,
                total_duration_ns=1,
                load_duration_ns=1,
                prompt_eval_duration_ns=1,
                eval_duration_ns=1,
                usage_source="ollama_response",
                done=True,
            )
            setattr(result, field, value)
            with self.subTest(field=field, value=value):
                with patch("api.usage_events.engine.begin") as begin:
                    with self.assertRaises(ValueError):
                        persist_shadow_usage_event(
                            request_id="6a1e8e9a-52a1-45f6-9e19-7c7cb0c1e5a5",
                            user_id="user-1",
                            project_id="project-1",
                            result=result,
                        )
                begin.assert_not_called()

if __name__ == "__main__":
    unittest.main()
