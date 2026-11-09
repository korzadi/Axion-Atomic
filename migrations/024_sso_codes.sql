-- 024: códigos de un solo uso para SSO landing -> AXYRON Studio.
-- No almacena tokens de sesión ni secretos en claro: solo hashes.
CREATE TABLE sso_codes (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    code_hash TEXT NOT NULL UNIQUE CHECK (length(code_hash) = 64),
    state_hash TEXT NOT NULL CHECK (length(state_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX idx_sso_codes_expires
    ON sso_codes(expires_at)
    WHERE consumed_at IS NULL;
