"""Cifrado autenticado de resultados de inferencia con proveedor de claves inyectable.

La aplicación debe conectar un KMS/secret manager; este módulo no almacena ni
genera claves persistentes. AES-256-GCM autentica también el contexto de dueño,
reserva y ejecución para impedir mover ciphertext entre registros.
"""
from __future__ import annotations

import os
import base64
import json
import uuid
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ResultEncryptionError(RuntimeError):
    """Error seguro de cifrado, clave o autenticación."""


class EnvironmentResultKeyProvider:
    """Proveedor separado para resultados de facturación; nunca genera ni registra claves.

    Requiere AXYRON_BILLING_RESULT_KEY_ID y AXYRON_BILLING_RESULT_KEY_B64.
    Las claves antiguas opcionales se inyectan en AXYRON_BILLING_RESULT_KEYRING_B64
    como JSON {key_id: base64_32_bytes}; no se reutiliza la clave MFA.
    """

    def active_key(self) -> tuple[str, bytes]:
        key_id = (os.environ.get("AXYRON_BILLING_RESULT_KEY_ID") or "").strip()
        encoded = (os.environ.get("AXYRON_BILLING_RESULT_KEY_B64") or "").strip()
        if not key_id or not encoded:
            raise ResultEncryptionError("Clave de cifrado de resultados de facturación no configurada")
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ResultEncryptionError("Clave de resultados de facturación no válida") from exc
        _validate_key(key_id, key)
        return key_id, key

    def get_key(self, key_id: str) -> bytes:
        active_id, active_key = self.active_key()
        if key_id == active_id:
            return active_key
        encoded_ring = (os.environ.get("AXYRON_BILLING_RESULT_KEYRING_B64") or "").strip()
        if not encoded_ring:
            raise ResultEncryptionError("Clave histórica de resultados no disponible")
        try:
            ring = json.loads(encoded_ring)
            encoded = ring.get(key_id) if isinstance(ring, dict) else None
            if not isinstance(encoded, str):
                raise ValueError("missing key")
            key = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError, base64.binascii.Error) as exc:
            raise ResultEncryptionError("Clave histórica de resultados no válida") from exc
        _validate_key(key_id, key)
        return key


class ResultKeyProvider(Protocol):
    def active_key(self) -> tuple[str, bytes]:
        """Devuelve (key_id, 32-byte AES key) desde un gestor externo."""
        ...

    def get_key(self, key_id: str) -> bytes:
        """Recupera una clave histórica por ID para descifrado/rotación."""
        ...


@dataclass(frozen=True)
class EncryptedResult:
    ciphertext: bytes
    nonce: bytes
    key_id: str


def _aad(*, user_id: str, reservation_id: str, execution_id: str) -> bytes:
    try:
        user = str(uuid.UUID(user_id))
        reservation = str(uuid.UUID(reservation_id))
        execution = str(uuid.UUID(execution_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("IDs de contexto inválidos") from exc
    return f"axion-result:v1:{user}:{reservation}:{execution}".encode("ascii")


def _validate_key(key_id: str, key: bytes) -> None:
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise ResultEncryptionError("Identificador de clave inválido")
    if not isinstance(key, bytes) or len(key) != 32:
        raise ResultEncryptionError("El proveedor debe entregar una clave AES-256 de 32 bytes")


class AesGcmResultCipher:
    """Cifrador AES-256-GCM; la custodia y rotación de claves son del proveedor."""

    def __init__(self, key_provider: ResultKeyProvider):
        self._keys = key_provider

    def encrypt(
        self, plaintext: bytes, *, user_id: str,
        reservation_id: str, execution_id: str,
    ) -> EncryptedResult:
        if not isinstance(plaintext, bytes) or not plaintext:
            raise ValueError("El resultado debe ser bytes no vacíos")
        key_id, key = self._keys.active_key()
        _validate_key(key_id, key)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(
            nonce, plaintext,
            _aad(user_id=user_id, reservation_id=reservation_id, execution_id=execution_id),
        )
        return EncryptedResult(ciphertext=ciphertext, nonce=nonce, key_id=key_id)

    def decrypt(
        self, encrypted: EncryptedResult, *, user_id: str,
        reservation_id: str, execution_id: str,
    ) -> bytes:
        if not isinstance(encrypted, EncryptedResult):
            raise TypeError("Se requiere EncryptedResult")
        if not isinstance(encrypted.nonce, bytes) or len(encrypted.nonce) != 12:
            raise ResultEncryptionError("Nonce AES-GCM inválido")
        key = self._keys.get_key(encrypted.key_id)
        _validate_key(encrypted.key_id, key)
        try:
            return AESGCM(key).decrypt(
                encrypted.nonce, encrypted.ciphertext,
                _aad(user_id=user_id, reservation_id=reservation_id, execution_id=execution_id),
            )
        except InvalidTag as exc:
            raise ResultEncryptionError("No se pudo autenticar el resultado cifrado") from exc
