"""Contratos de persistencia y conciliación de invoices Lightning (PostgreSQL).

Se omite fuera del job postgres-migrations; exige DATABASE_URL.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)

from decimal import Decimal

from sqlalchemy import create_engine, text

from api.payment_manager import create_payment_order, get_payment_order, expire_overdue_orders
from api.qvapay_settlement import (
    InvoiceOrderStateError,
    InvoicePersistenceError,
    create_invoice_record,
    list_open_invoices,
    new_payment_reference,
    reconcile_lightning_payments,
)
from api.qvapay_lightning import LightningPayment

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
ADDRESS = "axyronatomic@qvpay.me"


def _user():
    user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status)
            VALUES (:id, :email, :email, 'test-hash', 'Payment invoice', 'active')
        """), {"id": user_id, "email": f"{user_id}@example.invalid"})
    return user_id


def _order(user_id, amount=500, credits=1000):
    return create_payment_order(
        engine=engine, user_id=user_id, product_code="credits-1000",
        amount_minor=amount, credits=credits,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
    )


def _invoice(order_id, sats=1000, reference=None):
    return create_invoice_record(
        engine=engine, order_id=order_id, bolt11="lnbc1000n1validtestinvoice010",
        reference=reference or new_payment_reference(),
        sats=sats, btc_usd_price="100000.00", fee_usd_pct="0.5",
    )


def _payment(*, reference, sats=1000, address=ADDRESS, tx=None,
             paid_at=None, credit_usd="5.00"):
    return LightningPayment(
        uuid=str(uuid.uuid4()), transaction_uuid=tx or str(uuid.uuid4()),
        address=address, sats=sats, credit_usd=Decimal(credit_usd),
        credit_unit="usd", comment=reference,
        paid_at=paid_at or datetime.now(timezone.utc),
    )


def test_invoice_is_persisted_for_pending_order_and_listed_open():
    user_id = _user()
    order = _order(user_id)
    record = create_invoice_record(
        engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice001",
        reference="axy" + uuid.uuid4().hex[:12], sats=21000,
        btc_usd_price="95000.5", fee_usd_pct="0.5",
    )
    assert record.status == "created"
    assert record.amount_minor == 500
    open_records = list_open_invoices(engine)
    assert any(r.invoice_id == record.invoice_id for r in open_records)


def test_creating_a_new_invoice_supersedes_the_open_one():
    user_id = _user()
    order = _order(user_id)
    first = _invoice(order.order_id, reference=new_payment_reference())
    second = _invoice(order.order_id, reference=new_payment_reference())
    with engine.connect() as conn:
        status_first = conn.execute(text(
            "SELECT status FROM payment_invoices WHERE id=CAST(:id AS UUID)"
        ), {"id": first.invoice_id}).scalar_one()
    assert status_first == "superseded"
    open_records = list_open_invoices(engine)
    assert [r.invoice_id for r in open_records if r.order_id == order.order_id] == [second.invoice_id]


def test_invoice_for_non_pending_order_is_rejected():
    user_id = _user()
    order = _order(user_id)
    reference = new_payment_reference()
    payment = _payment(reference=reference, sats=1000)
    create_invoice_record(
        engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice001",
        reference=reference, sats=1000, btc_usd_price="100000", fee_usd_pct="0.5",
    )
    reconcile_lightning_payments(engine=engine, payments=[payment], recipient=ADDRESS)
    with pytest.raises(InvoiceOrderStateError):
        _invoice(order.order_id, reference=new_payment_reference())


def test_create_invoice_validates_inputs():
    user_id = _user()
    order = _order(user_id)
    with pytest.raises(InvoicePersistenceError):
        create_invoice_record(
            engine=engine, order_id=order.order_id, bolt11="not-an-invoice",
            reference=new_payment_reference(), sats=1000,
            btc_usd_price="100000", fee_usd_pct="0.5",
        )
    with pytest.raises(InvoicePersistenceError):
        create_invoice_record(
            engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice001",
            reference="short", sats=1000, btc_usd_price="100000", fee_usd_pct="0.5",
        )
    with pytest.raises(InvoicePersistenceError):
        create_invoice_record(
            engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice001",
            reference=new_payment_reference(), sats=1000,
            btc_usd_price="0", fee_usd_pct="0.5",
        )


def test_matching_payment_confirms_order_grants_credits_and_marks_invoice_paid():
    user_id = _user()
    order = _order(user_id, amount=500, credits=1000)
    reference = new_payment_reference()
    invoice = create_invoice_record(
        engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice011",
        reference=reference, sats=1000, btc_usd_price="100000", fee_usd_pct="0.5",
    )
    paid_at = datetime.now(timezone.utc)
    payment = _payment(reference=reference, sats=1000, paid_at=paid_at)
    results = reconcile_lightning_payments(engine=engine, payments=[payment], recipient=ADDRESS)
    outcome = next(r for r in results if r.reference == reference)
    assert outcome.outcome == "confirmed"
    assert outcome.provider_transaction_id == payment.transaction_uuid
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT status, provider_transaction_id, paid_at
            FROM payment_invoices WHERE id=CAST(:id AS UUID)
        """), {"id": invoice.invoice_id}).mappings().one()
        credits = conn.execute(text("""
            SELECT coalesce(sum(granted_credits), 0) FROM billing_credit_lots
            WHERE source_reference=:ref
        """), {"ref": f"payment-order:{order.order_id}"}).scalar_one()
    assert row["status"] == "paid"
    assert row["provider_transaction_id"] == payment.transaction_uuid
    assert credits == 1000
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "paid"


def test_reconciliation_is_idempotent_for_same_transaction():
    user_id = _user()
    order = _order(user_id, amount=500, credits=1000)
    reference = new_payment_reference()
    create_invoice_record(
        engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice011",
        reference=reference, sats=1000, btc_usd_price="100000", fee_usd_pct="0.5",
    )
    payment = _payment(reference=reference, sats=1000)
    first = reconcile_lightning_payments(engine=engine, payments=[payment], recipient=ADDRESS)
    second = reconcile_lightning_payments(engine=engine, payments=[payment], recipient=ADDRESS)
    assert next(r for r in first if r.reference == reference).outcome == "confirmed"
    assert all(r.outcome != "confirmed" or r.reference != reference for r in second)
    with engine.connect() as conn:
        txs = conn.execute(text(
            "SELECT count(*) FROM payment_transactions WHERE order_id=CAST(:id AS UUID)"
        ), {"id": order.order_id}).scalar_one()
    assert txs == 1


def test_wrong_comment_wrong_sats_or_wrong_destination_never_confirms():
    user_id = _user()
    order = _order(user_id)
    reference = new_payment_reference()
    create_invoice_record(
        engine=engine, order_id=order.order_id, bolt11="lnbc1000n1validtestinvoice011",
        reference=reference, sats=1000, btc_usd_price="100000", fee_usd_pct="0.5",
    )
    bad_payments = [
        _payment(reference="other-reference", sats=1000),
        _payment(reference=reference, sats=999),
        _payment(reference=reference, sats=1000, address="otro@qvpay.me"),
    ]
    for payment in bad_payments:
        results = reconcile_lightning_payments(engine=engine, payments=[payment], recipient=ADDRESS)
        assert next(r for r in results if r.reference == reference).outcome == "unmatched"
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "pending"


def _expire_order_in_past(order_id):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE payment_orders
               SET expires_at = now() - interval '1 hour'
             WHERE id = CAST(:id AS UUID)
        """), {"id": order_id})


def test_expire_overdue_orders_closes_order_and_invoice_idempotently():
    user_id = _user()
    order = _order(user_id)
    invoice = _invoice(order.order_id, reference=new_payment_reference())
    _expire_order_in_past(order.order_id)
    assert expire_overdue_orders(engine=engine) == 1
    assert expire_overdue_orders(engine=engine) == 0
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "expired"
    with engine.connect() as conn:
        invoice_status = conn.execute(text(
            "SELECT status FROM payment_invoices WHERE id=CAST(:id AS UUID)"
        ), {"id": invoice.invoice_id}).scalar_one()
        events = conn.execute(text(
            "SELECT count(*) FROM payment_order_events WHERE order_id=CAST(:id AS UUID) AND event_type='expired'"
        ), {"id": order.order_id}).scalar_one()
    assert invoice_status == "expired"
    assert events == 1


def test_expire_overdue_orders_spares_fresh_orders():
    user_id = _user()
    order = _order(user_id)
    assert expire_overdue_orders(engine=engine) == 0
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "pending"


def test_get_payment_order_lazily_expires_overdue_order_and_invoice():
    user_id = _user()
    order = _order(user_id)
    invoice = _invoice(order.order_id, reference=new_payment_reference())
    _expire_order_in_past(order.order_id)
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "expired"
    with engine.connect() as conn:
        invoice_status = conn.execute(text(
            "SELECT status FROM payment_invoices WHERE id=CAST(:id AS UUID)"
        ), {"id": invoice.invoice_id}).scalar_one()
    assert invoice_status == "expired"


def test_expire_overdue_orders_rejects_invalid_limit():
    import pytest
    with pytest.raises(Exception):
        expire_overdue_orders(engine=engine, limit=0)
