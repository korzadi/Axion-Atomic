"""Registro durable de ejecuciones; resultados siempre cifrados por el caller."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ExecutionStoreError(RuntimeError):
    pass


class ExecutionAlreadyClaimed(ExecutionStoreError):
    pass


@dataclass(frozen=True)
class ExecutionClaim:
    execution_id: str
    state: str
    claimed: bool


@dataclass(frozen=True)
class EncryptedExecutionResult:
    execution_id: str
    ciphertext: bytes
    nonce: bytes
    key_id: str
    sha256: str


def claim_execution(*, engine: Engine, user_id: str, reservation_id: str) -> ExecutionClaim:
    """Crea un único derecho de ejecución por reserva held; jamás roba una ejecución."""
    rid = str(uuid.UUID(reservation_id))
    execution_id = str(uuid.uuid4())
    with engine.begin() as conn:
        reservation = conn.execute(text("""
            SELECT id, state FROM billing_usage_reservations
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
            FOR UPDATE
        """), {"id": rid, "user_id": user_id}).mappings().first()
        if reservation is None:
            raise ExecutionStoreError("Reserva inexistente")
        if reservation["state"] != "held":
            raise ExecutionStoreError("Solo una reserva held puede reclamar una ejecución")
        inserted = conn.execute(text("""
            INSERT INTO billing_inference_executions
                (id, reservation_id, user_id, state)
            VALUES (CAST(:id AS UUID), CAST(:reservation_id AS UUID), :user_id, 'started')
            ON CONFLICT (reservation_id) DO NOTHING
        """), {"id": execution_id, "reservation_id": rid, "user_id": user_id})
        row = conn.execute(text("""
            SELECT id, state FROM billing_inference_executions
            WHERE reservation_id=CAST(:reservation_id AS UUID) AND user_id=:user_id
            FOR UPDATE
        """), {"reservation_id": rid, "user_id": user_id}).mappings().one()
        return ExecutionClaim(str(row["id"]), row["state"], inserted.rowcount == 1)


def persist_encrypted_result(
    *, engine: Engine, user_id: str, execution_id: str,
    ciphertext: bytes, nonce: bytes, key_id: str,
) -> EncryptedExecutionResult:
    """Guarda ciphertext autenticable; nunca acepta texto plano ni payload vacío."""
    eid = str(uuid.UUID(execution_id))
    if not isinstance(ciphertext, bytes) or not ciphertext:
        raise ValueError("ciphertext debe ser bytes no vacíos")
    if not isinstance(nonce, bytes) or not nonce:
        raise ValueError("nonce debe ser bytes no vacíos")
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise ValueError("key_id inválido")
    digest = hashlib.sha256(ciphertext).hexdigest()
    with engine.begin() as conn:
        updated = conn.execute(text("""
            UPDATE billing_inference_executions
            SET state='completed', result_ciphertext=:ciphertext, result_nonce=:nonce,
                result_key_id=:key_id, result_sha256=:digest,
                completed_at=:now, updated_at=:now
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id AND state='started'
        """), {
            "ciphertext": ciphertext, "nonce": nonce, "key_id": key_id,
            "digest": digest, "now": datetime.now(timezone.utc),
            "id": eid, "user_id": user_id,
        })
        if updated.rowcount != 1:
            raise ExecutionAlreadyClaimed("La ejecución no está en estado started")
    return EncryptedExecutionResult(eid, ciphertext, nonce, key_id, digest)


def load_encrypted_result(
    *, engine: Engine, user_id: str, reservation_id: str,
) -> EncryptedExecutionResult | None:
    """Recupera solo ciphertext completado; el caller debe verificar y descifrar."""
    rid = str(uuid.UUID(reservation_id))
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT e.id, e.result_ciphertext, e.result_nonce, e.result_key_id,
                   e.result_sha256
            FROM billing_inference_executions e
            WHERE e.reservation_id=CAST(:rid AS UUID) AND e.user_id=:user_id
              AND e.state='completed'
        """), {"rid": rid, "user_id": user_id}).mappings().first()
    if row is None:
        return None
    ciphertext = bytes(row["result_ciphertext"])
    digest = hashlib.sha256(ciphertext).hexdigest()
    if digest != row["result_sha256"].strip():
        raise ExecutionStoreError("La integridad del resultado cifrado no coincide")
    return EncryptedExecutionResult(
        str(row["id"]), ciphertext, bytes(row["result_nonce"]),
        row["result_key_id"], digest,
    )


def mark_execution_unknown(*, engine: Engine, user_id: str, execution_id: str) -> None:
    eid = str(uuid.UUID(execution_id))
    with engine.begin() as conn:
        updated = conn.execute(text("""
            UPDATE billing_inference_executions
            SET state='unknown', updated_at=:now
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
              AND state IN ('started', 'review')
        """), {"id": eid, "user_id": user_id, "now": datetime.now(timezone.utc)})
        if updated.rowcount != 1:
            raise ExecutionAlreadyClaimed("La ejecución no puede pasar a unknown")
