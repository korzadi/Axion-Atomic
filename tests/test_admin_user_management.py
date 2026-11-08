"""Contratos de gestión administrativa de usuarios, roles y estado.

Se usa un engine simulado: el objetivo es verificar autorización, validación,
atomicidad del orden de escrituras y auditoría sin depender de PostgreSQL.
"""
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.admin_routes import _admin_csrf
from api.global_admin import authenticated_admin_user
from api.main import app


REASON = "Motivo administrativo verificado"


def _result(*, first=None, mappings_first=None, scalar=None, rowcount=1):
    result = MagicMock()
    result.first.return_value = first
    result.scalar_one.return_value = scalar
    result.rowcount = rowcount
    mappings = MagicMock()
    mappings.first.return_value = mappings_first
    mappings.all.return_value = mappings_first if isinstance(mappings_first, list) else []
    result.mappings.return_value = mappings
    return result


class AdminUserManagementTests(unittest.TestCase):
    def setUp(self):
        self.role = "platform_admin"
        self.actor = "admin-actor"
        app.dependency_overrides[authenticated_admin_user] = lambda: {"id": self.actor}
        app.dependency_overrides[_admin_csrf] = lambda: {"id": self.actor}
        self.roles_patch = patch(
            "api.global_admin.global_roles_for_user",
            side_effect=lambda _user_id: (self.role,),
        )
        self.roles_patch.start()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.roles_patch.stop()

    def _engine(self, connection):
        context = MagicMock()
        context.__enter__.return_value = connection
        engine = MagicMock()
        engine.begin.return_value = context
        engine.connect.return_value.__enter__.return_value = connection
        return engine

    def _post_role(self, role="billing_readonly", reason=REASON, user_id="user-1"):
        return self.client.post(
            f"/admin/users/{user_id}/roles",
            json={"role": role, "reason": reason},
        )

    def test_grant_requires_users_manage(self):
        self.role = "billing_support"
        response = self._post_role()
        self.assertEqual(response.status_code, 404)

    def test_grant_rejects_unknown_role_without_database_write(self):
        with patch("api.admin_routes.engine") as engine:
            response = self._post_role(role="root")
        self.assertEqual(response.status_code, 422)
        engine.begin.assert_not_called()

    def test_grant_returns_conflict_when_role_is_already_active(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(first=(1,)),
            _result(rowcount=0),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self._post_role()
        self.assertEqual(response.status_code, 409)

    def test_grant_writes_assignment_and_audit_in_one_transaction(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(first=(1,)),
            _result(rowcount=1),
            _result(),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self._post_role(role="billing_readonly")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "granted")
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertIn("INSERT INTO global_role_assignments", statements[1])
        self.assertIn("INSERT INTO global_admin_audit_events", statements[2])
        audit_params = connection.execute.call_args_list[2].args[1]
        self.assertEqual(audit_params["action"], "role.granted")
        self.assertEqual(audit_params["role"], "billing_readonly")
        self.assertEqual(audit_params["actor_user_id"], self.actor)

    def test_revoke_blocks_removing_last_active_platform_admin(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(first=("assignment-1",)),
            _result(scalar=0),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.request(
                "DELETE",
                "/admin/users/user-1/roles/platform_admin",
                json={"role": "platform_admin", "reason": REASON},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(connection.execute.call_count, 2)

    def test_revoke_records_audit_after_success(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(first=("assignment-1",)),
            _result(),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.request(
                "DELETE",
                "/admin/users/user-1/roles/billing_readonly",
                json={"role": "billing_readonly", "reason": REASON},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "revoked")
        audit_params = connection.execute.call_args_list[1].args[1]
        self.assertEqual(audit_params["action"], "role.revoked")

    def test_status_rejects_self_disable(self):
        connection = MagicMock()
        connection.execute.side_effect = [_result(mappings_first={"status": "active"})]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.post(
                f"/admin/users/{self.actor}/status",
                json={"status": "disabled", "reason": REASON},
            )
        self.assertEqual(response.status_code, 409)

    def test_status_disable_revokes_sessions_and_audits(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(mappings_first={"status": "active"}),
            _result(scalar=1),
            _result(first=None),
            _result(),
            _result(),
            _result(),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.post(
                "/admin/users/user-1/status",
                json={"status": "disabled", "reason": REASON},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "disabled")
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertTrue(any("UPDATE user_sessions" in statement for statement in statements))
        audit_params = connection.execute.call_args_list[-1].args[1]
        self.assertEqual(audit_params["action"], "user.disabled")

    def test_status_cannot_activate_account_without_verified_email(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(mappings_first={"status": "pending_verification", "email_verified_at": None}),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.post(
                "/admin/users/user-1/status",
                json={"status": "active", "reason": REASON},
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("sin correo verificado", response.json()["detail"])
        self.assertEqual(connection.execute.call_count, 1)

    def test_status_activates_verified_account_and_audits(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(mappings_first={
                "status": "disabled",
                "email_verified_at": "2026-11-01T10:00:00+00:00",
            }),
            _result(),
            _result(),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.post(
                "/admin/users/user-1/status",
                json={"status": "active", "reason": REASON},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")
        audit_params = connection.execute.call_args_list[-1].args[1]
        self.assertEqual(audit_params["action"], "user.active")
        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertFalse(any("UPDATE user_sessions" in statement for statement in statements))

    def test_status_rejects_unknown_value(self):
        with patch("api.admin_routes.engine") as engine:
            response = self.client.post(
                "/admin/users/user-1/status",
                json={"status": "owner", "reason": REASON},
            )
        self.assertEqual(response.status_code, 422)
        engine.begin.assert_not_called()

    def test_roles_read_requires_users_read(self):
        self.role = "billing_readonly"
        response = self.client.get("/admin/users/user-1/roles")
        self.assertEqual(response.status_code, 404)

    def test_roles_read_returns_active_and_historical_assignments(self):
        connection = MagicMock()
        connection.execute.side_effect = [
            _result(first=(1,)),
            _result(mappings_first=[
                {
                    "role": "billing_readonly",
                    "granted_by": "admin-1",
                    "grant_reason": REASON,
                    "granted_at": "2026-11-08T10:00:00+00:00",
                    "revoked_by": None,
                    "revoke_reason": None,
                    "revoked_at": None,
                },
                {
                    "role": "billing_support",
                    "granted_by": "admin-1",
                    "grant_reason": REASON,
                    "granted_at": "2026-11-01T10:00:00+00:00",
                    "revoked_by": "admin-2",
                    "revoke_reason": "Cambio de funciones",
                    "revoked_at": "2026-11-07T10:00:00+00:00",
                },
            ]),
        ]
        with patch("api.admin_routes.engine", self._engine(connection)):
            response = self.client.get("/admin/users/user-1/roles")
        self.assertEqual(response.status_code, 200)
        assignments = response.json()["assignments"]
        self.assertEqual(len(assignments), 2)
        self.assertTrue(assignments[0]["active"])
        self.assertFalse(assignments[1]["active"])
        self.assertNotIn("password_hash", response.text)


if __name__ == "__main__":
    unittest.main()
