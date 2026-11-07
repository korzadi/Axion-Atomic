"""Primitivas MFA para AXION ATOMIC.

No gestiona sesiones ni persiste datos: las rutas deben usar transacciones
atómicas al guardar last_counter y consumir códigos de recuperación.
La clave AES debe venir de un gestor externo; nunca se genera ni persiste aquí.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class MfaError(RuntimeError):
    """Error seguro al cifrar o descifrar secretos MFA."""


class MfaKeyProvider(Protocol):
    def active_key(self) -> tuple[str, bytes]:
        """Devuelve un ID y una clave AES-256 desde un gestor externo."""
        ...

    def get_key(self, key_id: str) -> bytes:
        """Recupera una clave histórica para descifrado/rotación."""
        ...


@dataclass(frozen=True)
class EncryptedTotpSecret:
    ciphertext: bytes
    nonce: bytes
    key_id: str


def generate_totp_secret() -> str:
    """Genera 160 bits aleatorios codificados en Base32 sin padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    if not isinstance(secret, str) or not re.fullmatch(r"[A-Z2-7]{16,128}", secret):
        raise ValueError("Secreto TOTP Base32 no válido")
    try:
        return base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=False)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Secreto TOTP Base32 no válido") from exc


def totp_at(secret: str, timestamp: int | float, *, period: int = 30, digits: int = 6) -> str:
    """Calcula TOTP RFC 6238 (HMAC-SHA1, ventana temporal configurable)."""
    if period < 15 or period > 120 or digits not in (6, 8):
        raise ValueError("Parámetros TOTP no válidos")
    counter = int(timestamp) // period
    digest = hmac.new(_secret_bytes(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** digits)).zfill(digits)


def matching_totp_counter(
    secret: str,
    code: str,
    *,
    now: int | float | None = None,
    last_accepted_counter: int = -1,
    window: int = 1,
    period: int = 30,
    digits: int = 6,
) -> int | None:
    """Devuelve el contador válido más cercano; el llamador debe persistirlo atómicamente.

    Rechaza códigos ya aceptados. Un resultado no debe considerarse consumido
    hasta que last_accepted_counter se actualice dentro de una transacción.
    """
    if not isinstance(code, str) or not re.fullmatch(rf"\d{{{digits}}}", code):
        return None
    if window < 0 or window > 2:
        raise ValueError("Ventana TOTP no válida")
    timestamp = time.time() if now is None else now
    current = int(timestamp) // period
    for counter in sorted(range(current - window, current + window + 1), key=lambda n: (abs(n - current), -n)):
        if counter <= last_accepted_counter or counter < 0:
            continue
        expected = totp_at(secret, counter * period, period=period, digits=digits)
        if hmac.compare_digest(expected, code):
            return counter
    return None


def _validate_key(key_id: str, key: bytes) -> None:
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise MfaError("Identificador de clave MFA no válido")
    if not isinstance(key, bytes) or len(key) != 32:
        raise MfaError("El proveedor MFA debe entregar una clave AES-256 de 32 bytes")


class AesGcmTotpCipher:
    """Cifra secretos TOTP con AES-256-GCM y AAD ligada al usuario."""

    def __init__(self, key_provider: MfaKeyProvider):
        self._keys = key_provider

    @staticmethod
    def _aad(user_id: str) -> bytes:
        if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 256:
            raise ValueError("Identificador de usuario no válido")
        return f"axion-mfa-totp:v1:{user_id}".encode("utf-8")

    def encrypt(self, secret: str, *, user_id: str) -> EncryptedTotpSecret:
        _secret_bytes(secret)
        key_id, key = self._keys.active_key()
        _validate_key(key_id, key)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, secret.encode("ascii"), self._aad(user_id))
        return EncryptedTotpSecret(ciphertext=ciphertext, nonce=nonce, key_id=key_id)

    def decrypt(self, encrypted: EncryptedTotpSecret, *, user_id: str) -> str:
        if not isinstance(encrypted, EncryptedTotpSecret) or len(encrypted.nonce) != 12:
            raise MfaError("Registro TOTP cifrado no válido")
        key = self._keys.get_key(encrypted.key_id)
        _validate_key(encrypted.key_id, key)
        try:
            secret = AESGCM(key).decrypt(encrypted.nonce, encrypted.ciphertext, self._aad(user_id)).decode("ascii")
            _secret_bytes(secret)
            return secret
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise MfaError("No se pudo autenticar el secreto TOTP") from exc


def generate_recovery_codes(count: int = 10) -> list[str]:
    """Genera códigos de recuperación de alta entropía; mostrarlos una sola vez."""
    if count < 1 or count > 20:
        raise ValueError("Cantidad de códigos de recuperación no válida")
    return [secrets.token_hex(8).upper() for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    """Hash SHA-256 de código aleatorio de 64 bits; nunca guardar el código original."""
    if not isinstance(code, str) or not re.fullmatch(r"[A-Fa-f0-9]{16}", code):
        raise ValueError("Código de recuperación no válido")
    return hashlib.sha256(code.upper().encode("ascii")).hexdigest()
