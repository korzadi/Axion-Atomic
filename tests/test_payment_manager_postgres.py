"""PostgreSQL integration tests for internal payment order bookkeeping."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from api.payment_manager import (
    PaymentOrderNotFound, PaymentOrderStateError, VerifiedPayment,
    confirm_verified_payment, create_payment_order, get_payment_order,
    record_payment_observation,
)

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.startswith(("postgresql://", "postgresql+")):
    pytest.skip("Requiere PostgreSQL del job postgres-migrations", allow_module_level=True)
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def _user():
    user_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (id, email, email_normalized, password_hash, display_name, status)
            VALUES (:id, :email, :email, 'test-hash', 'Payment test', 'active')
        """), {"id": user_id, "email": f"{user_id}@example.invalid"})
    return user_id


def _order(user_id, amount=500, credits=1000):
    return create_payment_order(
        engine=engine, user_id=user_id, product_code="credits-1000",
        amount_minor=amount, credits=credits,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
    )


def test_create_order_is_persisted_and_private_to_owner():
    user_id = _user()
    order = _order(user_id)
    assert order.status == "pending"
    assert order.amount_minor == 500
    assert order.currency == "USD"
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id) == order
    with pytest.raises(PaymentOrderNotFound):
        get_payment_order(engine=engine, user_id=str(uuid.uuid4()), order_id=order.order_id)


def test_untrusted_observation_never_marks_order_paid_or_grants_credits():
    user_id = _user()
    order = _order(user_id)
    assert record_payment_observation(
        engine=engine, order_id=order.order_id, event_key="untrusted-observation-1",
        actor="system", details={"source":"client_claim","note":"user says paid"},
    )
    assert not record_payment_observation(
        engine=engine, order_id=order.order_id, event_key="untrusted-observation-1",
        actor="system", details={"source":"client_claim"},
    )
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "pending"
    with engine.connect() as conn:
        lots = conn.execute(text("SELECT count(*) FROM billing_credit_lots WHERE user_id=:u"), {"u": user_id}).scalar_one()
        events = conn.execute(text("""
            SELECT count(*) FROM payment_order_events
            WHERE order_id=CAST(:id AS UUID) AND event_type='payment_observed'
        """), {"id": order.order_id}).scalar_one()
    assert lots == 0
    assert events == 1


def test_exact_verified_payment_grants_credits_once_atomically():
    user_id = _user()
    order = _order(user_id)
    payment = VerifiedPayment(
        provider_transaction_id="qv-lightning-tx-unique-001",
        amount_minor=500, currency="USD", recipient="axionatomic@qvpay.me",
        verification_source="provider_api", verified_at=datetime.now(timezone.utc),
    )
    assert confirm_verified_payment(
        engine=engine, order_id=order.order_id, payment=payment,
        expected_recipient="axionatomic@qvpay.me",
    )
    assert not confirm_verified_payment(
        engine=engine, order_id=order.order_id, payment=payment,
        expected_recipient="axionatomic@qvpay.me",
    )
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "paid"
    with engine.connect() as conn:
        lot = conn.execute(text("""
            SELECT granted_credits, available_credits FROM billing_credit_lots
            WHERE user_id=:u AND source_reference=:ref
        """), {"u": user_id, "ref": f"payment-order:{order.order_id}"}).one()
        ledger_count = conn.execute(text("""
            SELECT count(*) FROM billing_credit_ledger
            WHERE user_id=:u AND idempotency_key=:key
        """), {"u": user_id, "key": f"payment-grant:{order.order_id}"}).scalar_one()
        tx_count = conn.execute(text("""
            SELECT count(*) FROM payment_transactions WHERE order_id=CAST(:id AS UUID)
        """), {"id": order.order_id}).scalar_one()
    assert lot.granted_credits == 1000 and lot.available_credits == 1000
    assert ledger_count == 1 and tx_count == 1


def test_amount_mismatch_moves_order_to_review_without_grant():
    user_id = _user()
    order = _order(user_id)
    payment = VerifiedPayment(
        provider_transaction_id="qv-lightning-tx-mismatch-002",
        amount_minor=499, currency="USD", recipient="axionatomic@qvpay.me",
        verification_source="provider_api", verified_at=datetime.now(timezone.utc),
    )
    assert not confirm_verified_payment(
        engine=engine, order_id=order.order_id, payment=payment,
        expected_recipient="axionatomic@qvpay.me",
    )
    assert get_payment_order(engine=engine, user_id=user_id, order_id=order.order_id).status == "under_review"
    with engine.connect() as conn:
        lots = conn.execute(text("SELECT count(*) FROM billing_credit_lots WHERE user_id=:u"), {"u": user_id}).scalar_one()
    assert lots == 0


def test_same_provider_transaction_cannot_pay_two_orders():
    user_id = _user()
    first, second = _order(user_id), _order(user_id)
    payment = VerifiedPayment(
        provider_transaction_id="qv-lightning-tx-replay-003",
        amount_minor=500, currency="USD", recipient="axionatomic@qvpay.me",
        verification_source="provider_api", verified_at=datetime.now(timezone.utc),
    )
    confirm_verified_payment(engine=engine, order_id=first.order_id, payment=payment,
                             expected_recipient="axionatomic@qvpay.me")
    with pytest.raises(Exception):
        confirm_verified_payment(engine=engine, order_id=second.order_id, payment=payment,
                                 expected_recipient="axionatomic@qvpay.me")
    assert get_payment_order(engine=engine, user_id=user_id, order_id=second.order_id).status == "pending"
