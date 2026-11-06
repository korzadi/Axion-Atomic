"""Endpoint público de catálogo comercial en modo informativo.

No crea órdenes, no activa checkout y no publica precios no aprobados.
"""
from fastapi import APIRouter

from api.commercial_catalog import public_catalog

router = APIRouter(tags=["catalog"])


@router.get("/billing/catalog")
async def get_public_billing_catalog():
    """Devuelve únicamente el catálogo público aprobado para mostrar."""
    return public_catalog()
