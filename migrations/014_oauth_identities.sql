-- 014: identidades externas OAuth y estados de autorización de un solo uso.
CREATE TABLE IF NOT EXISTS oauth_identities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('google','github')),
    provider_subject TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(provider, provider_subject),
    UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities(user_id);
CREATE TABLE IF NOT EXISTS oauth_login_states (
    state_hash CHAR(64) PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('google','github')),
    nonce TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_oauth_login_states_expiry ON oauth_login_states(expires_at) WHERE consumed_at IS NULL;
