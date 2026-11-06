"""Operaciones PostgreSQL transaccionales de reservas y liquidación de créditos.

Este módulo no se conecta a rutas HTTP ni habilita cobros. Requiere migraciones
007/008 aplicadas y solo debe invocarse después de verificar identidad y
autorización del proyecto en la capa superior.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from api.billing_policy import InsufficientCredits


class IdempotencyConflict(ValueError):
    """La misma clave se reutilizó con un payload diferente."""


class ReservationNotFound(LookupError):
    """No existe la reserva para el usuario indicado."""


class ReservationStateError(ValueError):
    """La reserva no está en un estado que permita esta operación."""


@dataclass(frozen=True)
class ReservationResult:
    reservation_id: str
    state: str
    requested_credits: int
    idempotent: bool = False


@dataclass(frozen=True)
class SettlementResult:
    reservation_id: str
    state: str
    charged_credits: int | None
    idempotent: bool = False


def _aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} debe incluir zona horaria")
    return value.astimezone(timezone.utc)


def reserve_credits(
    *,
    engine: Engine,
    user_id: str,
    project_id: str | None,
    request_id: str,
    idempotency_key: str,
    payload_sha256: str,
    required_credits: int,
    policy_version: str,
    purchased_fallback_allowed: bool = False,
    expires_at: datetime,
    now: datetime | None = None,
) -> ReservationResult:
    """Reserva cuotas y lotes en una transacción; prioriza cuota diaria y FEFO."""
    if not user_id or not idempotency_key or len(idempotency_key) > 200:
        raise ValueError("Identidad y clave idempotente son obligatorias")
    if isinstance(required_credits, bool) or not isinstance(required_credits, int) or required_credits <= 0:
        raise ValueError("required_credits debe ser un entero positivo")
    if len(payload_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in payload_sha256):
        raise ValueError("payload_sha256 debe ser SHA-256 hexadecimal")
    if not policy_version:
        raise ValueError("policy_version es obligatoria")
    instant = _aware(now or datetime.now(timezone.utc), "now")
    expiry = _aware(expires_at, "expires_at")
    if expiry <= instant:
        raise ValueError("expires_at debe ser posterior a now")
    # Normaliza y valida UUID antes de abrir la transacción.
    request_uuid = str(uuid.UUID(request_id))
    reservation_uuid = str(uuid.uuid4())

    with engine.begin() as conn:
        # Serializa intentos con la misma clave incluso antes de insertar la reserva.
        lock_key = f"axion-billing:{user_id}:{idempotency_key}"
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        existing = conn.execute(text("""
            SELECT id, state, requested_credits, payload_sha256
            FROM billing_usage_reservations
            WHERE user_id=:user_id AND idempotency_key=:idempotency_key
            FOR UPDATE
        """), {"user_id": user_id, "idempotency_key": idempotency_key}).mappings().first()
        if existing:
            if existing["payload_sha256"].strip() != payload_sha256:
                raise IdempotencyConflict("La clave idempotente ya pertenece a otra solicitud")
            return ReservationResult(
                str(existing["id"]), existing["state"], existing["requested_credits"], True
            )

        # Bloqueo estable: primero cuotas diarias, luego suscripciones y por ID.
        quota_rows = conn.execute(text("""
            SELECT id, quota_kind, limit_credits, reserved_credits, consumed_credits
            FROM billing_quota_periods
            WHERE user_id=:user_id AND period_start <= :instant AND period_end > :instant
            ORDER BY CASE quota_kind WHEN 'daily_free' THEN 0 ELSE 1 END, period_end, id
            FOR UPDATE
        """), {"user_id": user_id, "instant": instant}).mappings().all()

        remaining = required_credits
        allocations: list[dict] = []
        for row in quota_rows:
            available = row["limit_credits"] - row["reserved_credits"] - row["consumed_credits"]
            amount = min(remaining, max(0, available))
            if amount:
                allocations.append({
                    "source": row["quota_kind"], "amount": amount,
                    "quota_period_id": str(row["id"]), "credit_lot_id": None,
                })
                remaining -= amount
            if not remaining:
                break

        if remaining and purchased_fallback_allowed:
            lot_rows = conn.execute(text("""
                SELECT id, available_credits
                FROM billing_credit_lots
                WHERE user_id=:user_id AND available_credits > 0
                  AND (expires_at IS NULL OR expires_at > :instant)
                ORDER BY expires_at ASC NULLS LAST, created_at, id
                FOR UPDATE
            """), {"user_id": user_id, "instant": instant}).mappings().all()
            for row in lot_rows:
                amount = min(remaining, row["available_credits"])
                if amount:
                    allocations.append({
                        "source": "purchased", "amount": amount,
                        "quota_period_id": None, "credit_lot_id": str(row["id"]),
                    })
                    remaining -= amount
                if not remaining:
                    break
        if remaining:
            raise InsufficientCredits("Cuota y créditos disponibles insuficientes")

        conn.execute(text("""
            INSERT INTO billing_usage_reservations
                (id, user_id, project_id, request_id, idempotency_key, payload_sha256,
                 requested_credits, state, policy_version, created_at, expires_at)
            VALUES
                (CAST(:id AS UUID), :user_id, :project_id, CAST(:request_id AS UUID),
                 :idempotency_key, :payload_sha256, :requested_credits, 'held',
                 :policy_version, :instant, :expires_at)
        """), {
            "id": reservation_uuid, "user_id": user_id, "project_id": project_id,
            "request_id": request_uuid, "idempotency_key": idempotency_key,
            "payload_sha256": payload_sha256, "requested_credits": required_credits,
            "policy_version": policy_version, "instant": instant, "expires_at": expiry,
        })

        for item in allocations:
            allocation_id = str(uuid.uuid4())
            conn.execute(text("""
                INSERT INTO billing_reservation_allocations
                    (id, reservation_id, source, quota_period_id, credit_lot_id, allocated_credits)
                VALUES (CAST(:id AS UUID), CAST(:reservation_id AS UUID), :source,
                        CAST(:quota_period_id AS UUID), CAST(:credit_lot_id AS UUID), :amount)
            """), {
                "id": allocation_id, "reservation_id": reservation_uuid,
                **item, "amount": item["amount"],
            })
            if item["source"] == "purchased":
                conn.execute(text("""
                    UPDATE billing_credit_lots
                    SET available_credits=available_credits-:amount,
                        reserved_credits=reserved_credits+:amount
                    WHERE id=CAST(:lot_id AS UUID)
                """), {"amount": item["amount"], "lot_id": item["credit_lot_id"]})
            else:
                conn.execute(text("""
                    UPDATE billing_quota_periods
                    SET reserved_credits=reserved_credits+:amount
                    WHERE id=CAST(:period_id AS UUID)
                """), {"amount": item["amount"], "period_id": item["quota_period_id"]})

            conn.execute(text("""
                INSERT INTO billing_credit_ledger
                    (id, user_id, credit_lot_id, reservation_id, event_type,
                     available_delta, reserved_delta, consumed_delta,
                     idempotency_key, reason)
                VALUES (CAST(:id AS UUID), :user_id, CAST(:lot_id AS UUID),
                        CAST(:reservation_id AS UUID), 'reserve',
                        :available_delta, :reserved_delta, 0, :ledger_key, :reason)
            """), {
                "id": str(uuid.uuid4()), "user_id": user_id,
                "lot_id": item["credit_lot_id"], "reservation_id": reservation_uuid,
                "available_delta": -item["amount"] if item["source"] == "purchased" else 0,
                "reserved_delta": item["amount"],
                "ledger_key": f"reserve:{reservation_uuid}:{allocation_id}",
                "reason": f"Reserva de consumo ({item['source']})",
            })

    return ReservationResult(reservation_uuid, "held", required_credits)


def settle_reservation(
    *,
    engine: Engine,
    user_id: str,
    reservation_id: str,
    actual_credits: int,
) -> SettlementResult:
    """Liquida uso medido; devuelve exceso reservado y nunca cobra sobre la reserva."""
    if isinstance(actual_credits, bool) or not isinstance(actual_credits, int) or actual_credits < 0:
        raise ValueError("actual_credits debe ser un entero no negativo")
    reservation_uuid = str(uuid.UUID(reservation_id))
    with engine.begin() as conn:
        reservation = conn.execute(text("""
            SELECT id, state, requested_credits
            FROM billing_usage_reservations
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id
            FOR UPDATE
        """), {"id": reservation_uuid, "user_id": user_id}).mappings().first()
        if reservation is None:
            raise ReservationNotFound("Reserva inexistente")
        if reservation["state"] == "settled":
            return SettlementResult(reservation_uuid, "settled", None, True)
        if reservation["state"] != "held":
            raise ReservationStateError(f"No se puede liquidar una reserva en estado {reservation['state']}")
        if actual_credits > reservation["requested_credits"]:
            conn.execute(text("""
                UPDATE billing_usage_reservations SET state='review'
                WHERE id=CAST(:id AS UUID)
            """), {"id": reservation_uuid})
            return SettlementResult(reservation_uuid, "review", None)

        allocations = conn.execute(text("""
            SELECT a.id, a.source, a.quota_period_id, a.credit_lot_id, a.allocated_credits
            FROM billing_reservation_allocations a
            LEFT JOIN billing_quota_periods q ON q.id=a.quota_period_id
            LEFT JOIN billing_credit_lots l ON l.id=a.credit_lot_id
            WHERE a.reservation_id=CAST(:id AS UUID)
            ORDER BY CASE a.source WHEN 'daily_free' THEN 0 WHEN 'subscription' THEN 1 ELSE 2 END,
                     CASE WHEN a.source='purchased' THEN l.expires_at ELSE q.period_end END NULLS LAST,
                     l.created_at NULLS LAST, a.id
            FOR UPDATE OF a
        """), {"id": reservation_uuid}).mappings().all()

        remaining = actual_credits
        for item in allocations:
            used = min(remaining, item["allocated_credits"])
            released = item["allocated_credits"] - used
            remaining -= used
            if item["source"] == "purchased":
                conn.execute(text("""
                    UPDATE billing_credit_lots
                    SET reserved_credits=reserved_credits-:allocated,
                        consumed_credits=consumed_credits+:used,
                        available_credits=available_credits+:released
                    WHERE id=CAST(:lot_id AS UUID)
                """), {
                    "allocated": item["allocated_credits"], "used": used,
                    "released": released, "lot_id": str(item["credit_lot_id"]),
                })
            else:
                conn.execute(text("""
                    UPDATE billing_quota_periods
                    SET reserved_credits=reserved_credits-:allocated,
                        consumed_credits=consumed_credits+:used
                    WHERE id=CAST(:period_id AS UUID)
                """), {
                    "allocated": item["allocated_credits"], "used": used,
                    "period_id": str(item["quota_period_id"]),
                })

            if used:
                conn.execute(text("""
                    INSERT INTO billing_credit_ledger
                        (id, user_id, credit_lot_id, reservation_id, event_type,
                         available_delta, reserved_delta, consumed_delta, idempotency_key, reason)
                    VALUES (CAST(:id AS UUID), :user_id, CAST(:lot_id AS UUID),
                            CAST(:reservation_id AS UUID), 'consume', 0, :delta, :used,
                            :ledger_key, 'Liquidación de uso medido')
                """), {
                    "id": str(uuid.uuid4()), "user_id": user_id,
                    "lot_id": item["credit_lot_id"], "reservation_id": reservation_uuid,
                    "delta": -used, "used": used,
                    "ledger_key": f"consume:{reservation_uuid}:{item['id']}",
                })
            if released:
                conn.execute(text("""
                    INSERT INTO billing_credit_ledger
                        (id, user_id, credit_lot_id, reservation_id, event_type,
                         available_delta, reserved_delta, consumed_delta, idempotency_key, reason)
                    VALUES (CAST(:id AS UUID), :user_id, CAST(:lot_id AS UUID),
                            CAST(:reservation_id AS UUID), 'release', :available, :delta, 0,
                            :ledger_key, 'Liberación de exceso reservado')
                """), {
                    "id": str(uuid.uuid4()), "user_id": user_id,
                    "lot_id": item["credit_lot_id"], "reservation_id": reservation_uuid,
                    "available": released if item["source"] == "purchased" else 0,
                    "delta": -released,
                    "ledger_key": f"release:{reservation_uuid}:{item['id']}",
                })

        if remaining:
            raise RuntimeError("Inconsistencia: asignaciones menores que la reserva")
        conn.execute(text("""
            UPDATE billing_usage_reservations
            SET state='settled', settled_at=now()
            WHERE id=CAST(:id AS UUID)
        """), {"id": reservation_uuid})
    return SettlementResult(reservation_uuid, "settled", actual_credits)


def mark_reservation_unknown(*, engine: Engine, user_id: str, reservation_id: str) -> None:
    """Conserva saldo reservado cuando el resultado del proveedor es incierto."""
    reservation_uuid = str(uuid.UUID(reservation_id))
    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE billing_usage_reservations SET state='unknown'
            WHERE id=CAST(:id AS UUID) AND user_id=:user_id AND state='held'
        """), {"id": reservation_uuid, "user_id": user_id})
        if result.rowcount != 1:
            raise ReservationStateError("La reserva no existe o ya no está en estado held")
