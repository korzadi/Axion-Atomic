from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.global_admin import authenticated_admin_user
from api.main import app


def _client_with_role(role):
    app.dependency_overrides[authenticated_admin_user] = lambda: {"id": "support-user"}
    patcher = patch("api.global_admin.global_roles_for_user", return_value=(role,))
    patcher.start()
    return TestClient(app), patcher


def test_global_admin_audit_lists_events_for_audit_reader():
    client, patcher = _client_with_role("billing_support")
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            count_result = MagicMock()
            count_result.scalar_one.return_value = 1
            rows_result = MagicMock()
            rows_result.mappings.return_value.all.return_value = [{
                "id": "event-1", "actor_user_id": "admin-1",
                "target_user_id": "user-2", "action": "role.granted",
                "role": "billing_readonly", "reason": "Acceso de soporte autorizado",
                "created_at": "2026-11-07T12:00:00+00:00",
            }]
            context.execute.side_effect = [count_result, rows_result]
            response = client.get("/admin/audit")
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["total"] == 1
        assert body["events"][0]["action"] == "role.granted"
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_global_admin_audit_bounds_pagination():
    client, patcher = _client_with_role("billing_support")
    try:
        assert client.get("/admin/audit?limit=500").status_code == 422
        assert client.get("/admin/audit?offset=10001").status_code == 422
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_global_admin_audit_denies_user_without_audit_permission():
    client, patcher = _client_with_role("billing_readonly")
    try:
        response = client.get("/admin/audit")
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()
