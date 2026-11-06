-- 011: tokens de verificación de correo de un solo uso.
-- Solo se almacena SHA-256 del token; el valor original se entrega al adaptador de correo.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;

CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CHECK (expires_at > created_at),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE UNIQUE INDEX idx_email_verification_one_open_per_user
    ON email_verification_tokens(user_id)
    WHERE consumed_at IS NULL;
CREATE INDEX idx_email_verification_expiry
    ON email_verification_tokens(expires_at)
    WHERE consumed_at IS NULL;
