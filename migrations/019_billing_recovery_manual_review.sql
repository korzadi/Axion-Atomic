-- 019: detener reintentos automáticos repetidos y dejar evidencia para revisión manual.
-- No modifica saldos, reservas ni el ciphertext completado.
ALTER TABLE billing_inference_executions
    ADD COLUMN recovery_requires_review BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX idx_billing_execution_recovery_review
    ON billing_inference_executions(recovery_last_attempt_at, id)
    WHERE state = 'completed' AND recovery_requires_review = TRUE;
