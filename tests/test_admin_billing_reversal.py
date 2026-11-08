"""HTTP contracts for the audited reversal of settled billing consumption."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.admin_routes import _admin_csrf
from api.billing_reservations import IdempotencyConflict, ReservationStateError, ReversalResult
from api.global_admin import authenticated_admin_user
from api.main import app


RESERVATION_ID = "11111111-1111-4111-8111-111111111111"
REASON = "Reversión administrativa verificada"
KEY = "reversal-key-1"


def _client_with_role(role):
    app.dependency_overrides[authenticated_admin_user] = lambda: {"id": "admin-user"}
    app.dependency_overrides[_admin_csrf] = lambda: {"id": "admin-user"}
    patcher = patch("api.global_admin.global_roles_for_user", return_value=(role,))
    patcher.start()
    return TestClient(app), patcher


def _engine_with_audit():
    context = MagicMock()
    context.__enter__.return_value = context
    engine = MagicMock()
    engine.begin.return_value = context
    return engine


def _post(client, **overrides):
    payload = {"reservation_id": RESERVATION_ID, "reason": REASON, "idempotency_key": KEY}
    payload.update(overrides)
    return client.post("/admin/billing/reservations/reverse", json=payload)


def test_reversal_requires_billing_manage():
    client, patcher = _client_with_role("billing_readonly")
    try:
        assert _post(client).status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_rejects_invalid_uuid_before_loading_reservation():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner") as load:
            response = _post(client, reservation_id="zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz")
        assert response.status_code == 400
        load.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_returns_not_found_for_unknown_reservation():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner", return_value=None):
            response = _post(client)
        assert response.status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_rejects_non_settled_reservation_without_mutation():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "held")), \
                patch("api.admin_routes.reverse_settled_reservation") as reverse:
            response = _post(client)
        assert response.status_code == 409
        reverse.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_rejects_key_with_spaces_without_mutation():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch("api.admin_routes.reverse_settled_reservation") as reverse:
            response = _post(client, idempotency_key="reversal key")
        assert response.status_code == 400
        reverse.assert_not_called()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_applies_compensating_entries_and_audits():
    client, patcher = _client_with_role("platform_admin")
    try:
        reverse_result = ReversalResult(RESERVATION_ID, "settled", 7)
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch("api.admin_routes.reverse_settled_reservation", return_value=reverse_result) as reverse, \
                patch("api.admin_routes.engine", _engine_with_audit()) as engine:
            response = _post(client)
        assert response.status_code == 200
        body = response.json()
        assert body["reversed_credits"] == 7
        assert body["idempotent"] is False
        assert body["audited"] is True
        assert reverse.call_args.kwargs["reservation_id"] == RESERVATION_ID
        assert reverse.call_args.kwargs["actor_user_id"] == "admin-user"
        engine.begin.assert_called_once()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_is_idempotent_for_same_key():
    client, patcher = _client_with_role("platform_admin")
    try:
        reverse_result = ReversalResult(RESERVATION_ID, "settled", 7, True)
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch("api.admin_routes.reverse_settled_reservation", return_value=reverse_result), \
                patch("api.admin_routes.engine", _engine_with_audit()):
            response = _post(client)
        assert response.status_code == 200
        assert response.json()["idempotent"] is True
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_maps_conflicting_key_to_409():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch(
                    "api.admin_routes.reverse_settled_reservation",
                    side_effect=IdempotencyConflict("conflict"),
                ):
            response = _post(client)
        assert response.status_code == 409
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_maps_state_error_to_409():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch(
                    "api.admin_routes.reverse_settled_reservation",
                    side_effect=ReservationStateError("state"),
                ):
            response = _post(client)
        assert response.status_code == 409
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reversal_reports_partial_audit_failure_for_idempotent_retry():
    client, patcher = _client_with_role("platform_admin")
    try:
        reverse_result = ReversalResult(RESERVATION_ID, "settled", 7)
        engine = MagicMock()
        engine.begin.side_effect = RuntimeError("audit unavailable")
        with patch("api.admin_routes._load_reservation_owner", return_value=("user-1", "settled")), \
                patch("api.admin_routes.reverse_settled_reservation", return_value=reverse_result), \
                patch("api.admin_routes.engine", engine):
            response = _post(client)
        assert response.status_code == 503
        assert "misma clave idempotente" in response.json()["detail"]
    finally:
        patcher.stop()
        app.dependency_overrides.clear()
