-- 012: tokens de recuperación de contraseña de un solo uso.
-- Solo almacena SHA-256; el token en claro se entrega exclusivamente al adaptador de correo.
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CHECK (expires_at > created_at),
    CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);
CREATE UNIQUE INDEX idx_password_reset_one_open_per_user
    ON password_reset_tokens(user_id) WHERE consumed_at IS NULL;
CREATE INDEX idx_password_reset_expiry
    ON password_reset_tokens(expires_at) WHERE consumed_at IS NULL;
