from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.global_admin import require_global_permission
from api.main import app


def test_global_admin_audit_requires_audit_read_permission():
    client = TestClient(app)
    dependency = require_global_permission("audit.read")
    app.dependency_overrides[dependency] = lambda: {"id": "support-user"}
    try:
        with patch("api.admin_routes.engine.connect") as connect:
            context = MagicMock()
            context.__enter__.return_value = context
            connect.return_value = context
            context.execute.return_value.scalar_one.return_value = 0
            context.execute.return_value.mappings.return_value.all.return_value = []
            response = client.get("/admin/audit")
        assert response.status_code == 200
        assert response.json()["events"] == []
        assert response.json()["pagination"]["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_global_admin_audit_bounds_pagination():
    client = TestClient(app)
    dependency = require_global_permission("audit.read")
    app.dependency_overrides[dependency] = lambda: {"id": "support-user"}
    try:
        response = client.get("/admin/audit?limit=500")
        assert response.status_code == 422
        response = client.get("/admin/audit?offset=10001")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_global_admin_audit_is_forbidden_without_permission():
    client = TestClient(app)
    dependency = require_global_permission("audit.read")
    app.dependency_overrides[dependency] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=404, detail="Recurso no encontrado")
    )
    try:
        response = client.get("/admin/audit")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
