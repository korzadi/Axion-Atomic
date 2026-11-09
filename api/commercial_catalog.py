"""Catálogo comercial V1.0 — valores aprobados por el propietario (2026-11-08).

Fuente: ``docs/COMMERCIAL_VALIDATION_V1.md`` (entregables A–H) y decisión
explícita del propietario del 2026-11-08:

- 1 crédito = 100 tokens (los ponderadores viven en ``api/config.py``).
- FREE = 50 créditos de concesión única al verificar el correo.
- Planes de **compra única** (sin suscripciones recurrentes en V1.0):
  STARTER 300 créditos $4,99 · PLUS 750 créditos $9,99 ·
  PRO 1.700 créditos $19,99 · STUDIO 3.600 créditos $39,99.
- Comisión Lightning asumida: 0,5 % (hipótesis no garantizada por el proveedor;
  la tarifa efectiva se lee en runtime de ``address_status``).
- Sin paquetes de créditos adicionales, sin planes no documentados.
- Los precios se publican en unidades menores (centavos USD) y el catálogo no
  concede créditos por sí mismo: el cobro exige QvaPay verificado (ver
  ``api/checkout_routes.py``).

``checkout_enabled`` refleja ``QVAPAY_ENABLED`` en tiempo real: con la
integración desactivada, el catálogo se publica pero el cobro falla cerrado.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from api.config import settings

CATALOG_VERSION = 1

FREE_CREDITS_ON_VERIFY = 50


@dataclass(frozen=True)
class PublicModel:
    code: str
    name: str
    description: str
    available_for_chat: bool
    billing_candidate: bool
    billing_enabled: bool


_PLANS = (
    {
        "code": "starter_300",
        "name": "Axyron Atomic STARTER",
        "description": "300 créditos (30.000 tokens) de Atomic Code. Compra única, sin renovación.",
        "credits": 300,
        "price_minor": 499,
        "currency": "USD",
        "one_time": True,
    },
    {
        "code": "plus_750",
        "name": "Axyron Atomic PLUS",
        "description": "750 créditos (75.000 tokens) de Atomic Code. Compra única, sin renovación.",
        "credits": 750,
        "price_minor": 999,
        "currency": "USD",
        "one_time": True,
    },
    {
        "code": "pro_1700",
        "name": "Axyron Atomic PRO",
        "description": "1.700 créditos (170.000 tokens) de Atomic Code. Compra única, sin renovación.",
        "credits": 1700,
        "price_minor": 1999,
        "currency": "USD",
        "one_time": True,
    },
    {
        "code": "studio_3600",
        "name": "Axyron Atomic STUDIO",
        "description": "3.600 créditos (360.000 tokens) de Atomic Code. Compra única, sin renovación.",
        "credits": 3600,
        "price_minor": 3999,
        "currency": "USD",
        "one_time": True,
    },
)

_STATIC_MODEL = PublicModel(
    code="atomic-code",
    name="ATOMIC CODE",
    description="Modelo de programación de AXYRON ATOMIC.",
    available_for_chat=True,
    billing_candidate=True,
    billing_enabled=False,
)


def public_catalog() -> dict:
    """Representación serializable y detachada; sin secretos ni datos internos."""
    checkout_enabled = bool(settings.qvapay_enabled)
    model = asdict(_STATIC_MODEL)
    model["billing_enabled"] = bool(settings.billing_enforcement_enabled)
    return {
        "version": CATALOG_VERSION,
        "status": "active",
        "checkout_enabled": checkout_enabled,
        "payment_provider": "qvapay_lightning" if checkout_enabled else None,
        "models": [model],
        "plans": [dict(plan) for plan in _PLANS],
        "credit_packages": [],
        "free_credits_on_verify": FREE_CREDITS_ON_VERIFY,
    }


def plan_for_code(product_code: str) -> dict | None:
    """Devuelve una copia del plan aprobado o ``None`` si no existe."""
    if not isinstance(product_code, str):
        return None
    for plan in _PLANS:
        if plan["code"] == product_code:
            return dict(plan)
    return None
