from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.usage_routes import _enabled_user, project_usage


class _Result:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def mappings(self):
        return self

    def one(self):
        return self._one

    def all(self):
        return self._rows


class _Connection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if len(self.calls) == 1:
            return _Result(one={
                "requests": 3,
                "measured_prompt_requests": 2,
                "measured_output_requests": 2,
                "prompt_tokens": 30,
                "output_tokens": 12,
                "unavailable_measurements": 1,
            })
        return _Result(rows=[{
            "request_id": "request-1",
            "requested_model": "atomic-code:16k-8k",
            "returned_model": "atomic-code:16k-8k",
            "prompt_tokens": 20,
            "output_tokens": 8,
            "usage_source": "ollama_response",
            "done": True,
            "observed_at": "2026-11-07T12:00:00Z",
        }])


class _Engine:
    def __init__(self):
        self.connection = _Connection()

    @contextmanager
    def connect(self):
        yield self.connection


def test_auth_disabled_fails_before_session_database_lookup():
    with patch("api.usage_routes.settings.auth_enabled", False):
        with pytest.raises(HTTPException) as error:
            _enabled_user(axion_session=None)
    assert error.value.status_code == 503


def test_usage_endpoint_authorizes_project_and_scopes_queries_to_user():
    engine = _Engine()
    user = {"id": "user-1"}

    with (
        patch("api.usage_routes.authorize_project") as authorize,
        patch("api.usage_routes.engine", engine),
    ):
        response = project_usage(project_id="project-1", limit=25, user=user)

    authorize.assert_called_once_with(
        "user-1", "project-1", ("owner", "admin", "editor", "viewer")
    )
    assert response["totals"]["requests"] == 3
    assert response["totals"]["measured_prompt_requests"] == 2
    assert response["totals"]["unavailable_measurements"] == 1
    assert response["totals"]["prompt_tokens"] == 30
    assert len(response["items"]) == 1
    assert len(engine.connection.calls) == 2
    for statement, params in engine.connection.calls:
        assert "user_id = :user_id AND project_id = :project_id" in statement
        assert params["user_id"] == "user-1"
        assert params["project_id"] == "project-1"
    assert engine.connection.calls[1][1]["limit"] == 25


def test_usage_endpoint_preserves_unknown_token_totals_as_null():
    engine = _Engine()
    engine.connection.execute = lambda statement, params: _Result(
        one={
            "requests": 1,
            "measured_prompt_requests": 0,
            "measured_output_requests": 0,
            "prompt_tokens": None,
            "output_tokens": None,
            "unavailable_measurements": 1,
        }
    ) if "COUNT(*) AS requests" in str(statement) else _Result(rows=[])

    with patch("api.usage_routes.engine", engine):
        response = project_usage(
            project_id="project-1", limit=50, user={"id": "user-1"}
        )

    assert response["totals"]["requests"] == 1
    assert response["totals"]["prompt_tokens"] is None
    assert response["totals"]["output_tokens"] is None
    assert response["totals"]["unavailable_measurements"] == 1


def test_usage_endpoint_does_not_bypass_project_authorization():
    with (
        patch("api.usage_routes.authorize_project", side_effect=HTTPException(404)),
        patch("api.usage_routes.engine") as engine,
    ):
        with pytest.raises(HTTPException) as error:
            project_usage(project_id="other-project", limit=50, user={"id": "user-1"})

    assert error.value.status_code == 404
    engine.connect.assert_not_called()
