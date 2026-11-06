-- 016: órdenes internas y conciliación de pagos.
-- No integra proveedores, no crea facturas y no habilita cobros.
CREATE TABLE payment_orders (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    product_code TEXT NOT NULL CHECK (length(product_code) BETWEEN 1 AND 80),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'USD'),
    credits BIGINT NOT NULL CHECK (credits > 0),
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'under_review', 'paid', 'expired', 'cancelled', 'refunded'
    )),
    payment_method TEXT NOT NULL CHECK (payment_method = 'qvapay_lightning'),
    expires_at TIMESTAMPTZ NOT NULL,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);
CREATE INDEX idx_payment_orders_user_created
    ON payment_orders(user_id, created_at DESC);
CREATE INDEX idx_payment_orders_pending_expiry
    ON payment_orders(status, expires_at) WHERE status = 'pending';

CREATE TABLE payment_transactions (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES payment_orders(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL CHECK (provider = 'qvapay_lightning'),
    provider_transaction_id TEXT NOT NULL CHECK (length(provider_transaction_id) BETWEEN 1 AND 200),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'USD'),
    recipient TEXT NOT NULL CHECK (length(recipient) BETWEEN 1 AND 200),
    verification_source TEXT NOT NULL CHECK (verification_source IN ('provider_api', 'signed_webhook', 'manual_review')),
    verified_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_transaction_id),
    UNIQUE (order_id)
);
CREATE INDEX idx_payment_transactions_order ON payment_transactions(order_id);

CREATE TABLE payment_order_events (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES payment_orders(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'created', 'payment_observed', 'payment_verified', 'review_required',
        'expired', 'cancelled', 'refund_recorded'
    )),
    event_key TEXT NOT NULL UNIQUE CHECK (length(event_key) BETWEEN 1 AND 200),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor TEXT NOT NULL CHECK (length(actor) BETWEEN 1 AND 120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payment_order_events_order
    ON payment_order_events(order_id, created_at, id);

CREATE OR REPLACE FUNCTION payment_reject_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'payment_order_events es append-only';
END;
$$;
CREATE TRIGGER trg_payment_order_events_no_update_delete
    BEFORE UPDATE OR DELETE ON payment_order_events
    FOR EACH ROW EXECUTE FUNCTION payment_reject_event_mutation();
CREATE TRIGGER trg_payment_order_events_no_truncate
    BEFORE TRUNCATE ON payment_order_events
    FOR EACH STATEMENT EXECUTE FUNCTION payment_reject_event_mutation();
