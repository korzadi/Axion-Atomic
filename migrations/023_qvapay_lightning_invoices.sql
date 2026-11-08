-- 023: persistencia de invoices Lightning de QvaPay ligadas a órdenes internas.
-- No habilita checkout ni acredita créditos; solo registra la correlación.
CREATE TABLE payment_invoices (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES payment_orders(id) ON DELETE RESTRICT,
    provider TEXT NOT NULL DEFAULT 'qvapay_lightning' CHECK (provider = 'qvapay_lightning'),
    reference TEXT NOT NULL UNIQUE CHECK (length(reference) BETWEEN 8 AND 64),
    bolt11 TEXT NOT NULL CHECK (length(bolt11) BETWEEN 16 AND 4096),
    comment TEXT NOT NULL CHECK (length(comment) BETWEEN 1 AND 255),
    sats BIGINT NOT NULL CHECK (sats > 0),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency CHAR(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    btc_usd_price NUMERIC(20,8) NOT NULL CHECK (btc_usd_price > 0),
    fee_usd_pct NUMERIC(6,3) NOT NULL CHECK (fee_usd_pct >= 0 AND fee_usd_pct < 100),
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'superseded', 'expired', 'paid')),
    provider_transaction_id TEXT,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_transaction_id),
    CHECK ((status = 'paid') = (provider_transaction_id IS NOT NULL AND paid_at IS NOT NULL))
);
CREATE UNIQUE INDEX payment_invoices_one_open_per_order
    ON payment_invoices(order_id) WHERE status = 'created';
CREATE INDEX idx_payment_invoices_status_created
    ON payment_invoices(status, created_at);
