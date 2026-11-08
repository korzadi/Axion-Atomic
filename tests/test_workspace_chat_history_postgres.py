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
