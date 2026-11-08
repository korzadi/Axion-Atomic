"""Pruebas HTTP de reconciliación humana de acciones interrumpidas del agente."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from agent.run_store import RunStoreError
from api.schemas import AgentReconcileRequest
from api.workspace_routes import (
    _reconcile_agent_action,
    workspace_reconcile_agent_run,
)

HASH = "a" * 64


def request(resolution="applied"):
    return AgentReconcileRequest(
        action_hash=HASH,
        resolution=resolution,
        note="Verificado manualmente en el workspace",
    )


class AgentReconcileSchemaTests(unittest.TestCase):
    def test_rejects_non_sha256_hash(self):
        with self.assertRaises(ValidationError):
            AgentReconcileRequest(
                action_hash="z" * 64, resolution="applied",
                note="Verificado manualmente",
            )

    def test_rejects_short_or_blank_note(self):
        for note in ("corto", "        "):
            with self.subTest(note=note):
                with self.assertRaises(ValidationError):
                    AgentReconcileRequest(
                        action_hash=HASH, resolution="applied", note=note,
                    )


class WorkspaceAgentReconciliationHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_reconciles_interrupted_action_without_executing_it(self):
        with (
            patch("api.workspace_routes._project_role") as role,
            patch("api.workspace_routes._enforce_workspace_limit") as limit,
            patch("api.workspace_routes._reconcile_agent_action", return_value="ok") as reconcile,
        ):
            result = await workspace_reconcile_agent_run(
                "run-1", request(), project_id="project-a", user={"id": "owner-1"}
            )

        role.assert_called_once_with(
            {"id": "owner-1"}, "project-a", ("owner", "admin")
        )
        limit.assert_called_once()
        reconcile.assert_called_once()
        self.assertEqual(reconcile.call_args.args, (
            "run-1", "project-a", HASH, "applied",
            "Verificado manualmente en el workspace", "owner-1",
        ))
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(result["next_action"], "resume")
        self.assertTrue(result["audited"])

    async def test_non_member_is_rejected_before_rate_limit_and_reconciliation(self):
        with (
            patch(
                "api.workspace_routes._project_role",
                side_effect=HTTPException(status_code=404, detail="Proyecto no encontrado"),
            ),
            patch("api.workspace_routes._enforce_workspace_limit") as limit,
            patch("api.workspace_routes._reconcile_agent_action") as reconcile,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_reconcile_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "outsider"}
                )

        self.assertEqual(raised.exception.status_code, 404)
        limit.assert_not_called()
        reconcile.assert_not_called()

    async def test_editor_cannot_reconcile(self):
        with (
            patch(
                "api.workspace_routes._project_role",
                side_effect=HTTPException(status_code=404, detail="Proyecto no encontrado"),
            ),
            patch("api.workspace_routes._reconcile_agent_action") as reconcile,
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_reconcile_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "editor-1"}
                )

        self.assertEqual(raised.exception.status_code, 404)
        reconcile.assert_not_called()

    async def test_outcomes_map_to_explicit_http_errors(self):
        cases = {
            "run_not_found": 404,
            "action_not_found": 404,
            "not_reconcilable": 409,
            "action_not_running": 409,
        }
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
        ):
            for outcome, expected in cases.items():
                with self.subTest(outcome=outcome):
                    with patch("api.workspace_routes._reconcile_agent_action", return_value=outcome):
                        with self.assertRaises(HTTPException) as raised:
                            await workspace_reconcile_agent_run(
                                "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                            )
                    self.assertEqual(raised.exception.status_code, expected)

    async def test_concurrent_change_returns_409(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch(
                "api.workspace_routes._reconcile_agent_action",
                side_effect=RunStoreError("La acción cambió durante la reconciliación"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_reconcile_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertNotIn("RunStoreError", raised.exception.detail)

    async def test_atomic_failure_returns_503(self):
        with (
            patch("api.workspace_routes._project_role"),
            patch("api.workspace_routes._enforce_workspace_limit"),
            patch(
                "api.workspace_routes._reconcile_agent_action",
                side_effect=RuntimeError("audit chain conflict"),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await workspace_reconcile_agent_run(
                    "run-1", request(), project_id="project-a", user={"id": "owner-1"}
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("audit chain conflict", raised.exception.detail)

    async def test_route_requires_csrf_dependency(self):
        import inspect

        user = inspect.signature(workspace_reconcile_agent_run).parameters["user"].default
        self.assertEqual(user.dependency.__name__, "_csrf_user")


class ReconcileActionStoreTests(unittest.TestCase):
    def _transaction(self, rows):
        conn = MagicMock()
        conn.execute.side_effect = rows
        transaction = MagicMock()
        transaction.__enter__.return_value = conn
        return transaction, conn

    @staticmethod
    def _successful_rows():
        return [
            MagicMock(first=MagicMock(return_value=("needs_reconciliation",))),
            MagicMock(first=MagicMock(return_value=("running",))),
            MagicMock(rowcount=1),
            MagicMock(rowcount=1),
            MagicMock(first=MagicMock(return_value=(0, ""))),
            MagicMock(rowcount=1),
            MagicMock(),
        ]

    def test_applied_action_run_and_audit_are_updated_in_one_transaction(self):
        transaction, conn = self._transaction(self._successful_rows())
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _reconcile_agent_action(
                "run-1", "project-a", HASH, "applied",
                "Verificado manualmente", "owner-1",
            )

        self.assertEqual(outcome, "ok")
        self.assertEqual(conn.execute.call_count, 7)
        self.assertEqual(
            conn.execute.call_args_list[2].args[1],
            {
                "resolution": "applied",
                "note": "Verificado manualmente",
                "run_id": "run-1",
                "project_id": "project-a",
                "action_hash": HASH,
            },
        )
        self.assertIn("status='awaiting_approval'", str(conn.execute.call_args_list[3].args[0]))
        audit_insert = conn.execute.call_args_list[6]
        self.assertIn("INSERT INTO audit_log", str(audit_insert.args[0]))
        self.assertEqual(audit_insert.args[1]["actor"], "owner-1")
        self.assertEqual(audit_insert.args[1]["event"], "agent.action.reconcile")
        transaction.__exit__.assert_called_once()
        self.assertIsNone(transaction.__exit__.call_args.args[0])

    def test_run_update_conflict_rolls_back_the_transaction(self):
        rows = self._successful_rows()
        rows[3] = MagicMock(rowcount=0)
        transaction, _conn = self._transaction(rows)
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            with self.assertRaisesRegex(RunStoreError, "cambió durante la reconciliación"):
                _reconcile_agent_action(
                    "run-1", "project-a", HASH, "applied",
                    "Verificado manualmente", "owner-1",
                )

        self.assertIsNotNone(transaction.__exit__.call_args.args[0])

    def test_only_running_actions_can_be_reconciled(self):
        transaction, conn = self._transaction([
            MagicMock(first=MagicMock(return_value=("needs_reconciliation",))),
            MagicMock(first=MagicMock(return_value=("applied",))),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            outcome = _reconcile_agent_action(
                "run-1", "project-a", HASH, "failed",
                "Verificado manualmente", "owner-1",
            )

        self.assertEqual(outcome, "action_not_running")
        self.assertEqual(conn.execute.call_count, 2)

    def test_audit_chain_conflict_rolls_back_the_transaction(self):
        transaction, _conn = self._transaction([
            MagicMock(first=MagicMock(return_value=("needs_reconciliation",))),
            MagicMock(first=MagicMock(return_value=("running",))),
            MagicMock(rowcount=1),
            MagicMock(rowcount=1),
            MagicMock(first=MagicMock(return_value=(0, ""))),
            MagicMock(rowcount=0),
        ])
        with patch("api.workspace_routes.engine.begin", return_value=transaction):
            with self.assertRaisesRegex(RuntimeError, "cadena de auditoría"):
                _reconcile_agent_action(
                    "run-1", "project-a", HASH, "applied",
                    "Verificado manualmente", "owner-1",
                )

        self.assertIsNotNone(transaction.__exit__.call_args.args[0])

    def test_invalid_resolution_is_rejected_before_database_access(self):
        with patch("api.workspace_routes.engine.begin") as begin:
            with self.assertRaisesRegex(ValueError, "Resolución"):
                _reconcile_agent_action(
                    "run-1", "project-a", HASH, "done",
                    "Verificado manualmente", "owner-1",
                )
        begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
