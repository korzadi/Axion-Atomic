"""Catálogo comercial seguro: describe el alcance sin habilitar ventas ni facturación.

Los precios y límites permanecen sin publicar hasta su aprobación. Este módulo es
puro: no accede a PostgreSQL, no crea órdenes y no concede créditos.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PublicModel:
    code: str
    name: str
    description: str
    available_for_chat: bool
    billing_candidate: bool
    billing_enabled: bool


@dataclass(frozen=True)
class CommercialCatalog:
    version: int
    status: str
    checkout_enabled: bool
    payment_provider: str | None
    models: tuple[PublicModel, ...]
    plans: tuple[dict, ...]
    credit_packages: tuple[dict, ...]


CATALOG = CommercialCatalog(
    version=1,
    status="preview_only",
    checkout_enabled=False,
    payment_provider=None,
    models=(
        PublicModel(
            code="atomic-code",
            name="ATOMIC CODE",
            description="Modelo de programación de AXION ATOMIC.",
            available_for_chat=True,
            billing_candidate=True,
            billing_enabled=False,
        ),
    ),
    # No inventar precios, cuotas, nombres de planes ni paquetes.
    # Los arrays vacíos evitan que el frontend interprete productos como vendibles.
    plans=(),
    credit_packages=(),
)


def public_catalog() -> dict:
    """Devuelve una representación serializable sin datos internos ni secretos."""
    return {
        "version": CATALOG.version,
        "status": CATALOG.status,
        "checkout_enabled": CATALOG.checkout_enabled,
        "payment_provider": CATALOG.payment_provider,
        "models": [asdict(model) for model in CATALOG.models],
        "plans": list(CATALOG.plans),
        "credit_packages": list(CATALOG.credit_packages),
    }
