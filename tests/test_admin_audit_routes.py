from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.admin_routes import _admin_csrf
from api.global_admin import authenticated_admin_user
from api.main import app


def _client_with_role(role):
    app.dependency_overrides[authenticated_admin_user] = lambda: {"id": "admin-user"}
    app.dependency_overrides[_admin_csrf] = lambda: {"id": "admin-user"}
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
        assert response.json()["pagination"]["total"] == 1
        assert response.json()["events"][0]["action"] == "role.granted"
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


def test_admin_user_list_returns_real_account_fields_without_credentials():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            count_result = MagicMock()
            count_result.scalar_one.return_value = 1
            rows_result = MagicMock()
            rows_result.mappings.return_value.all.return_value = [{
                "id": "u-1", "email": "person@example.com",
                "display_name": "Example", "status": "active",
                "email_verified_at": None, "created_at": "2026-01-01T00:00:00Z",
                "last_login_at": None,
            }]
            context.execute.side_effect = [count_result, rows_result]
            response = client.get("/admin/users")
        assert response.status_code == 200
        body = response.json()
        assert body["users"][0]["email"] == "person@example.com"
        assert "password_hash" not in body["users"][0]
        assert body["pagination"]["total"] == 1
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_user_list_is_not_available_to_billing_support():
    client, patcher = _client_with_role("billing_support")
    try:
        response = client.get("/admin/users")
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_user_list_validates_search_and_pagination():
    client, patcher = _client_with_role("platform_admin")
    try:
        assert client.get("/admin/users?limit=500").status_code == 422
        assert client.get("/admin/users?q=").status_code == 422
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_overview_reads_persisted_aggregates():
    client, patcher = _client_with_role("billing_readonly")
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            reservations = MagicMock()
            reservations.mappings.return_value.all.return_value = [
                {"state": "settled", "count": 3, "credits": 120}
            ]
            ledger = MagicMock()
            ledger.mappings.return_value.all.return_value = [
                {"event_type": "consume", "count": 3, "available_delta": 0,
                 "reserved_delta": -120, "consumed_delta": 120}
            ]
            executions = MagicMock()
            executions.mappings.return_value.all.return_value = [
                {"state": "completed", "count": 3, "requires_review": 0,
                 "recovery_due": 0}
            ]
            context.execute.side_effect = [reservations, ledger, executions]
            response = client.get("/admin/billing/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["reservations"][0]["credits"] == 120
        assert body["ledger"][0]["consumed_delta"] == 120
        assert body["executions"][0]["count"] == 3
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_overview_requires_billing_read_permission():
    client, patcher = _client_with_role("unassigned_role")
    try:
        assert client.get("/admin/billing/overview").status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_overview_reads_persisted_aggregates():
    client, patcher = _client_with_role("billing_support")
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            results = []
            for row in (
                [{"state": "held", "count": 2, "credits": 40}],
                [{"event_type": "consume", "count": 1, "available_delta": 0,
                  "reserved_delta": -10, "consumed_delta": 10}],
                [{"state": "completed", "count": 1, "requires_review": 0, "recovery_due": 0}],
            ):
                result = MagicMock()
                result.mappings.return_value.all.return_value = row
                results.append(result)
            context.execute.side_effect = results
            response = client.get("/admin/billing/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["reservations"][0]["credits"] == 40
        assert body["ledger"][0]["event_type"] == "consume"
        assert body["executions"][0]["state"] == "completed"
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_overview_denies_role_without_billing_permission():
    client, patcher = _client_with_role("unknown_role")
    try:
        response = client.get("/admin/billing/overview")
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()

def test_admin_billing_executions_returns_paginated_persisted_details():
    client, patcher = _client_with_role("billing_readonly")
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            count_result = MagicMock()
            count_result.scalar_one.return_value = 1
            rows_result = MagicMock()
            rows_result.mappings.return_value.all.return_value = [{
                "id": "exec-1", "user_id": "user-1", "reservation_id": "res-1",
                "state": "completed", "reservation_state": "settled",
                "requested_credits": 25, "recovery_attempts": 1,
                "recovery_next_attempt_at": None, "recovery_last_attempt_at": None,
                "recovery_last_error_code": None, "recovery_requires_review": False,
                "recovery_settled_at": "2026-11-07T12:00:00Z",
                "created_at": "2026-11-07T11:00:00Z",
                "updated_at": "2026-11-07T12:00:00Z",
                "completed_at": "2026-11-07T11:30:00Z",
            }]
            context.execute.side_effect = [count_result, rows_result]
            response = client.get("/admin/billing/executions?limit=10&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["total"] == 1
        assert body["executions"][0]["requested_credits"] == 25
        assert body["executions"][0]["recovery_attempts"] == 1
        assert "result_ciphertext" not in body["executions"][0]
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_executions_requires_billing_read_permission():
    client, patcher = _client_with_role("unknown_role")
    try:
        # La autorización se resuelve antes que la validación de query: un rol
        # desconocido nunca debe distinguir parámetros válidos de inválidos.
        assert client.get("/admin/billing/executions").status_code == 404
        assert client.get("/admin/billing/executions?limit=500").status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_executions_bounds_pagination_for_authorized_role():
    client, patcher = _client_with_role("billing_readonly")
    try:
        assert client.get("/admin/billing/executions?limit=500").status_code == 422
        assert client.get("/admin/billing/executions?offset=-1").status_code == 422
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_recovery_requires_billing_manage_permission():
    client, patcher = _client_with_role("billing_readonly")
    try:
        response = client.post("/admin/billing/executions/recover")
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_recovery_validates_reservation_id_before_side_effects():
    client, patcher = _client_with_role("billing_admin")
    try:
        with patch("api.admin_routes.EnvironmentResultKeyProvider") as provider:
            response = client.post("/admin/billing/executions/recover?reservation_id=not-a-uuid")
        assert response.status_code == 400
        provider.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_recovery_fails_closed_without_encryption_key():
    from api.billing_result_crypto import ResultEncryptionError

    client, patcher = _client_with_role("billing_admin")
    try:
        with (
            patch("api.admin_routes.EnvironmentResultKeyProvider.active_key",
                  side_effect=ResultEncryptionError("not configured")),
            patch("api.admin_routes.engine.begin") as begin,
        ):
            response = client.post("/admin/billing/executions/recover")
        assert response.status_code == 503
        begin.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_recovery_settles_completed_results_and_audits_attempt():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    batch = SimpleNamespace(
        examined=1, settled=1, review=0, failed=0, skipped=0,
        items=(SimpleNamespace(
            reservation_id="00000000-0000-0000-0000-000000000001",
            state="settled", charged_credits=12, detail="liquidación confirmada",
        ),),
    )
    client, patcher = _client_with_role("billing_admin")
    try:
        with (
            patch("api.admin_routes.EnvironmentResultKeyProvider.active_key",
                  return_value=("billing-v1", b"x" * 32)),
            patch("api.admin_routes.AesGcmResultCipher"),
            patch("api.admin_routes.run_in_threadpool", new=AsyncMock(return_value=batch)),
            patch("api.admin_routes.engine.begin") as begin,
            patch("api.admin_routes.recover_completed_billing_executions") as recovery,
        ):
            context = MagicMock()
            context.__enter__.return_value = context
            begin.return_value = context
            response = client.post(
                "/admin/billing/executions/recover?limit=10&reason=Conciliación manual autorizada"
            )
        assert response.status_code == 200
        body = response.json()
        assert body["settled"] == 1
        assert body["items"][0]["charged_credits"] == 12
        params = context.execute.call_args.args[1]
        assert params["actor_user_id"] == "admin-user"
        assert params["reason"] == "Conciliación manual autorizada"
        assert "INSERT INTO global_admin_audit_events" in context.execute.call_args.args[0].text
        assert recovery is not None
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_billing_recovery_requires_csrf_for_authorized_operator():
    app.dependency_overrides[authenticated_admin_user] = lambda: {"id": "admin-user"}
    with patch("api.global_admin.global_roles_for_user", return_value=("billing_admin",)):
        try:
            response = TestClient(app).post("/admin/billing/executions/recover")
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 403


def test_admin_reconcile_no_execution_requires_billing_manage_permission():
    client, patcher = _client_with_role("billing_readonly")
    try:
        response = client.post(
            "/admin/billing/reservations/reconcile-no-execution",
            json={
                "reservation_id": "00000000-0000-0000-0000-000000000001",
                "reason": "Confirmado que la inferencia no se ejecutó",
                "idempotency_key": "reconcile-1",
            },
        )
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_reconcile_no_execution_requires_csrf():
    app.dependency_overrides[authenticated_admin_user] = lambda: {"id": "admin-user"}
    with patch("api.global_admin.global_roles_for_user", return_value=("billing_admin",)):
        try:
            response = TestClient(app).post(
                "/admin/billing/reservations/reconcile-no-execution",
                json={
                    "reservation_id": "00000000-0000-0000-0000-000000000001",
                    "reason": "Confirmado que la inferencia no se ejecutó",
                    "idempotency_key": "reconcile-1",
                },
            )
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 403


def test_admin_reconcile_no_execution_returns_conflict_for_held_reservation():
    from unittest.mock import AsyncMock

    client, patcher = _client_with_role("billing_admin")
    try:
        with (
            patch("api.admin_routes.run_in_threadpool", new=AsyncMock(return_value=("user-1", "held"))),
            patch("api.admin_routes.reconcile_confirmed_no_execution") as reconcile,
        ):
            response = client.post(
                "/admin/billing/reservations/reconcile-no-execution",
                json={
                    "reservation_id": "00000000-0000-0000-0000-000000000001",
                    "reason": "Confirmado que la inferencia no se ejecutó",
                    "idempotency_key": "reconcile-1",
                },
            )
        assert response.status_code == 409
        reconcile.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_reconcile_no_execution_returns_not_found():
    from unittest.mock import AsyncMock

    client, patcher = _client_with_role("billing_admin")
    try:
        with patch("api.admin_routes.run_in_threadpool", new=AsyncMock(return_value=None)):
            response = client.post(
                "/admin/billing/reservations/reconcile-no-execution",
                json={
                    "reservation_id": "00000000-0000-0000-0000-000000000001",
                    "reason": "Confirmado que la inferencia no se ejecutó",
                    "idempotency_key": "reconcile-1",
                },
            )
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_admin_reconcile_no_execution_releases_unknown_reservation_and_audits():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    reconciled = SimpleNamespace(
        reservation_id="00000000-0000-0000-0000-000000000001",
        state="released",
        idempotent=False,
    )
    client, patcher = _client_with_role("billing_admin")
    try:
        with (
            patch(
                "api.admin_routes.run_in_threadpool",
                new=AsyncMock(side_effect=[("user-1", "unknown"), reconciled]),
            ) as run,
            patch("api.admin_routes.reconcile_confirmed_no_execution") as reconcile,
            patch("api.admin_routes.engine.begin") as begin,
        ):
            context = MagicMock()
            context.__enter__.return_value = context
            begin.return_value = context
            response = client.post(
                "/admin/billing/reservations/reconcile-no-execution",
                json={
                    "reservation_id": "00000000-0000-0000-0000-000000000001",
                    "reason": "Confirmado que la inferencia no se ejecutó",
                    "idempotency_key": "reconcile-1",
                },
            )
        assert response.status_code == 200
        assert response.json()["state"] == "released"
        assert response.json()["audited"] is True
        reconcile_kwargs = run.await_args_list[1].kwargs
        assert reconcile_kwargs["user_id"] == "user-1"
        assert reconcile_kwargs["actor_user_id"] == "admin-user"
        audit_params = context.execute.call_args.args[1]
        assert audit_params["target_user_id"] == "user-1"
        assert audit_params["reason"] == "Confirmado que la inferencia no se ejecutó"
        assert "billing.reservation.reconcile_no_execution" in context.execute.call_args.args[0].text
        assert reconcile is not None
    finally:
        patcher.stop()
        app.dependency_overrides.clear()
