import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.schemas import ChatRequest, Message
from api.workspace_routes import workspace_chat


class WorkspaceChatBillingIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return ChatRequest(
            project_id="project-a",
            messages=[Message(role="user", content="Haz el trabajo")],
            max_tokens=64,
        )

    def inference_result(self):
        return SimpleNamespace(
            content="Trabajo completado",
            requested_model="atomic-code:1.1",
            returned_model="atomic-code:1.1",
            prompt_eval_count=12,
            eval_count=8,
            usage_source="ollama_response",
            total_duration_ns=100,
            load_duration_ns=10,
            prompt_eval_duration_ns=20,
            eval_duration_ns=30,
            done=True,
        )

    async def test_enforced_billing_requires_idempotency_key_before_inference(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="")),
            patch("api.workspace_routes.settings.billing_enforcement_enabled", True),
            patch("api.workspace_routes.chat_with_usage", new=AsyncMock()) as inference,
            patch("api.workspace_routes.EnvironmentResultKeyProvider.active_key") as key_check,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_chat(self.request(), {"id": "user-a"})
        self.assertEqual(caught.exception.status_code, 400)
        key_check.assert_not_called()
        inference.assert_not_awaited()

    async def test_enforced_billing_validates_dedicated_key_before_model_or_reservation(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="")),
            patch("api.workspace_routes.settings.billing_enforcement_enabled", True),
            patch(
                "api.workspace_routes.EnvironmentResultKeyProvider.active_key",
                side_effect=__import__("api.billing_result_crypto", fromlist=["ResultEncryptionError"]).ResultEncryptionError("missing"),
            ),
            patch("api.workspace_routes.execute_durable_reserved_inference", new=AsyncMock()) as execute,
            patch("api.workspace_routes.chat_with_usage", new=AsyncMock()) as inference,
        ):
            with self.assertRaises(HTTPException) as caught:
                await workspace_chat(
                    self.request(), {"id": "user-a"},
                    idempotency_key_header="stable-request-1",
                )
        self.assertEqual(caught.exception.status_code, 503)
        execute.assert_not_awaited()
        inference.assert_not_awaited()

    async def test_enforced_billing_uses_durable_ledger_and_returns_measured_charge(self):
        result = self.inference_result()
        durable = SimpleNamespace(
            inference=result,
            reservation=SimpleNamespace(reservation_id="00000000-0000-0000-0000-000000000001"),
            settlement=SimpleNamespace(state="settled", charged_credits=20),
            recovered=False,
            execution_id="00000000-0000-0000-0000-000000000002",
        )
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch("api.workspace_routes.retrieve", new=AsyncMock(return_value="RAG real")),
            patch("api.workspace_routes.settings.billing_enforcement_enabled", True),
            patch("api.workspace_routes.settings.chat_model", "atomic-code:1.1"),
            patch("api.workspace_routes.EnvironmentResultKeyProvider.active_key", return_value=("billing-v1", b"x" * 32)),
            patch("api.workspace_routes.execute_durable_reserved_inference", new=AsyncMock(return_value=durable)) as execute,
            patch("api.workspace_routes.persist_shadow_usage_event"),
            patch("api.workspace_routes._save_chat_history"),
        ):
            response = await workspace_chat(
                self.request(), {"id": "user-a"},
                idempotency_key_header="stable-request-1",
            )
        self.assertEqual(response["choices"][0]["message"]["content"], "Trabajo completado")
        self.assertEqual(response["usage_billing"]["mode"], "ledger")
        self.assertTrue(response["usage_billing"]["charged"])
        self.assertEqual(response["usage_billing"]["credits_charged"], 20)
        self.assertEqual(response["usage_billing"]["reservation_id"], durable.reservation.reservation_id)
        kwargs = execute.await_args.kwargs
        self.assertEqual(kwargs["idempotency_key"], "stable-request-1")
        self.assertEqual(
            kwargs["budget"].reserved_credits,
            kwargs["budget"].input_tokens_upper_bound + kwargs["budget"].output_tokens_upper_bound,
        )
        self.assertEqual(kwargs["expected_runtime_model"], "atomic-code:1.1")


if __name__ == "__main__":
    unittest.main()
