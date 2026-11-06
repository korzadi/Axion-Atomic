"""Orquestación segura de reserva -> inferencia -> liquidación.

No está conectada a rutas HTTP. El caller debe autenticar al usuario, autorizar
el proyecto, construir el presupuesto sobre el prompt FINAL y aportar una clave
idempotente y un hash del payload. Los reintentos nunca repiten una inferencia
cuando ya existe una reserva con esa clave.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.engine import Engine

from api.billing_budget import InferenceBudget
from api.billing_policy import UsageUnavailable, credits_for_usage
from api.billing_reservations import (
    ReservationResult,
    ReservationStateError,
    SettlementResult,
    mark_reservation_unknown,
    reserve_credits,
    settle_reservation,
)


class DuplicateExecution(ReservationStateError):
    """La clave ya tiene una reserva; se prohíbe repetir la inferencia."""


class UsageReviewRequired(ReservationStateError):
    """La medición excedió la reserva y requiere revisión antes de responder."""


class ModelExecutionMismatch(ReservationStateError):
    """La inferencia no corresponde al modelo runtime reservado."""


@dataclass(frozen=True)
class BillingExecutionResult:
    inference: object
    reservation: ReservationResult
    settlement: SettlementResult


async def execute_reserved_inference(
    *,
    engine: Engine,
    user_id: str,
    project_id: str | None,
    request_id: str,
    idempotency_key: str,
    payload_sha256: str,
    budget: InferenceBudget,
    expected_runtime_model: str,
    inference_call,
    reservation_expires_at: datetime,
    purchased_fallback_allowed: bool = False,
) -> BillingExecutionResult:
    """Reserva primero; ejecuta una sola vez; liquida solo con medición válida."""
    if budget.runtime_model != expected_runtime_model:
        raise ValueError("El presupuesto no corresponde al runtime autorizado")
    if budget.reserved_credits <= 0:
        raise ValueError("La reserva debe ser positiva")
    reservation = await asyncio.to_thread(
        reserve_credits,
        engine=engine,
        user_id=user_id,
        project_id=project_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        payload_sha256=payload_sha256,
        required_credits=budget.reserved_credits,
        policy_version=budget.policy_version,
        purchased_fallback_allowed=purchased_fallback_allowed,
        expires_at=reservation_expires_at,
    )
    if reservation.idempotent:
        # No hay un registro de resultado recuperable en esta capa todavía.
        # Repetir la llamada al modelo podría duplicar consumo/cargos.
        raise DuplicateExecution("La petición ya fue reservada; recuperar su resultado o conciliarla")

    try:
        result = await inference_call()
    except BaseException:
        # Incluye cancelación/timeout: el motor podría haber procesado la petición.
        await asyncio.to_thread(
            mark_reservation_unknown,
            engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id,
        )
        raise

    if (
        getattr(result, "requested_model", None) != expected_runtime_model
        or getattr(result, "returned_model", None) != expected_runtime_model
        or getattr(result, "done", None) is not True
    ):
        await asyncio.to_thread(
            mark_reservation_unknown,
            engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id,
        )
        raise ModelExecutionMismatch("Modelo o estado de ejecución no verificable; reserva retenida")

    if getattr(result, "usage_source", None) != "ollama_response":
        await asyncio.to_thread(
            mark_reservation_unknown,
            engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id,
        )
        raise UsageUnavailable("Ollama no proporcionó contadores verificables; reserva retenida")

    try:
        actual_credits = credits_for_usage(
            getattr(result, "prompt_eval_count", None),
            getattr(result, "eval_count", None),
            input_weight=budget.input_weight,
            output_weight=budget.output_weight,
        )
    except (UsageUnavailable, ValueError):
        await asyncio.to_thread(
            mark_reservation_unknown,
            engine=engine, user_id=user_id,
            reservation_id=reservation.reservation_id,
        )
        raise

    settlement = await asyncio.to_thread(
        settle_reservation,
        engine=engine, user_id=user_id,
        reservation_id=reservation.reservation_id,
        actual_credits=actual_credits,
    )
    if settlement.state != "settled":
        raise UsageReviewRequired("El consumo superó la reserva; respuesta retenida para revisión")
    return BillingExecutionResult(result, reservation, settlement)
