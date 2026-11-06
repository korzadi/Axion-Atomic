-- 009: auditoría inmutable de recuperación de reservas inciertas.
-- Solo permite registrar decisiones posteriores verificadas; no habilita endpoints ni cobros.
CREATE TABLE billing_reservation_reconciliations (
    id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL REFERENCES billing_usage_reservations(id) ON DELETE RESTRICT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    actor_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    resolution TEXT NOT NULL CHECK (resolution IN ('confirmed_no_execution')),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 1 AND 200),
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 10 AND 1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_billing_reconciliations_reservation
    ON billing_reservation_reconciliations(reservation_id, created_at);

CREATE OR REPLACE FUNCTION billing_reject_reconciliation_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'billing_reservation_reconciliations es append-only';
END;
$$;
CREATE TRIGGER trg_billing_reconciliations_no_update_delete
    BEFORE UPDATE OR DELETE ON billing_reservation_reconciliations
    FOR EACH ROW EXECUTE FUNCTION billing_reject_reconciliation_mutation();
CREATE TRIGGER trg_billing_reconciliations_no_truncate
    BEFORE TRUNCATE ON billing_reservation_reconciliations
    FOR EACH STATEMENT EXECUTE FUNCTION billing_reject_reconciliation_mutation();
