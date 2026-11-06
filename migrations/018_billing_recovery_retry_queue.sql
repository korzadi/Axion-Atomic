-- 018: backoff y exclusión atómica de workers de recuperación.
-- No altera reservas, saldos ni habilita facturación.
ALTER TABLE billing_inference_executions
    ADD COLUMN recovery_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (recovery_attempts >= 0),
    ADD COLUMN recovery_next_attempt_at TIMESTAMPTZ,
    ADD COLUMN recovery_last_attempt_at TIMESTAMPTZ,
    ADD COLUMN recovery_last_error_code TEXT,
    ADD COLUMN recovery_settled_at TIMESTAMPTZ;

UPDATE billing_inference_executions
SET recovery_next_attempt_at = now()
WHERE state = 'completed';

CREATE INDEX idx_billing_execution_recovery_due
    ON billing_inference_executions(recovery_next_attempt_at, completed_at, id)
    WHERE state = 'completed';
