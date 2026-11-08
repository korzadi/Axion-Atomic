"""Contratos sin base de datos del módulo de conciliación QvaPay."""
import asyncio

import httpx
import pytest

from api.qvapay_lightning import QvaPayLightningClient, QvaPayLightningConfigError
from api.qvapay_settlement import fetch_recent_payments, new_payment_reference

ADDRESS = "axionatomic@qvpay.me"
TOKEN = "qvapay-user-token-for-tests"


def _status_payload(payments):
    return {
        "data": {
            "visible": True,
            "available": True,
            "receiving": True,
            "address": {
                "uuid": "0b9f3c1e-6a2d-4c5b-9e7f-2a1b3c4d5e6f",
                "name": "axionatomic",
                "address": ADDRESS,
                "lnurl": "LNURL1TEST",
                "status": "active",
                "receive_as": "usd",
            },
            "limits": {"min_usd": 0.1, "max_usd": 500, "daily_usd": 1000,
                       "used_24h_usd": 0, "remaining_usd": 1000},
            "fees": {"usd_pct": 0.5},
            "payments": payments,
        }
    }


def _payment(index, sats=21000):
    return {
        "uuid": f"6c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e{index:02d}",
        "address": ADDRESS,
        "sats": sats,
        "credit_usd": "14.54",
        "credit_unit": "usd",
        "comment": f"order-{index}",
        "paid_at": "2026-10-30T12:05:00.000Z",
        "transaction_uuid": f"9a8b7c6d-5e4f-4a3b-2c1d-0e9f8a7b6c{index:02d}",
    }


def test_new_payment_reference_is_unique_and_bounded():
    references = {new_payment_reference() for _ in range(200)}
    assert len(references) == 200
    assert all(r.startswith("axy") and 8 <= len(r) <= 64 for r in references)


def test_fetch_recent_payments_paginates_until_short_page():
    pages = {}

    def handler(request):
        page = int(request.url.params.get("page", "1"))
        pages[page] = pages.get(page, 0) + 1
        payments = [_payment(i) for i in range(20 * (page - 1), 20 * page)] if page < 3 else [_payment(60)]
        return httpx.Response(200, json=_status_payload(payments))

    client = QvaPayLightningClient(transport=httpx.MockTransport(handler))
    payments = asyncio.run(fetch_recent_payments(client, token=TOKEN))
    assert len(payments) == 41
    assert pages == {1: 1, 2: 1, 3: 1}


def test_fetch_recent_payments_stops_when_page_repeats():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=_status_payload([_payment(1)]))

    client = QvaPayLightningClient(transport=httpx.MockTransport(handler))
    payments = asyncio.run(fetch_recent_payments(client, token=TOKEN))
    assert len(payments) == 1
    assert len(calls) == 1


def test_fetch_recent_payments_deduplicates_transactions():
    def handler(request):
        page = int(request.url.params.get("page", "1"))
        if page == 1:
            return httpx.Response(200, json=_status_payload([_payment(i) for i in range(1, 21)]))
        return httpx.Response(200, json=_status_payload([_payment(1)] + [_payment(i) for i in range(21, 40)]))

    client = QvaPayLightningClient(transport=httpx.MockTransport(handler))
    payments = asyncio.run(fetch_recent_payments(client, token=TOKEN))
    uuids = [p.transaction_uuid for p in payments]
    assert len(uuids) == len(set(uuids))


def test_fetch_recent_payments_respects_page_cap_and_validates_input():
    def handler(request):
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(
            200, json=_status_payload([_payment(i) for i in range(20 * (page - 1) + 1, 20 * page + 1)])
        )

    client = QvaPayLightningClient(transport=httpx.MockTransport(handler))
    payments = asyncio.run(fetch_recent_payments(client, token=TOKEN, max_pages=2))
    assert len(payments) == 40
    with pytest.raises(QvaPayLightningConfigError):
        asyncio.run(fetch_recent_payments(client, token=TOKEN, max_pages=0))
