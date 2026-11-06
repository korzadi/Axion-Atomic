"""Operaciones de proyectos con propiedad asignada transaccionalmente."""
import secrets

from sqlalchemy import text

from api.database import engine


def create_owned_project(user_id: str, name: str) -> dict:
    clean_name = name.strip()
    if not user_id or len(clean_name) < 2 or len(clean_name) > 120:
        raise ValueError("Datos del proyecto no válidos")
    project_id = secrets.token_urlsafe(24)
    membership_id = secrets.token_urlsafe(24)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
            {"id": project_id, "name": clean_name},
        )
        conn.execute(
            text("INSERT INTO project_memberships (id, project_id, user_id, role, created_by) "
                 "VALUES (:id, :project_id, :user_id, 'owner', :created_by)"),
            {"id": membership_id, "project_id": project_id, "user_id": user_id, "created_by": user_id},
        )
    return {"id": project_id, "name": clean_name, "role": "owner"}


def list_user_projects(user_id: str, limit: int = 100) -> list[dict]:
    if not user_id:
        raise ValueError("user_id is required")
    bounded_limit = max(1, min(int(limit), 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT p.id, p.name, p.created_at, m.role "
                 "FROM projects p JOIN project_memberships m ON m.project_id=p.id "
                 "WHERE m.user_id=:user_id ORDER BY p.created_at DESC LIMIT :limit"),
            {"user_id": user_id, "limit": bounded_limit},
        ).mappings().all()
    return [dict(row) for row in rows]
