-- 010: persistencia cifrada de resultados para recuperación idempotente.
-- El servicio solo almacena ciphertext; el cifrado/descifrado y sus claves
-- pertenecen a un proveedor de claves externo a la base de datos.
CREATE TABLE billing_inference_executions (
    id UUID PRIMARY KEY,
    reservation_id UUID NOT NULL UNIQUE
        REFERENCES billing_usage_reservations(id) ON DELETE RESTRICT,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('started', 'completed', 'unknown', 'review')),
    result_ciphertext BYTEA,
    result_nonce BYTEA,
    result_key_id TEXT,
    result_sha256 CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CHECK (
        (state = 'completed'
         AND result_ciphertext IS NOT NULL AND octet_length(result_ciphertext) > 0
         AND result_nonce IS NOT NULL AND octet_length(result_nonce) > 0
         AND result_key_id IS NOT NULL AND length(result_key_id) BETWEEN 1 AND 128
         AND result_sha256 ~ '^[0-9a-f]{64}$'
         AND completed_at IS NOT NULL)
        OR
        (state <> 'completed'
         AND result_ciphertext IS NULL AND result_nonce IS NULL
         AND result_key_id IS NULL AND result_sha256 IS NULL
         AND completed_at IS NULL)
    )
);
CREATE INDEX idx_billing_execution_recovery
    ON billing_inference_executions(state, updated_at);
