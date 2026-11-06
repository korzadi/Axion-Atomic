"""Pure billing allocation policy; no database writes or balance mutation.

This module computes a deterministic allocation proposal only. PostgreSQL
reservations, row locks, ledger postings and settlement are implemented
separately before any real billing can be enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


class UsageUnavailable(ValueError):
    """A final charge cannot be computed from missing provider counters."""


class InsufficientCredits(ValueError):
    """Included quota and permitted purchased credits cannot cover the request."""


@dataclass(frozen=True)
class CreditLot:
    lot_id: str
    available: int
    expires_at: datetime


@dataclass(frozen=True)
class Allocation:
    source: Literal["daily_free", "subscription", "purchased"]
    amount: int
    lot_id: str | None = None


@dataclass(frozen=True)
class AllocationPlan:
    required: int
    allocations: tuple[Allocation, ...]
    remaining: int


def credits_for_usage(
    prompt_tokens: int | None,
    output_tokens: int | None,
    *,
    input_weight: int = 1,
    output_weight: int = 1,
) -> int:
    """Convert known non-negative provider counters into integer credits."""
    if prompt_tokens is None or output_tokens is None:
        raise UsageUnavailable("No se puede liquidar un uso con contadores desconocidos")
    values = (prompt_tokens, output_tokens, input_weight, output_weight)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("Los contadores y ponderadores deben ser enteros no negativos")
    return prompt_tokens * input_weight + output_tokens * output_weight


def plan_allocation(
    required: int,
    *,
    daily_free_available: int,
    subscription_available: int,
    purchased_lots: tuple[CreditLot, ...] = (),
    purchased_fallback_allowed: bool = False,
    now: datetime | None = None,
) -> AllocationPlan:
    """Plan FREE daily -> subscription -> purchased FEFO without mutating balances."""
    values = (required, daily_free_available, subscription_available)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("Los saldos y el consumo requerido deben ser enteros no negativos")
    if required == 0:
        return AllocationPlan(0, (), 0)

    remaining = required
    allocations: list[Allocation] = []
    for source, available in (
        ("daily_free", daily_free_available),
        ("subscription", subscription_available),
    ):
        amount = min(remaining, available)
        if amount:
            allocations.append(Allocation(source=source, amount=amount))
            remaining -= amount

    if remaining and purchased_fallback_allowed:
        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now debe incluir zona horaria")
        valid_lots = []
        for lot in purchased_lots:
            if not lot.lot_id or isinstance(lot.available, bool) or not isinstance(lot.available, int) or lot.available < 0:
                raise ValueError("Lote de créditos inválido")
            if lot.expires_at.tzinfo is None or lot.expires_at.utcoffset() is None:
                raise ValueError("La expiración del lote debe incluir zona horaria")
            if lot.expires_at > instant and lot.available:
                valid_lots.append(lot)
        for lot in sorted(valid_lots, key=lambda item: (item.expires_at, item.lot_id)):
            amount = min(remaining, lot.available)
            if amount:
                allocations.append(Allocation(source="purchased", amount=amount, lot_id=lot.lot_id))
                remaining -= amount
            if not remaining:
                break

    if remaining:
        raise InsufficientCredits("Cuota agotada o créditos comprados insuficientes")
    return AllocationPlan(required, tuple(allocations), 0)
