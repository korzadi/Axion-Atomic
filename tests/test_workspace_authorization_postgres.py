"""Regresiones de autorización multi-proyecto contra PostgreSQL real de CI.

Este módulo solo se ejecuta en el job postgres-migrations, después de aplicar
las migraciones a una base efímera. Los registros creados usan IDs únicos y se
eliminan en finally; nunca apunta a datos de producción.
"""
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from unittest.mock import patch


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere DATABASE_URL PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True)


def test_project_authorization_isolated_between_real_postgres_projects():
    suffix = uuid.uuid4().hex
    user_a = f"authz-user-a-{suffix}"
    user_b = f"authz-user-b-{suffix}"
    project_a = f"authz-project-a-{suffix}"
    project_b = f"authz-project-b-{suffix}"

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users
                    (id, email, email_normalized, password_hash, display_name, status)
                VALUES
                    (:user_a, :email_a, :normalized_a, 'ci-hash', 'AuthZ A', 'active'),
                    (:user_b, :email_b, :normalized_b, 'ci-hash', 'AuthZ B', 'active')
            """), {
                "user_a": user_a,
                "email_a": f"{user_a}@example.invalid",
                "normalized_a": f"{user_a}@example.invalid",
                "user_b": user_b,
                "email_b": f"{user_b}@example.invalid",
                "normalized_b": f"{user_b}@example.invalid",
            })
            conn.execute(text("""
                INSERT INTO projects (id, name)
                VALUES (:project_a, 'AuthZ project A'), (:project_b, 'AuthZ project B')
            """), {"project_a": project_a, "project_b": project_b})
            conn.execute(text("""
                INSERT INTO project_memberships (id, project_id, user_id, role, created_by)
                VALUES
                    (:membership_a, :project_a, :user_a, 'owner', :user_a),
                    (:membership_b, :project_b, :user_b, 'owner', :user_b)
            """), {
                "membership_a": f"membership-a-{suffix}",
                "project_a": project_a,
                "user_a": user_a,
                "membership_b": f"membership-b-{suffix}",
                "project_b": project_b,
                "user_b": user_b,
            })

        # Usa el motor PostgreSQL del job para probar la misma consulta de producción.
        with patch("api.auth.engine", engine):
            from api.auth import authorize_project

            assert authorize_project(user_a, project_a, ("owner", "admin", "editor", "viewer")) == "owner"

            with pytest.raises(HTTPException) as not_member:
                authorize_project(user_a, project_b, ("owner", "admin", "editor", "viewer"))
            assert not_member.value.status_code == 404
            assert not_member.value.detail == "Proyecto no encontrado"

            with pytest.raises(HTTPException) as insufficient_role:
                authorize_project(user_a, project_a, ("admin", "editor"))
            assert insufficient_role.value.status_code == 404
            assert insufficient_role.value.detail == "Proyecto no encontrado"
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM projects WHERE id IN (:a, :b)"),
                         {"a": project_a, "b": project_b})
            conn.execute(text("DELETE FROM users WHERE id IN (:a, :b)"),
                         {"a": user_a, "b": user_b})
