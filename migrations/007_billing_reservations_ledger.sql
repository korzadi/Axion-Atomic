-- 007: base de datos para cuotas, reservas y ledger de créditos.
-- Aditiva: no activa cobros ni modifica rutas de inferencia.
-- La lógica transaccional y la protección append-only deben implementarse y probarse antes de facturar.

CREATE TABLE billing_quota_periods (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    quota_kind TEXT NOT NULL CHECK (quota_kind IN ('daily_free', 'subscription')),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    timezone_name TEXT NOT NULL DEFAULT 'UTC',
    limit_credits BIGINT NOT NULL CHECK (limit_credits >= 0),
    reserved_credits BIGINT NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
    consumed_credits BIGINT NOT NULL DEFAULT 0 CHECK (consumed_credits >= 0),
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_end > period_start),
    CHECK (reserved_credits + consumed_credits <= limit_credits),
    UNIQUE (user_id, quota_kind, period_start, period_end)
);
CREATE INDEX idx_billing_quota_user_window
    ON billing_quota_periods(user_id, period_end);

CREATE TABLE billing_credit_lots (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (source IN ('purchased', 'promotion', 'manual_adjustment')),
    source_reference TEXT NOT NULL,
    granted_credits BIGINT NOT NULL CHECK (granted_credits > 0),
    available_credits BIGINT NOT NULL CHECK (available_credits >= 0),
    reserved_credits BIGINT NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
    consumed_credits BIGINT NOT NULL DEFAULT 0 CHECK (consumed_credits >= 0),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (available_credits + reserved_credits + consumed_credits <= granted_credits),
    UNIQUE (source, source_reference)
);
CREATE INDEX idx_billing_credit_lots_fefo
    ON billing_credit_lots(user_id, expires_at, created_at, id)
    WHERE available_credits > 0;

CREATE TABLE billing_usage_reservations (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id TEXT REFERENCES projects(id) ON DELETE RESTRICT,
    request_id UUID NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    requested_credits BIGINT NOT NULL CHECK (requested_credits > 0),
    state TEXT NOT NULL CHECK (state IN ('held', 'settled', 'released', 'unknown', 'review')),
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    settled_at TIMESTAMPTZ,
    UNIQUE (user_id, idempotency_key),
    CHECK (expires_at > created_at),
    CHECK ((state = 'settled' AND settled_at IS NOT NULL) OR state <> 'settled')
);
CREATE INDEX idx_billing_reservations_recovery
    ON billing_usage_reservations(state, expires_at);

CREATE TABLE billing_reservation_allocations (
    id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL REFERENCES billing_usage_reservations(id) ON DELETE RESTRICT,
    source TEXT NOT NULL CHECK (source IN ('daily_free', 'subscription', 'purchased')),
    quota_period_id UUID REFERENCES billing_quota_periods(id) ON DELETE RESTRICT,
    credit_lot_id UUID REFERENCES billing_credit_lots(id) ON DELETE RESTRICT,
    allocated_credits BIGINT NOT NULL CHECK (allocated_credits > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (source IN ('daily_free', 'subscription') AND quota_period_id IS NOT NULL AND credit_lot_id IS NULL)
        OR (source = 'purchased' AND credit_lot_id IS NOT NULL AND quota_period_id IS NULL)
    )
);
CREATE INDEX idx_billing_allocations_reservation
    ON billing_reservation_allocations(reservation_id);
CREATE INDEX idx_billing_allocations_lot
    ON billing_reservation_allocations(credit_lot_id)
    WHERE credit_lot_id IS NOT NULL;

CREATE TABLE billing_credit_ledger (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    credit_lot_id UUID REFERENCES billing_credit_lots(id) ON DELETE RESTRICT,
    reservation_id UUID REFERENCES billing_usage_reservations(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'grant', 'reserve', 'consume', 'release', 'expire', 'adjustment', 'reversal'
    )),
    available_delta BIGINT NOT NULL DEFAULT 0,
    reserved_delta BIGINT NOT NULL DEFAULT 0,
    consumed_delta BIGINT NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    related_entry_id UUID REFERENCES billing_credit_ledger(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    actor_user_id TEXT REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (available_delta + reserved_delta + consumed_delta <> 0),
    CHECK (
        (event_type IN ('grant', 'adjustment') AND reservation_id IS NULL)
        OR (event_type IN ('reserve', 'consume', 'release') AND reservation_id IS NOT NULL)
        OR event_type IN ('expire', 'reversal')
    )
);
CREATE INDEX idx_billing_ledger_user_created
    ON billing_credit_ledger(user_id, created_at DESC);
CREATE INDEX idx_billing_ledger_lot_created
    ON billing_credit_ledger(credit_lot_id, created_at)
    WHERE credit_lot_id IS NOT NULL;
