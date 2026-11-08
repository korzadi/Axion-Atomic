"""Contratos del cliente oficial de Lightning Address de QvaPay."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from api.qvapay_lightning import (
    QvaPayLightningClient,
    QvaPayLightningConfigError,
    QvaPayLightningResponseError,
    QvaPayLightningTransportError,
    LightningPayment,
    match_payment,
    usd_cents_to_sats,
)


TOKEN = "qvapay-user-token-for-tests"
ADDRESS = "axyronatomic@qvpay.me"


def _client(handler):
    return QvaPayLightningClient(transport=httpx.MockTransport(handler))


def _status_payload():
    return {
        "data": {
            "visible": True,
            "available": True,
            "receiving": True,
            "address": {
                "uuid": "0b9f3c1e-6a2d-4c5b-9e7f-2a1b3c4d5e6f",
                "name": "axyronatomic",
                "address": ADDRESS,
                "lnurl": "LNURL1TEST",
                "status": "active",
                "receive_as": "usd",
            },
            "limits": {
                "min_usd": 0.1,
                "max_usd": 500,
                "daily_usd": 1000,
                "used_24h_usd": 14.61,
                "remaining_usd": 985.39,
            },
            "fees": {"usd_pct": 0.5, "sats_pct": 0},
            "payments": [
                {
                    "uuid": "6c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
                    "address": ADDRESS,
                    "sats": 21000,
                    "credit_usd": "14.54",
                    "credit_unit": "usd",
                    "comment": "order-reference",
                    "paid_at": "2026-10-30T12:05:00.000Z",
                    "transaction_uuid": "9a8b7c6d-5e4f-4a3b-2c1d-0e9f8a7b6c5d",
                }
            ],
        }
    }


def test_address_status_parses_documented_response_and_uses_bearer_token():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=_status_payload())

    status = asyncio.run(_client(handler).address_status(TOKEN))
    assert seen["url"] == "https://api.qvapay.com/user/lightning-address"
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert status.address == ADDRESS
    assert status.receiving is True
    assert status.min_usd == Decimal("0.1")
    assert status.fee_usd_pct == Decimal("0.5")
    assert status.payments[0].sats == 21000
    assert status.payments[0].paid_at == datetime(2026, 10, 30, 12, 5, tzinfo=timezone.utc)


def test_address_status_sends_page_only_when_requested():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json=_status_payload())

    client = _client(handler)
    asyncio.run(client.address_status(TOKEN))
    asyncio.run(client.address_status(TOKEN, page=3))
    assert urls == [
        "https://api.qvapay.com/user/lightning-address",
        "https://api.qvapay.com/user/lightning-address?page=3",
    ]


def test_http_error_does_not_include_token_or_remote_body():
    def handler(request):
        return httpx.Response(401, json={"detail": "invalid token"})

    with pytest.raises(QvaPayLightningResponseError) as caught:
        asyncio.run(_client(handler).address_status(TOKEN))
    message = str(caught.value)
    assert "401" in message
    assert TOKEN not in message
    assert "invalid token" not in message


def test_transport_error_is_wrapped_without_credentials():
    def handler(request):
        raise httpx.ConnectError("connection failed")

    with pytest.raises(QvaPayLightningTransportError) as caught:
        asyncio.run(_client(handler).address_status(TOKEN))
    assert TOKEN not in str(caught.value)


def test_invalid_status_contract_is_rejected():
    payload = _status_payload()
    payload["data"]["payments"][0]["sats"] = -1

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(QvaPayLightningResponseError):
        asyncio.run(_client(handler).address_status(TOKEN))


def test_btc_usd_price_reads_public_coins_endpoint():
    def handler(request):
        assert str(request.url) == "https://api.qvapay.com/coins"
        return httpx.Response(200, json=[
            {"Coins": [
                {"tick": "USDT", "price": "1"},
                {"tick": "BTC", "price": "62500.25"},
            ]}
        ])

    assert asyncio.run(_client(handler).btc_usd_price()) == Decimal("62500.25")


def test_btc_usd_price_rejects_missing_coin():
    def handler(request):
        return httpx.Response(200, json=[{"Coins": [{"tick": "USDT", "price": "1"}]}])

    with pytest.raises(QvaPayLightningResponseError):
        asyncio.run(_client(handler).btc_usd_price())


def test_lnurl_pay_request_and_invoice_use_official_callback():
    paths = []

    def handler(request):
        paths.append(str(request.url))
        if request.url.host == "qvpay.me":
            return httpx.Response(200, json={
                "tag": "payRequest",
                "callback": "https://www.qvapay.com/.well-known/lnurlp/axyronatomic/callback",
                "minSendable": 143000,
                "maxSendable": 714285000,
                "commentAllowed": 255,
            })
        assert request.url.params["amount"] == "1000000"
        assert request.url.params["comment"] == "order-123"
        return httpx.Response(200, json={"pr": "lnbc10u1ptest", "routes": []})

    invoice = asyncio.run(
        _client(handler).create_invoice(name="axyronatomic", sats=1000, comment="order-123")
    )
    assert invoice.sats == 1000
    assert invoice.pr == "lnbc10u1ptest"
    assert paths == [
        "https://qvpay.me/.well-known/lnurlp/axyronatomic",
        "https://www.qvapay.com/.well-known/lnurlp/axyronatomic/callback?amount=1000000&comment=order-123",
    ]


def test_lnurl_rejects_callback_outside_official_domain():
    def handler(request):
        return httpx.Response(200, json={
            "tag": "payRequest",
            "callback": "https://evil.example/callback",
            "minSendable": 1000,
            "maxSendable": 1000000,
            "commentAllowed": 255,
        })

    with pytest.raises(QvaPayLightningResponseError):
        asyncio.run(_client(handler).lnurl_pay_request("axyronatomic"))


def test_invoice_rejects_amount_outside_lnurl_limits_without_creating_invoice():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={
            "tag": "payRequest",
            "callback": "https://www.qvapay.com/.well-known/lnurlp/axyronatomic/callback",
            "minSendable": 100000,
            "maxSendable": 200000,
            "commentAllowed": 255,
        })

    with pytest.raises(QvaPayLightningConfigError):
        asyncio.run(
            _client(handler).create_invoice(name="axyronatomic", sats=10, comment="order-123")
        )
    assert len(calls) == 1


def test_sats_conversion_rounds_up_and_rejects_invalid_prices():
    assert usd_cents_to_sats(100, Decimal("62500")) == 1600
    assert usd_cents_to_sats(1, Decimal("62500")) == 16
    assert usd_cents_to_sats(1, Decimal("62000")) == 17
    with pytest.raises(QvaPayLightningConfigError):
        usd_cents_to_sats(0, Decimal("62500"))
    with pytest.raises(QvaPayLightningConfigError):
        usd_cents_to_sats(100, Decimal("0"))


def test_match_payment_requires_exact_reference_sats_and_address():
    payments = [
        LightningPayment(
            uuid="p1", transaction_uuid="t1", address=ADDRESS, sats=1600,
            credit_usd=Decimal("0.99"), credit_unit="usd", comment="order-1",
            paid_at=datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        ),
        LightningPayment(
            uuid="p2", transaction_uuid="t2", address=ADDRESS, sats=1600,
            credit_usd=Decimal("0.99"), credit_unit="usd", comment="order-1",
            paid_at=datetime(2026, 10, 30, 12, 5, tzinfo=timezone.utc),
        ),
    ]
    matched = match_payment(payments, reference="order-1", sats=1600, address=ADDRESS)
    assert matched is not None and matched.transaction_uuid == "t2"
    assert match_payment(payments, reference="order-1", sats=1601, address=ADDRESS) is None
    assert match_payment(payments, reference="order-2", sats=1600, address=ADDRESS) is None
    assert match_payment(payments, reference="order-1", sats=1600, address="otro@qvpay.me") is None


def test_address_name_and_comment_validation():
    client = _client(lambda request: httpx.Response(500))
    with pytest.raises(QvaPayLightningConfigError):
        asyncio.run(client.lnurl_pay_request("BAD NAME"))
    with pytest.raises(QvaPayLightningConfigError):
        asyncio.run(client.create_invoice(name="axyronatomic", sats=1, comment=""))
