"""Orquestación durable: reserva -> claim único -> inferencia -> ciphertext -> settlement.

El caller aporta serialización estable y AesGcmResultCipher conectado a un
proveedor externo de claves. Nunca se repite una inferencia con claim existente.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy.engine import Engine

from api.billing_budget import InferenceBudget
from api.billing_policy import UsageUnavailable, credits_for_usage
from api.billing_reservations import (
    ReservationResult,
    SettlementResult,
    mark_reservation_unknown,
    reserve_credits,
    settle_reservation,
)
from api.billing_result_crypto import EncryptedResult
from api.billing_execution_store import (
    ExecutionStoreError,
    claim_execution,
    load_encrypted_result,
    mark_execution_unknown,
    persist_encrypted_result,
)


class DurableExecutionRecoveryRequired(RuntimeError):
    """Una ejecución iniciada o incierta necesita conciliación; no se reejecuta."""


class DurableUsageReviewRequired(RuntimeError):
    """La medición requiere revisión; el resultado cifrado queda conservado."""


@dataclass(frozen=True)
class DurableBillingExecutionResult:
    inference: object
    reservation: ReservationResult
    settlement: SettlementResult
    recovered: bool
    execution_id: str


async def execute_durable_reserved_inference(
    *,
    engine: Engine,
    user_id: str,
    project_id: str | None,
    request_id: str,
    idempotency_key: str,
    payload_sha256: str,
    budget: InferenceBudget,
    expected_runtime_model: str,
    inference_call: Callable,
    reservation_expires_at: datetime,
    cipher,
    serialize_result: Callable[[object], bytes],
    deserialize_result: Callable[[bytes], object],
    purchased_fallback_allowed: bool = False,
) -> DurableBillingExecutionResult:
    """Recupera resultados completed y liquida sin repetir inferencia."""
    if budget.runtime_model != expected_runtime_model or budget.reserved_credits <= 0:
        raise ValueError("Presupuesto/runtime inválido")
    reservation = await asyncio.to_thread(
        reserve_credits, engine=engine, user_id=user_id, project_id=project_id,
        request_id=request_id, idempotency_key=idempotency_key,
        payload_sha256=payload_sha256, required_credits=budget.reserved_credits,
        policy_version=budget.policy_version,
        purchased_fallback_allowed=purchased_fallback_allowed,
        expires_at=reservation_expires_at,
    )
    claim = await asyncio.to_thread(
        claim_execution, engine=engine, user_id=user_id,
        reservation_id=reservation.reservation_id,
    )

    recovered = not claim.claimed
    if recovered:
        if claim.state != "completed":
            raise DurableExecutionRecoveryRequired(
                f"Ejecución existente en estado {claim.state}; no se repetirá la inferencia"
            )
        encrypted = await asyncio.to_thread(
            load_encrypted_result, engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id,
        )
        if encrypted is None or encrypted.execution_id != claim.execution_id:
            raise ExecutionStoreError("No existe resultado cifrado íntegro para la ejecución completada")
        plaintext = cipher.decrypt(
            EncryptedResult(
                ciphertext=encrypted.ciphertext,
                nonce=encrypted.nonce,
                key_id=encrypted.key_id,
            ),
            user_id=user_id, reservation_id=reservation.reservation_id,
            execution_id=claim.execution_id,
        )
        result = deserialize_result(plaintext)
    else:
        try:
            result = await inference_call()
            if (
                getattr(result, "requested_model", None) != expected_runtime_model
                or getattr(result, "returned_model", None) != expected_runtime_model
                or getattr(result, "done", None) is not True
                or getattr(result, "usage_source", None) != "ollama_response"
            ):
                raise UsageUnavailable("Respuesta de inferencia no verificable")
            plaintext = serialize_result(result)
            encrypted = cipher.encrypt(
                plaintext, user_id=user_id, reservation_id=reservation.reservation_id,
                execution_id=claim.execution_id,
            )
            await asyncio.to_thread(
                persist_encrypted_result, engine=engine, user_id=user_id,
                execution_id=claim.execution_id, ciphertext=encrypted.ciphertext,
                nonce=encrypted.nonce, key_id=encrypted.key_id,
            )
        except BaseException:
            # Si persistencia tuvo éxito y una excepción posterior ocurre,
            # no se marca unknown a ciegas; un retry verá el estado completed.
            execution_marked_unknown = False
            try:
                await asyncio.to_thread(
                    mark_execution_unknown, engine=engine, user_id=user_id,
                    execution_id=claim.execution_id,
                )
                execution_marked_unknown = True
            except Exception:
                # Si el commit de persistencia fue exitoso pero la respuesta DB
                # se perdió, el estado completed debe permanecer recuperable.
                pass
            if execution_marked_unknown:
                try:
                    await asyncio.to_thread(
                        mark_reservation_unknown, engine=engine, user_id=user_id,
                        reservation_id=reservation.reservation_id,
                    )
                except Exception:
                    pass
            raise

    if (
        getattr(result, "requested_model", None) != expected_runtime_model
        or getattr(result, "returned_model", None) != expected_runtime_model
        or getattr(result, "done", None) is not True
        or getattr(result, "usage_source", None) != "ollama_response"
    ):
        raise UsageUnavailable("Resultado recuperado no cumple el contrato de inferencia")
    actual = credits_for_usage(
        getattr(result, "prompt_eval_count", None),
        getattr(result, "eval_count", None),
        input_weight=budget.input_weight, output_weight=budget.output_weight,
    )
    settlement = await asyncio.to_thread(
        settle_reservation, engine=engine, user_id=user_id,
        reservation_id=reservation.reservation_id, actual_credits=actual,
    )
    if settlement.state != "settled":
        raise DurableUsageReviewRequired(
            "Consumo superior a la reserva o estado de revisión; resultado cifrado conservado"
        )
    return DurableBillingExecutionResult(
        inference=result, reservation=reservation, settlement=settlement,
        recovered=recovered, execution_id=claim.execution_id,
    )
