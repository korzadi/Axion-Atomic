from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api import workspace_routes


def test_workspace_limit_uses_hashed_user_and_project_buckets(monkeypatch):
    calls = []

    def consume(*, engine, bucket_key, limit, window):
        calls.append((bucket_key, limit, window))
        return SimpleNamespace(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(workspace_routes, "consume_rate_limit", consume)
    monkeypatch.setattr(workspace_routes, "engine", object())

    workspace_routes._enforce_workspace_limit(
        "user-123", "project-456", "chat",
        user_limit=20, project_limit=60, window=timedelta(minutes=1),
    )

    assert len(calls) == 2
    assert calls[0][0] != calls[1][0]
    assert all(len(item[0]) == 64 for item in calls)
    assert all("user-123" not in item[0] and "project-456" not in item[0] for item in calls)
    assert [item[1] for item in calls] == [20, 60]


def test_project_limit_bucket_is_shared_by_all_project_members(monkeypatch):
    buckets = []

    def consume(*, engine, bucket_key, limit, window):
        buckets.append(bucket_key)
        return SimpleNamespace(allowed=True, retry_after_seconds=0)

    monkeypatch.setattr(workspace_routes, "consume_rate_limit", consume)
    monkeypatch.setattr(workspace_routes, "engine", object())

    workspace_routes._enforce_workspace_limit(
        "user-a", "shared-project", "chat",
        user_limit=20, project_limit=60, window=timedelta(minutes=1),
    )
    first_user_bucket, first_project_bucket = buckets

    buckets.clear()
    workspace_routes._enforce_workspace_limit(
        "user-b", "shared-project", "chat",
        user_limit=20, project_limit=60, window=timedelta(minutes=1),
    )
    second_user_bucket, second_project_bucket = buckets

    assert first_user_bucket != second_user_bucket
    assert first_project_bucket == second_project_bucket


def test_workspace_limit_returns_429_and_retry_after(monkeypatch):
    decisions = iter([
        SimpleNamespace(allowed=True, retry_after_seconds=0),
        SimpleNamespace(allowed=False, retry_after_seconds=37),
    ])

    monkeypatch.setattr(workspace_routes, "consume_rate_limit", lambda **kwargs: next(decisions))
    monkeypatch.setattr(workspace_routes, "engine", object())

    with pytest.raises(HTTPException) as raised:
        workspace_routes._enforce_workspace_limit(
            "user-123", "project-456", "chat",
            user_limit=20, project_limit=60, window=timedelta(minutes=1),
        )

    assert raised.value.status_code == 429
    assert raised.value.headers["Retry-After"] == "37"


def test_workspace_limit_fails_closed_when_database_is_unavailable(monkeypatch):
    def unavailable(**kwargs):
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(workspace_routes, "consume_rate_limit", unavailable)
    monkeypatch.setattr(workspace_routes, "engine", object())

    with pytest.raises(HTTPException) as raised:
        workspace_routes._enforce_workspace_limit(
            "user-123", "project-456", "chat",
            user_limit=20, project_limit=60, window=timedelta(minutes=1),
        )

    assert raised.value.status_code == 503
    assert "database unavailable" not in str(raised.value.detail)
