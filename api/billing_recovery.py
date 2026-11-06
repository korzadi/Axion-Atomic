"""Recuperación de ejecuciones completadas cuya reserva sigue held.

Este worker nunca invoca Ollama ni vuelve a ejecutar prompts. Solo descifra
resultados AES-GCM persistidos, valida el envelope y reintenta la liquidación.
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
    items: tuple[BillingRecoveryItem, ...]


def recover_completed_billing_executions(
    *,
    engine: Engine,
    cipher,
    limit: int = 100,
) -> BillingRecoveryBatch:
    """Liquida resultados cifrados completed/held sin repetir inferencia.

    El escaneo no toma locks largos. settle_reservation serializa cada reserva
    con FOR UPDATE y es idempotente si otro worker ya la liquidó.
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
            ORDER BY e.completed_at, e.id
            LIMIT :limit
        """), {"limit": limit}).mappings().all()

    items: list[BillingRecoveryItem] = []
    settled = review = failed = 0
    for candidate in candidates:
        reservation_id = str(candidate["reservation_id"])
        user_id = candidate["user_id"]
        try:
            stored = load_encrypted_result(
                engine=engine, user_id=user_id, reservation_id=reservation_id,
            )
            if stored is None or stored.execution_id != str(candidate["execution_id"]):
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
                settled += 1
                items.append(BillingRecoveryItem(
                    reservation_id, result.state, result.charged_credits,
                    "liquidación confirmada",
                ))
            elif result.state == "review":
                review += 1
                items.append(BillingRecoveryItem(
                    reservation_id, result.state, None,
                    "consumo excede la reserva; requiere revisión",
                ))
            else:
                failed += 1
                items.append(BillingRecoveryItem(
                    reservation_id, result.state, result.charged_credits,
                    "estado de liquidación no reconocido",
                ))
        except Exception as exc:
            failed += 1
            # No incluimos texto de excepción, prompts, ciphertext ni datos privados.
            items.append(BillingRecoveryItem(
                reservation_id, "failed", None, type(exc).__name__,
            ))

    return BillingRecoveryBatch(
        examined=len(candidates), settled=settled, review=review,
        failed=failed, items=tuple(items),
    )
