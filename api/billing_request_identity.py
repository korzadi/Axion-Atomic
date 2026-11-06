"""Identidad estable de una solicitud HTTP idempotente."""
from __future__ import annotations

import uuid


# Namespace fijo del producto; no depende de datos secretos ni del proceso.
_REQUEST_NAMESPACE = uuid.UUID("7cb3f0c0-8c43-4f6b-9a3a-6d2efb7a0f31")


class InvalidIdempotencyKey(ValueError):
    pass


def stable_request_id(*, user_id: str, idempotency_key: str) -> str:
    """Misma identidad de usuario/clave produce siempre el mismo UUID."""
    if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 256:
        raise ValueError("user_id inválido")
    if not isinstance(idempotency_key, str):
        raise InvalidIdempotencyKey("Idempotency-Key debe ser texto")
    if not 1 <= len(idempotency_key) <= 200:
        raise InvalidIdempotencyKey("Idempotency-Key debe tener entre 1 y 200 caracteres")
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in idempotency_key):
        raise InvalidIdempotencyKey("Idempotency-Key debe usar caracteres ASCII imprimibles sin espacios")
    # El UUID no revela la clave original ni cambia entre reintentos.
    return str(uuid.uuid5(_REQUEST_NAMESPACE, f"{user_id}\0{idempotency_key}"))
