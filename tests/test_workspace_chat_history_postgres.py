"""Pruebas de aislamiento del historial de chat sobre PostgreSQL real de CI.

Usa exclusivamente la base efímera del job postgres-migrations. Cada prueba
crea identidades/proyectos únicos y elimina sus filas al terminar.
"""
import os
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def test_chat_history_is_isolated_by_both_user_and_project():
    suffix = uuid.uuid4().hex
    user_a, user_b = f"chat-user-a-{suffix}", f"chat-user-b-{suffix}"
    project_a, project_b = f"chat-project-a-{suffix}", f"chat-project-b-{suffix}"

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users
                    (id, email, email_normalized, password_hash, display_name, status)
                VALUES
                    (:user_a, :email_a, :email_a, 'ci-hash', 'Chat A', 'active'),
                    (:user_b, :email_b, :email_b, 'ci-hash', 'Chat B', 'active')
            """), {
                "user_a": user_a,
                "email_a": f"{user_a}@example.invalid",
                "user_b": user_b,
                "email_b": f"{user_b}@example.invalid",
            })
            conn.execute(text("""
                INSERT INTO projects (id, name)
                VALUES (:project_a, 'Chat project A'), (:project_b, 'Chat project B')
            """), {"project_a": project_a, "project_b": project_b})

        from api.workspace_routes import _get_chat_history, _save_chat_history

        messages_a = [{"role": "user", "content": "private user A / project A"}]
        messages_b = [{"role": "user", "content": "private user B / project A"}]
        messages_other_project = [{"role": "assistant", "content": "private user A / project B"}]

        with patch("api.workspace_routes.engine", engine):
            _save_chat_history(user_a, project_a, messages_a)
            _save_chat_history(user_b, project_a, messages_b)
            _save_chat_history(user_a, project_b, messages_other_project)

            assert _get_chat_history(user_a, project_a)["messages"] == messages_a
            assert _get_chat_history(user_b, project_a)["messages"] == messages_b
            assert _get_chat_history(user_a, project_b)["messages"] == messages_other_project

            # An absent user/project pair must never inherit another pair's history.
            assert _get_chat_history(user_b, project_b) == {
                "messages": [],
                "updated_at": None,
            }

            with engine.connect() as conn:
                count = conn.execute(text("""
                    SELECT count(*) FROM workspace_chat_history
                    WHERE project_id IN (:project_a, :project_b)
                      AND user_id IN (:user_a, :user_b)
                """), {
                    "project_a": project_a,
                    "project_b": project_b,
                    "user_a": user_a,
                    "user_b": user_b,
                }).scalar_one()
            assert count == 3
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM projects WHERE id IN (:a, :b)"),
                         {"a": project_a, "b": project_b})
            conn.execute(text("DELETE FROM users WHERE id IN (:a, :b)"),
                         {"a": user_a, "b": user_b})

def test_chat_history_http_route_checks_real_postgres_membership():
    """La ruta HTTP no devuelve el historial a otro usuario del mismo proyecto."""
    import asyncio
    import httpx

    suffix = uuid.uuid4().hex
    user_a, user_b = f"chat-http-a-{suffix}", f"chat-http-b-{suffix}"
    project_id = f"chat-http-project-{suffix}"

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users
                    (id, email, email_normalized, password_hash, display_name, status)
                VALUES
                    (:user_a, :email_a, :email_a, 'ci-hash', 'Chat HTTP A', 'active'),
                    (:user_b, :email_b, :email_b, 'ci-hash', 'Chat HTTP B', 'active')
            """), {
                "user_a": user_a,
                "email_a": f"{user_a}@example.invalid",
                "user_b": user_b,
                "email_b": f"{user_b}@example.invalid",
            })
            conn.execute(text("INSERT INTO projects (id, name) VALUES (:id, 'Chat HTTP project')"),
                         {"id": project_id})
            conn.execute(text("""
                INSERT INTO project_memberships (id, project_id, user_id, role, created_by)
                VALUES (:id, :project_id, :user_id, 'viewer', :user_id)
            """), {
                "id": f"membership-{suffix}",
                "project_id": project_id,
                "user_id": user_a,
            })

        from api.main import app
        from api.workspace_routes import _enabled_user, _save_chat_history

        previous_override = app.dependency_overrides.get(_enabled_user)
        app.dependency_overrides[_enabled_user] = lambda: {"id": user_a}

        async def get_history():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                return await client.get(
                    "/workspace/chat/history",
                    params={"project_id": project_id},
                )

        try:
            with (
                patch("api.auth.engine", engine),
                patch("api.workspace_routes.engine", engine),
                patch("api.workspace_routes._enforce_workspace_limit"),
            ):
                _save_chat_history(
                    user_a,
                    project_id,
                    [{"role": "assistant", "content": "historial privado real"}],
                )
                allowed = asyncio.run(get_history())
                assert allowed.status_code == 200
                assert allowed.json()["messages"] == [
                    {"role": "assistant", "content": "historial privado real"}
                ]

                app.dependency_overrides[_enabled_user] = lambda: {"id": user_b}
                denied = asyncio.run(get_history())
                assert denied.status_code == 404
                assert "historial privado real" not in denied.text
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(_enabled_user, None)
            else:
                app.dependency_overrides[_enabled_user] = previous_override
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM projects WHERE id=:id"), {"id": project_id})
            conn.execute(text("DELETE FROM users WHERE id IN (:a, :b)"),
                         {"a": user_a, "b": user_b})
