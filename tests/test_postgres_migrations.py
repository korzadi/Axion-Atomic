"""Smoke tests del esquema PostgreSQL creado por las migraciones versionadas.

Se ejecutan en el job postgres-migrations de CI contra un PostgreSQL efímero.
No contienen datos de producción ni conectan con servicios externos.
"""
import os

import pytest
from sqlalchemy import create_engine, inspect, text


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    pytest.skip("DATABASE_URL no configurado: requiere el job PostgreSQL de CI", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True)


def test_all_expected_migrations_are_registered():
    with engine.connect() as conn:
        versions = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all()
    assert versions == ["001", "002", "003", "004", "005"]


def test_core_postgresql_tables_exist():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "projects",
        "users",
        "user_sessions",
        "project_memberships",
        "rag_files",
        "rag_chunks",
        "project_memories",
        "action_approvals",
        "audit_log",
        "audit_chain_head",
        "agent_runs",
        "agent_run_actions",
    }
    assert expected <= tables


def test_identity_constraints_and_relationships_exist():
    inspector = inspect(engine)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"id", "email_normalized", "password_hash", "status"} <= user_columns

    user_uniques = inspector.get_unique_constraints("users")
    assert any("email_normalized" in item.get("column_names", []) for item in user_uniques)

    session_fks = inspector.get_foreign_keys("user_sessions")
    assert any(
        item.get("referred_table") == "users"
        and item.get("constrained_columns") == ["user_id"]
        for item in session_fks
    )

    membership_fks = inspector.get_foreign_keys("project_memberships")
    assert any(item.get("referred_table") == "users" for item in membership_fks)
    assert any(item.get("referred_table") == "projects" for item in membership_fks)


def test_project_execution_and_audit_indexes_exist():
    inspector = inspect(engine)

    run_indexes = {item["name"] for item in inspector.get_indexes("agent_runs")}
    assert "idx_agent_runs_project_updated" in run_indexes
    assert "idx_agent_runs_project_status" in run_indexes

    audit_indexes = {item["name"] for item in inspector.get_indexes("audit_log")}
    assert "idx_audit_log_project" in audit_indexes

    with engine.connect() as conn:
        audit_head = conn.execute(
            text("SELECT id, last_hash, seq FROM audit_chain_head WHERE id = 1")
        ).one()
    assert audit_head.id == 1
    assert audit_head.last_hash == ""
    assert audit_head.seq == 0


def test_membership_role_check_is_present():
    inspector = inspect(engine)
    checks = inspector.get_check_constraints("project_memberships")
    definitions = " ".join(item.get("sqltext", "") for item in checks)
    assert "owner" in definitions
    assert "viewer" in definitions
