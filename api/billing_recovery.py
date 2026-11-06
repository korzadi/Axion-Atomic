"""Recuperación de ejecuciones completadas cuya reserva sigue held.

Este worker nunca invoca Ollama ni vuelve a ejecutar prompts. Solo descifra
resultados AES-GCM persistidos, valida el envelope y reintenta la liquidación.
Los intentos usan una concesión corta y backoff para evitar tormentas de reintentos.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from api.billing_execution_store import load_encrypted_result
from api.billing_execution_envelope import parse_execution_envelope
from api.billing_reservations import SettlementResult, settle_reservation
from api.billing_result_crypto import EncryptedResult


@dataclass(frozen=True)
class BillingRecoveryItem:
    reservation_id: str
    state: str
    charged_credits: int | None
    detail: str


@dataclass(frozen=True)
class BillingRecoveryBatch:
    examined: int
    settled: int
    review: int
    failed: int
    skipped: int
    items: tuple[BillingRecoveryItem, ...]


def _claim_attempt(engine: Engine, execution_id: str) -> int | None:
    """Adquiere atómicamente un intento; otro worker no puede tomar el mismo lease."""
    with engine.begin() as conn:
        row = conn.execute(text("""
            UPDATE billing_inference_executions
            SET recovery_attempts = recovery_attempts + 1,
                recovery_last_attempt_at = now(),
                recovery_next_attempt_at = now() + interval '5 minutes'
            WHERE id = CAST(:id AS UUID)
              AND state = 'completed'
              AND (recovery_next_attempt_at IS NULL OR recovery_next_attempt_at <= now())
            RETURNING recovery_attempts
        """), {"id": execution_id}).first()
    return int(row[0]) if row is not None else None


def _finish_attempt(
    engine: Engine,
    execution_id: str,
    *,
    attempt: int,
    error_code: str | None,
    settled: bool,
) -> None:
    """Marca éxito o programa backoff exponencial limitado a seis horas."""
    if settled:
        statement = text("""
            UPDATE billing_inference_executions
            SET recovery_next_attempt_at = NULL,
                recovery_settled_at = now(),
                recovery_last_error_code = NULL
            WHERE id = CAST(:id AS UUID) AND state = 'completed'
        """)
        params = {"id": execution_id}
    else:
        statement = text("""
            UPDATE billing_inference_executions
            SET recovery_next_attempt_at = CASE
                    WHEN :attempt >= 10 THEN NULL
                    ELSE now() + interval '1 second' *
                         LEAST(30 * power(2, LEAST(:attempt - 1, 10)), 21600)
                END,
                recovery_requires_review = (:attempt >= 10),
                recovery_last_error_code = :error_code
            WHERE id = CAST(:id AS UUID) AND state = 'completed'
        """)
        params = {
            "id": execution_id,
            "attempt": attempt,
            "error_code": (error_code or "RecoveryError")[:128],
        }
    with engine.begin() as conn:
        conn.execute(statement, params)


def recover_completed_billing_executions(
    *,
    engine: Engine,
    cipher,
    limit: int = 100,
    reservation_id: str | None = None,
) -> BillingRecoveryBatch:
    """Liquida resultados cifrados completed/held sin repetir inferencia.

    El escaneo es corto. Un lease de cinco minutos excluye workers concurrentes;
    ante fallo, el intento siguiente usa backoff de 30 s a 6 h. La liquidación
    sigue protegida por FOR UPDATE y es idempotente en PostgreSQL.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit debe estar entre 1 y 1000")

    with engine.connect() as conn:
        candidates = conn.execute(text("""
            SELECT r.id AS reservation_id, r.user_id, r.policy_version,
                   e.id AS execution_id
            FROM billing_usage_reservations r
            JOIN billing_inference_executions e
              ON e.reservation_id = r.id AND e.user_id = r.user_id
            WHERE r.state = 'held' AND e.state = 'completed'
              AND (CAST(:reservation_id AS UUID) IS NULL OR r.id = CAST(:reservation_id AS UUID))
              AND e.recovery_requires_review = FALSE
              AND (e.recovery_next_attempt_at IS NULL
                   OR e.recovery_next_attempt_at <= now())
            ORDER BY e.recovery_next_attempt_at NULLS FIRST, e.completed_at, e.id
            LIMIT :limit
        """), {"limit": limit, "reservation_id": reservation_id}).mappings().all()

    items: list[BillingRecoveryItem] = []
    settled = review = failed = skipped = 0
    examined = 0
    for candidate in candidates:
        reservation_id = str(candidate["reservation_id"])
        execution_id = str(candidate["execution_id"])
        user_id = candidate["user_id"]
        attempt = _claim_attempt(engine, execution_id)
        if attempt is None:
            skipped += 1
            continue
        examined += 1
        try:
            stored = load_encrypted_result(
                engine=engine, user_id=user_id, reservation_id=reservation_id,
            )
            if stored is None or stored.execution_id != execution_id:
                raise ValueError("Resultado cifrado completado no encontrado")
            plaintext = cipher.decrypt(
                EncryptedResult(
                    ciphertext=stored.ciphertext,
                    nonce=stored.nonce,
                    key_id=stored.key_id,
                ),
                user_id=user_id,
                reservation_id=reservation_id,
                execution_id=stored.execution_id,
            )
            envelope = parse_execution_envelope(plaintext)
            if envelope.policy_version != candidate["policy_version"]:
                raise ValueError("La política del envelope no coincide con la reserva")
            result: SettlementResult = settle_reservation(
                engine=engine,
                user_id=user_id,
                reservation_id=reservation_id,
                actual_credits=envelope.credits,
            )
            if result.state == "settled":
                _finish_attempt(
                    engine, execution_id, attempt=attempt,
                    error_code=None, settled=True,
                )
                settled += 1
                items.append(BillingRecoveryItem(
                    reservation_id, result.state, result.charged_credits,
                    "liquidación confirmada",
                ))
            elif result.state == "review":
                _finish_attempt(
                    engine, execution_id, attempt=attempt,
                    error_code="UsageReviewRequired", settled=False,
                )
                review += 1
                items.append(BillingRecoveryItem(
                    reservation_id, result.state, None,
                    "consumo excede la reserva; requiere revisión",
                ))
            else:
                raise ValueError("Estado de liquidación no reconocido")
        except Exception as exc:
            try:
                _finish_attempt(
                    engine, execution_id, attempt=attempt,
                    error_code=type(exc).__name__, settled=False,
                )
            except Exception:
                # El lease expira en cinco minutos si tampoco se puede escribir el backoff.
                pass
            failed += 1
            # No exponemos excepciones, prompts, ciphertext ni datos privados.
            items.append(BillingRecoveryItem(
                reservation_id, "failed", None, type(exc).__name__,
            ))

    return BillingRecoveryBatch(
        examined=examined, settled=settled, review=review,
        failed=failed, skipped=skipped, items=tuple(items),
    )
