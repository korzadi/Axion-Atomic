"""HTTP contracts for the audited admin-triggered QvaPay reconciliation."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.admin_routes import _admin_csrf
from api.global_admin import authenticated_admin_user
from api.main import app
from api.qvapay_lightning import QvaPayLightningTransportError
from api.qvapay_settlement import ReconciliationResult


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


def _settings(*, enabled=True, token="test-token"):
    mock_settings = MagicMock()
    mock_settings.qvapay_enabled = enabled
    mock_settings.qvapay_user_token = SecretStr(token) if token is not None else None
    mock_settings.qvapay_lightning_address = "axyronatomic@qvpay.me"
    mock_settings.qvapay_request_timeout_seconds = 5.0
    return mock_settings


def _post(client, **params):
    return client.post("/admin/billing/qvapay/reconcile", params=params)


def test_reconcile_requires_billing_manage():
    client, patcher = _client_with_role("billing_readonly")
    try:
        assert _post(client).status_code == 404
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reconcile_fails_closed_when_qvapay_disabled():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes.settings", _settings(enabled=False)), \
                patch("api.admin_routes.fetch_recent_payments", new=AsyncMock(side_effect=AssertionError("no debe llamarse"))):
            response = _post(client)
        assert response.status_code == 503
        assert "desactivada" in response.json()["detail"]
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reconcile_fails_closed_when_token_missing():
    client, patcher = _client_with_role("platform_admin")
    try:
        with patch("api.admin_routes.settings", _settings(enabled=True, token=None)), \
                patch("api.admin_routes.fetch_recent_payments", new=AsyncMock(side_effect=AssertionError("no debe llamarse"))):
            response = _post(client)
        assert response.status_code == 503
        assert "token" in response.json()["detail"].lower()
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reconcile_audits_before_external_call_and_hides_error():
    client, patcher = _client_with_role("billing_admin")
    try:
        engine = _engine_with_audit()
        failing_fetch = AsyncMock(side_effect=QvaPayLightningTransportError("detalle interno con token"))
        with patch("api.admin_routes.settings", _settings()), \
                patch("api.admin_routes.engine", engine), \
                patch("api.admin_routes.fetch_recent_payments", new=failing_fetch):
            response = _post(client)
        assert response.status_code == 503
        assert "token" not in response.json()["detail"]
        engine.begin.assert_called_once()
        audit_sql = engine.begin.return_value.__enter__.return_value.execute.call_args
        assert "billing.qvapay.reconcile" in str(audit_sql)
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reconcile_returns_outcome_summary_without_payment_details():
    client, patcher = _client_with_role("platform_admin")
    try:
        engine = _engine_with_audit()
        results = [
            ReconciliationResult("order-1", "axyref1", "confirmed", "tx-1", 2100),
            ReconciliationResult("order-2", "axyref2", "unmatched", None, None),
            ReconciliationResult("order-3", "axyref3", "confirmed", "tx-2", 4200),
        ]

        async def fake_threadpool(func, **kwargs):
            return results

        with patch("api.admin_routes.settings", _settings()), \
                patch("api.admin_routes.engine", engine), \
                patch("api.admin_routes.fetch_recent_payments", new=AsyncMock(return_value=[MagicMock(), MagicMock()])), \
                patch("api.admin_routes.run_in_threadpool", new=fake_threadpool):
            response = _post(client)
        assert response.status_code == 200
        body = response.json()
        assert body["examined_open_invoices"] == 3
        assert body["payments_fetched"] == 2
        assert body["outcomes"] == {"confirmed": 2, "unmatched": 1}
        assert body["audited"] is True
        for item in body["items"]:
            assert set(item) == {"order_id", "outcome"}
    finally:
        patcher.stop()
        app.dependency_overrides.clear()


def test_reconcile_rejects_invalid_max_pages():
    client, patcher = _client_with_role("platform_admin")
    try:
        assert _post(client, max_pages=0).status_code == 422
        assert _post(client, max_pages=99).status_code == 422
    finally:
        patcher.stop()
        app.dependency_overrides.clear()
