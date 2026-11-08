"""Cliente oficial de Lightning Address de QvaPay (LUD-16/LUD-06/LUD-12).

Contrato verificado el 8 de noviembre de 2026 contra la documentación pública:
- ``GET https://api.qvapay.com/user/lightning-address`` (Bearer del titular)
- ``GET https://qvpay.me/.well-known/lnurlp/{name}`` (público)
- ``GET {callback}?amount={msat}&comment={texto}`` (público)
- ``GET https://api.qvapay.com/coins`` (precio BTC/USD público)

El token del titular es un secreto: nunca se registra ni se incluye en errores.
Este módulo no crea órdenes ni escribe en la base de datos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from urllib.parse import quote, urlsplit

import httpx


API_BASE_URL = "https://api.qvapay.com"
LNURL_BASE_URL = "https://qvpay.me"
LNURL_CALLBACK_HOSTS = frozenset({"www.qvapay.com", "qvapay.com"})
_ADDRESS_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{1,30})[a-z0-9]$")


class QvaPayLightningError(RuntimeError):
    """Fallo seguro del adaptador; nunca incluye el token ni el cuerpo remoto."""


class QvaPayLightningConfigError(QvaPayLightningError):
    """Configuración local inválida (token, dirección, importe o comentario)."""


class QvaPayLightningTransportError(QvaPayLightningError):
    """No se pudo contactar con QvaPay o la respuesta no es utilizable."""


class QvaPayLightningResponseError(QvaPayLightningError):
    """QvaPay devolvió un estado o contrato inesperado."""


@dataclass(frozen=True)
class LightningPayment:
    uuid: str
    transaction_uuid: str
    address: str
    sats: int
    credit_usd: Decimal
    credit_unit: str
    comment: str | None
    paid_at: datetime


@dataclass(frozen=True)
class LightningAddressStatus:
    visible: bool
    available: bool
    receiving: bool
    address: str | None
    name: str | None
    lnurl: str | None
    status: str | None
    receive_as: str | None
    min_usd: Decimal
    max_usd: Decimal
    daily_usd: Decimal
    used_24h_usd: Decimal
    remaining_usd: Decimal
    fee_usd_pct: Decimal
    payments: tuple[LightningPayment, ...]


@dataclass(frozen=True)
class LnurlPayRequest:
    callback: str
    min_sendable_msat: int
    max_sendable_msat: int
    comment_allowed: int


@dataclass(frozen=True)
class LightningInvoice:
    pr: str
    sats: int
    comment: str
    callback: str


def validate_comment(comment: str) -> str:
    if not isinstance(comment, str) or not 1 <= len(comment) <= 255:
        raise QvaPayLightningConfigError("El comentario debe tener entre 1 y 255 caracteres")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in comment):
        raise QvaPayLightningConfigError("El comentario contiene caracteres de control")
    return comment


def validate_address_name(name: str) -> str:
    if not isinstance(name, str) or not _ADDRESS_NAME.fullmatch(name):
        raise QvaPayLightningConfigError("Nombre de Lightning Address inválido")
    return name


def usd_cents_to_sats(amount_minor: int, btc_usd_price: Decimal) -> int:
    """Convierte centavos USD a sats enteros, redondeando siempre al alza."""
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise QvaPayLightningConfigError("El importe en centavos debe ser un entero positivo")
    try:
        price = Decimal(btc_usd_price)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QvaPayLightningConfigError("Precio BTC/USD inválido") from exc
    if not price.is_finite() or price <= 0:
        raise QvaPayLightningConfigError("Precio BTC/USD inválido")
    sats = (Decimal(amount_minor) / Decimal(100) / price * Decimal(100_000_000)).to_integral_value(
        rounding=ROUND_CEILING
    )
    if sats < 1:
        raise QvaPayLightningConfigError("El importe no alcanza un satoshi")
    return int(sats)


def _decimal(value, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay") from exc
    if not parsed.is_finite() or parsed < 0:
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay")
    return parsed


def _integer(value, field: str) -> int:
    if isinstance(value, bool):
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay")
    if isinstance(value, int):
        parsed = value
    else:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError) as exc:
            raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay") from exc
    if parsed < 0:
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay")
    return parsed


def _timestamp(value, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QvaPayLightningResponseError(f"Campo {field} inválido en QvaPay") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QvaPayLightningResponseError(f"Campo {field} sin zona horaria")
    return parsed.astimezone(timezone.utc)


def _validate_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise QvaPayLightningConfigError("Falta el token del titular de QvaPay")
    if any(ord(char) < 0x21 or ord(char) > 0x7E for char in token):
        raise QvaPayLightningConfigError("El token de QvaPay tiene caracteres inválidos")
    return token


def _validate_callback(value) -> str:
    if not isinstance(value, str):
        raise QvaPayLightningResponseError("Callback LNURL inválido")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme != "https"
        or host not in LNURL_CALLBACK_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/.well-known/lnurlp/")
        or not parsed.path.endswith("/callback")
    ):
        raise QvaPayLightningResponseError("Callback LNURL fuera del dominio oficial")
    return value


class QvaPayLightningClient:
    """Cliente asíncrono con endpoints fijos y transporte inyectable para pruebas."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise QvaPayLightningConfigError("El timeout debe ser positivo")
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            transport=self._transport,
            follow_redirects=False,
        )

    async def _get(self, url: str, *, headers: dict | None = None, params: dict | None = None):
        try:
            async with self._client() as client:
                response = await client.get(url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise QvaPayLightningTransportError("No se pudo contactar con QvaPay") from exc
        if response.status_code != 200:
            raise QvaPayLightningResponseError(
                f"QvaPay respondió HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise QvaPayLightningResponseError("QvaPay devolvió JSON inválido") from exc

    async def address_status(self, token: str, *, page: int = 1) -> LightningAddressStatus:
        """Consulta el estado y los últimos cobros de la dirección del titular."""
        clean_token = _validate_token(token)
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise QvaPayLightningConfigError("La página debe ser un entero positivo")
        payload = await self._get(
            f"{API_BASE_URL}/user/lightning-address",
            headers={"Authorization": f"Bearer {clean_token}"},
            params={"page": page} if page > 1 else None,
        )
        if not isinstance(payload, dict):
            raise QvaPayLightningResponseError("Respuesta de Lightning Address inválida")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise QvaPayLightningResponseError("Respuesta de Lightning Address inválida")
        address = data.get("address")
        if address is not None and not isinstance(address, dict):
            raise QvaPayLightningResponseError("Dirección Lightning inválida")
        limits = data.get("limits") or {}
        fees = data.get("fees") or {}
        if not isinstance(limits, dict) or not isinstance(fees, dict):
            raise QvaPayLightningResponseError("Límites o comisiones inválidos")
        raw_payments = data.get("payments") or []
        if not isinstance(raw_payments, list):
            raise QvaPayLightningResponseError("Lista de pagos inválida")

        payments: list[LightningPayment] = []
        for item in raw_payments:
            if not isinstance(item, dict):
                raise QvaPayLightningResponseError("Pago Lightning inválido")
            payment_address = item.get("address")
            if not isinstance(payment_address, str) or not payment_address:
                raise QvaPayLightningResponseError("Dirección de pago inválida")
            comment = item.get("comment")
            if comment is not None and not isinstance(comment, str):
                raise QvaPayLightningResponseError("Comentario de pago inválido")
            payments.append(
                LightningPayment(
                    uuid=str(item.get("uuid") or ""),
                    transaction_uuid=str(item.get("transaction_uuid") or ""),
                    address=payment_address,
                    sats=_integer(item.get("sats"), "sats"),
                    credit_usd=_decimal(item.get("credit_usd"), "credit_usd"),
                    credit_unit=str(item.get("credit_unit") or ""),
                    comment=comment,
                    paid_at=_timestamp(item.get("paid_at"), "paid_at"),
                )
            )

        return LightningAddressStatus(
            visible=bool(data.get("visible")),
            available=bool(data.get("available")),
            receiving=bool(data.get("receiving")),
            address=address.get("address") if isinstance(address, dict) else None,
            name=address.get("name") if isinstance(address, dict) else None,
            lnurl=address.get("lnurl") if isinstance(address, dict) else None,
            status=address.get("status") if isinstance(address, dict) else None,
            receive_as=address.get("receive_as") if isinstance(address, dict) else None,
            min_usd=_decimal(limits.get("min_usd", 0), "min_usd"),
            max_usd=_decimal(limits.get("max_usd", 0), "max_usd"),
            daily_usd=_decimal(limits.get("daily_usd", 0), "daily_usd"),
            used_24h_usd=_decimal(limits.get("used_24h_usd", 0), "used_24h_usd"),
            remaining_usd=_decimal(limits.get("remaining_usd", 0), "remaining_usd"),
            fee_usd_pct=_decimal(fees.get("usd_pct", 0), "usd_pct"),
            payments=tuple(payments),
        )

    async def btc_usd_price(self) -> Decimal:
        """Obtiene el precio BTC/USD publicado por QvaPay en ``GET /coins``."""
        payload = await self._get(f"{API_BASE_URL}/coins")
        if isinstance(payload, dict) and isinstance(payload.get("coins"), list):
            categories = payload["coins"]
        elif isinstance(payload, list):
            categories = payload
        else:
            raise QvaPayLightningResponseError("Respuesta de monedas inválida")
        for category in categories:
            if not isinstance(category, dict):
                continue
            for coin in category.get("Coins") or []:
                if not isinstance(coin, dict) or str(coin.get("tick") or "").upper() != "BTC":
                    continue
                price = _decimal(coin.get("price"), "precio BTC")
                if price <= 0:
                    raise QvaPayLightningResponseError("Precio BTC inválido")
                return price
        raise QvaPayLightningResponseError("QvaPay no publicó el precio BTC")

    async def lnurl_pay_request(self, name: str) -> LnurlPayRequest:
        clean_name = validate_address_name(name)
        payload = await self._get(f"{LNURL_BASE_URL}/.well-known/lnurlp/{quote(clean_name)}")
        if not isinstance(payload, dict):
            raise QvaPayLightningResponseError("Respuesta LNURL inválida")
        if payload.get("tag") != "payRequest":
            raise QvaPayLightningResponseError("Respuesta LNURL no es payRequest")
        callback = _validate_callback(payload.get("callback"))
        comment_allowed = _integer(payload.get("commentAllowed", 0), "commentAllowed")
        return LnurlPayRequest(
            callback=callback,
            min_sendable_msat=_integer(payload.get("minSendable"), "minSendable"),
            max_sendable_msat=_integer(payload.get("maxSendable"), "maxSendable"),
            comment_allowed=comment_allowed,
        )

    async def create_invoice(
        self, *, name: str, sats: int, comment: str
    ) -> LightningInvoice:
        """Crea una invoice Lightning exacta con el comentario de correlación."""
        clean_name = validate_address_name(name)
        clean_comment = validate_comment(comment)
        if isinstance(sats, bool) or not isinstance(sats, int) or sats <= 0:
            raise QvaPayLightningConfigError("La cantidad de sats debe ser un entero positivo")
        pay = await self.lnurl_pay_request(clean_name)
        amount_msat = sats * 1000
        if amount_msat < pay.min_sendable_msat or amount_msat > pay.max_sendable_msat:
            raise QvaPayLightningConfigError("El importe está fuera de los límites LNURL")
        if len(clean_comment) > pay.comment_allowed:
            raise QvaPayLightningConfigError("La dirección no admite el comentario de la orden")
        payload = await self._get(
            pay.callback,
            params={"amount": amount_msat, "comment": clean_comment},
        )
        if not isinstance(payload, dict):
            raise QvaPayLightningResponseError("Respuesta de invoice inválida")
        pr = payload.get("pr")
        if not isinstance(pr, str) or not pr.startswith("lnbc"):
            raise QvaPayLightningResponseError("QvaPay no devolvió una invoice Lightning válida")
        return LightningInvoice(
            pr=pr,
            sats=sats,
            comment=clean_comment,
            callback=pay.callback,
        )


def match_payment(
    payments: tuple[LightningPayment, ...] | list[LightningPayment],
    *,
    reference: str,
    sats: int,
    address: str,
) -> LightningPayment | None:
    """Devuelve el primer pago que coincide exactamente con referencia, sats y destino."""
    best: LightningPayment | None = None
    for payment in payments:
        if (
            payment.comment == reference
            and payment.sats == sats
            and payment.address == address
            and payment.transaction_uuid
        ):
            if best is None or payment.paid_at > best.paid_at:
                best = payment
    return best
