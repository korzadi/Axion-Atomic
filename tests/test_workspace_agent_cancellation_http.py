"""Pruebas HTTP de cancelación explícita de ejecuciones pendientes del agente."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from agent.run_store import RunStoreError
from api.schemas import AgentCancelRequest
from api.workspace_routes import _cancel_agent_run, workspace_cancel_agent_run

NOTE = "Cancelada antes de aplicar la acción"


def request():
    return AgentCancelRequest(note=NOTE)


class AgentCancelSchemaTests(unittest.TestCase):
    def test_rejects_short_or_blank_note(self):
        for note in ("corto", "        "):
            with self.subTest(note=note):
                with self.assertRaises(ValidationError):
                    AgentCancelRequest(note=note)


class WorkspaceAgentCancellationHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_cancels_pending_run(self):
        with (
            patch("api.workspace_routes._project_role") as role,
            patch("api.workspace_routes._enforce_workspace_limit") as limit,
            patch("api.workspace_routes._cancel_agent_run", return_value="ok") as cancel,
        ):
            result = await workspace_cancel_agent_run(
                "run-1", request(), project_id="project-a", user={"id": "owner-1"}
            )

        role.assert_called_once_with({"id": "owner-1"}, "project-a", ("owner", "admin"))
        limit.assert_called_once()
        cancel.assert_called_once_with("run-1", "project-a", NOTE, "owner-1")
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(result["next_action"])
        self.assertTrue(result["audited"])

    async def test_non_member_is_rejected_before_rate_limit_and_cancellation(self):
        with (
            patch(
                "api.workspace_routes._project_role",
                side_effect=HTTPException(status_code=404, detail="Proyecto no encontrado"),
            ),
            patch("api.workspace_routes._enforce_workspace_limit") as limit,
            patch("api.workspace_routes._cancel_agent_run") as cancel,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_cancel_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "outsider"}
                )

        self.assertEqual(raised.exception.status_code, 404)
        limit.assert_not_called()
        cancel.assert_not_called()

    async def test_editor_cannot_cancel(self):
        with (
            patch(
                "api.workspace_routes._project_role",
                side_effect=HTTPException(status_code=404, detail="Proyecto no encontrado"),
            ),
            patch("api.workspace_routes._cancel_agent_run") as cancel,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_cancel_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "editor-1"}
                )

        self.assertEqual(raised.exception.status_code, 404)
        cancel.assert_not_called()

    async def test_outcomes_map_to_explicit_http_errors(self):
        cases = {
            "run_not_found": 404,
            "not_cancellable": 409,
            "invalid_state": 409,
        }
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
        ):
            for outcome, expected in cases.items():
                with self.subTest(outcome=outcome):
                    with patch("api.workspace_routes._cancel_agent_run", return_value=outcome):
                        with self.assertRaises(HTTPException) as raised:
                            await workspace_cancel_agent_run(
                                "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                            )
                    self.assertEqual(raised.exception.status_code, expected)

    async def test_concurrent_change_returns_409(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch(
                "api.workspace_routes._cancel_agent_run",
                side_effect=RunStoreError("La ejecución cambió durante la cancelación"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_cancel_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertNotIn("RunStoreError", raised.exception.detail)

    async def test_atomic_failure_returns_503(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch(
                "api.workspace_routes._cancel_agent_run",
                side_effect=RuntimeError("audit chain conflict"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_cancel_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("audit chain conflict", raised.exception.detail)

    async def test_route_requires_csrf_dependency(self):
        import inspect

        user = inspect.signature(workspace_cancel_agent_run).parameters["user"].default
        self.assertEqual(user.dependency.__name__, "_csrf_user")


class CancelAgentRunStoreTests(unittest.TestCase):
    def _transaction(self, rows):
        conn = MagicMock()
        conn.execute.side_effect = rows
        transaction = MagicMock()
        transaction.__enter__.return_value = conn
        return transaction, conn

    @staticmethod
    def _successful_rows():
        return [
            MagicMock(first=MagicMock(return_value=(
                "awaiting_approval", '[{"proposal_id": "p1"}]',
            ))),
            MagicMock(first=MagicMock(return_value=("p1",))),
            MagicMock(all=MagicMock(return_value=[("approved",)])),
            MagicMock(rowcount=1),
            MagicMock(rowcount=1),
            MagicMock(rowcount=1),
            MagicMock(first=MagicMock(return_value=(0, ""))),
            MagicMock(rowcount=1),
            MagicMock(),
        ]

    def test_pending_approvals_and_actions_are_invalidated_in_one_transaction(self):
        transaction, conn = self._transaction(self._successful_rows())
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertEqual(outcome, "ok")
        self.assertEqual(conn.execute.call_count, 9)
        approval_lock = conn.execute.call_args_list[1]
        self.assertIn("FOR UPDATE", str(approval_lock.args[0]))
        action_lock = conn.execute.call_args_list[2]
        self.assertIn("agent_run_actions", str(action_lock.args[0]))
        approval_update = conn.execute.call_args_list[3]
        self.assertIn("UPDATE action_approvals", str(approval_update.args[0]))
        self.assertEqual(approval_update.args[1]["proposal_id"], "p1")
        self.assertEqual(approval_update.args[1]["reviewer"], "owner-1")
        action_update = conn.execute.call_args_list[4]
        self.assertIn("state='expired'", str(action_update.args[0]))
        run_update = conn.execute.call_args_list[5]
        self.assertIn("status='cancelled'", str(run_update.args[0]))
        self.assertEqual(run_update.args[1]["error"], f"Cancelada por el usuario: {NOTE}")
        audit_insert = conn.execute.call_args_list[8]
        self.assertIn("INSERT INTO audit_log", str(audit_insert.args[0]))
        self.assertEqual(audit_insert.args[1]["event"], "agent.run.cancel")
        transaction.__exit__.assert_called_once()
        self.assertIsNone(transaction.__exit__.call_args.args[0])

    def test_missing_run_is_not_found(self):
        transaction, conn = self._transaction([
            MagicMock(first=MagicMock(return_value=None)),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertEqual(outcome, "run_not_found")
        self.assertEqual(conn.execute.call_count, 1)

    def test_only_awaiting_approval_can_be_cancelled(self):
        transaction, conn = self._transaction([
            MagicMock(first=MagicMock(return_value=("running", "[]"))),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertEqual(outcome, "not_cancellable")
        self.assertEqual(conn.execute.call_count, 1)

    def test_malformed_pending_actions_are_rejected(self):
        transaction, conn = self._transaction([
            MagicMock(first=MagicMock(return_value=("awaiting_approval", "{invalid"))),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertEqual(outcome, "invalid_state")
        self.assertEqual(conn.execute.call_count, 1)

    def test_running_action_prevents_cancellation(self):
        transaction, conn = self._transaction([
            MagicMock(first=MagicMock(return_value=("awaiting_approval", "[]"))),
            MagicMock(all=MagicMock(return_value=[("running",)])),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertEqual(outcome, "not_cancellable")
        self.assertEqual(conn.execute.call_count, 2)
        self.assertIsNone(transaction.__exit__.call_args.args[0])

    def test_concurrent_change_rolls_back_and_is_a_conflict(self):
        rows = self._successful_rows()
        rows[5] = MagicMock(rowcount=0)
        transaction, _conn = self._transaction(rows)
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            with self.assertRaisesRegex(RunStoreError, "cambió durante la cancelación"):
                _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertIsNotNone(transaction.__exit__.call_args.args[0])

    def test_audit_chain_conflict_rolls_back_the_transaction(self):
        rows = self._successful_rows()
        rows[7] = MagicMock(rowcount=0)
        transaction, _conn = self._transaction(rows)
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            with self.assertRaisesRegex(RuntimeError, "cadena de auditoría"):
                _cancel_agent_run("run-1", "project-a", NOTE, "owner-1")

        self.assertIsNotNone(transaction.__exit__.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
