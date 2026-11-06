"""Smoke tests del esquema PostgreSQL creado por las migraciones versionadas.

Se ejecutan en el job postgres-migrations de CI contra un PostgreSQL efímero.
No contienen datos de producción ni conectan con servicios externos.
"""
import os

import pytest
from sqlalchemy import create_engine, inspect, text


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere DATABASE_URL PostgreSQL del job postgres-migrations", allow_module_level=True)

engine = create_engine(DATABASE_URL, future=True)


def test_all_expected_migrations_are_registered():
    with engine.connect() as conn:
        versions = conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all()
    assert versions == ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012"]


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
        "inference_usage_events",
        "billing_quota_periods",
        "billing_credit_lots",
        "billing_usage_reservations",
        "billing_reservation_allocations",
        "billing_credit_ledger",
        "billing_reservation_reconciliations",
        "billing_inference_executions",
        "email_verification_tokens",
        "password_reset_tokens",
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



def test_inference_usage_event_schema_is_durable_and_nullable():
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("inference_usage_events")}
    assert {
        "request_id", "user_id", "project_id", "requested_model", "returned_model",
        "prompt_tokens", "output_tokens", "usage_source", "observed_at",
    } <= set(columns)
    assert columns["prompt_tokens"]["nullable"] is True
    assert columns["output_tokens"]["nullable"] is True

    primary_key = inspector.get_pk_constraint("inference_usage_events")
    assert primary_key["constrained_columns"] == ["request_id"]

    foreign_keys = inspector.get_foreign_keys("inference_usage_events")
    assert any(
        item.get("referred_table") == "users"
        and item.get("constrained_columns") == ["user_id"]
        and item.get("options", {}).get("ondelete") == "RESTRICT"
        for item in foreign_keys
    )
    assert any(
        item.get("referred_table") == "projects"
        and item.get("constrained_columns") == ["project_id"]
        and item.get("options", {}).get("ondelete") == "RESTRICT"
        for item in foreign_keys
    )

    indexes = {item["name"] for item in inspector.get_indexes("inference_usage_events")}
    assert {
        "idx_inference_usage_user_observed",
        "idx_inference_usage_project_observed",
        "idx_inference_usage_model_observed",
    } <= indexes

    with engine.connect() as conn:
        definitions = conn.execute(text("""
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conrelid = 'inference_usage_events'::regclass
        """)).scalars().all()
    joined = " ".join(definitions)
    assert "prompt_tokens" in joined
    assert "output_tokens" in joined
    assert "ollama_response" in joined



def test_billing_reservation_and_ledger_schema_constraints_exist():
    inspector = inspect(engine)
    expected_tables = {
        "billing_quota_periods",
        "billing_credit_lots",
        "billing_usage_reservations",
        "billing_reservation_allocations",
        "billing_credit_ledger",
    }
    assert expected_tables <= set(inspector.get_table_names())

    reservation_columns = {
        item["name"] for item in inspector.get_columns("billing_usage_reservations")
    }
    assert {
        "user_id", "project_id", "request_id", "idempotency_key",
        "payload_sha256", "requested_credits", "state", "policy_version",
    } <= reservation_columns

    reservation_uniques = inspector.get_unique_constraints("billing_usage_reservations")
    assert any(
        set(item.get("column_names", [])) == {"user_id", "idempotency_key"}
        for item in reservation_uniques
    )
    reservation_fks = inspector.get_foreign_keys("billing_usage_reservations")
    assert any(item.get("referred_table") == "users" for item in reservation_fks)
    assert any(item.get("referred_table") == "projects" for item in reservation_fks)

    ledger_columns = {
        item["name"] for item in inspector.get_columns("billing_credit_ledger")
    }
    assert {
        "event_type", "available_delta", "reserved_delta", "consumed_delta",
        "idempotency_key", "related_entry_id", "reason",
    } <= ledger_columns
    ledger_uniques = inspector.get_unique_constraints("billing_credit_ledger")
    assert any(
        "idempotency_key" in item.get("column_names", [])
        for item in ledger_uniques
    )

    lot_indexes = {item["name"] for item in inspector.get_indexes("billing_credit_lots")}
    assert "idx_billing_credit_lots_fefo" in lot_indexes
    reservation_indexes = {
        item["name"] for item in inspector.get_indexes("billing_usage_reservations")
    }
    assert "idx_billing_reservations_recovery" in reservation_indexes



def test_billing_ledger_rejects_update_delete_and_truncate():
    with engine.connect() as conn:
        triggers = conn.execute(text("""
            SELECT tgname
            FROM pg_trigger
            WHERE tgrelid = 'billing_credit_ledger'::regclass
              AND NOT tgisinternal
        """)).scalars().all()
    assert {
        "trg_billing_ledger_no_update_delete",
        "trg_billing_ledger_no_truncate",
    } <= set(triggers)



def test_billing_reconciliation_audit_is_append_only():
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("billing_reservation_reconciliations")}
    assert {
        "reservation_id", "user_id", "actor_user_id", "resolution",
        "idempotency_key", "reason", "created_at",
    } <= columns
    with engine.connect() as conn:
        triggers = conn.execute(text("""
            SELECT tgname
            FROM pg_trigger
            WHERE tgrelid = 'billing_reservation_reconciliations'::regclass
              AND NOT tgisinternal
        """)).scalars().all()
    assert {
        "trg_billing_reconciliations_no_update_delete",
        "trg_billing_reconciliations_no_truncate",
    } <= set(triggers)


def test_billing_execution_results_are_ciphertext_only_and_recoverable():
    inspector = inspect(engine)
    columns = {item["name"]: item for item in inspector.get_columns("billing_inference_executions")}
    assert {
        "reservation_id", "user_id", "state", "result_ciphertext",
        "result_nonce", "result_key_id", "result_sha256", "completed_at",
    } <= set(columns)
    assert columns["result_ciphertext"]["type"].__class__.__name__.lower() == "bytea"
    uniques = inspector.get_unique_constraints("billing_inference_executions")
    assert any(item.get("column_names") == ["reservation_id"] for item in uniques)
    with engine.connect() as conn:
        triggers = conn.execute(text("""
            SELECT tgname FROM pg_trigger
            WHERE tgrelid='billing_inference_executions'::regclass AND NOT tgisinternal
        """)).scalars().all()
    assert not triggers
