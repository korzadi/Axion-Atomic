-- 021: persistencia MFA segura. Los secretos se guardan cifrados por la aplicación.
-- La clave AES nunca se almacena en PostgreSQL; se inyecta desde runtime/secret manager.
CREATE TABLE user_mfa_credentials (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('pending', 'enabled')),
    pending_secret_ciphertext BYTEA,
    pending_secret_nonce BYTEA,
    pending_secret_key_id TEXT,
    secret_ciphertext BYTEA,
    secret_nonce BYTEA,
    secret_key_id TEXT,
    last_accepted_counter BIGINT NOT NULL DEFAULT -1 CHECK (last_accepted_counter >= -1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    enabled_at TIMESTAMPTZ,
    CHECK (
      (state = 'pending'
       AND pending_secret_ciphertext IS NOT NULL
       AND octet_length(pending_secret_nonce) = 12
       AND pending_secret_key_id IS NOT NULL
       AND secret_ciphertext IS NULL
       AND secret_nonce IS NULL
       AND secret_key_id IS NULL
       AND enabled_at IS NULL)
      OR
      (state = 'enabled'
       AND pending_secret_ciphertext IS NULL
       AND pending_secret_nonce IS NULL
       AND pending_secret_key_id IS NULL
       AND secret_ciphertext IS NOT NULL
       AND octet_length(secret_nonce) = 12
       AND secret_key_id IS NOT NULL
       AND enabled_at IS NOT NULL)
    )
);

CREATE TABLE user_mfa_recovery_codes (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    code_hash CHAR(64) NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    used_at TIMESTAMPTZ,
    UNIQUE (user_id, code_hash)
);
CREATE INDEX idx_user_mfa_recovery_unused
 ON user_mfa_recovery_codes(user_id, created_at)
 WHERE used_at IS NULL;

-- El token opaco del desafío solo se entrega al cliente; PostgreSQL conserva su hash.
CREATE TABLE auth_mfa_challenges (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    challenge_hash CHAR(64) NOT NULL UNIQUE CHECK (challenge_hash ~ '^[0-9a-f]{64}$'),
    purpose TEXT NOT NULL CHECK (purpose IN ('login', 'oauth')),
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 10),
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_auth_mfa_challenges_user_expiry
 ON auth_mfa_challenges(user_id, expires_at)
 WHERE consumed_at IS NULL;

CREATE TABLE user_mfa_audit_events (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (action IN (
      'enrollment_started', 'enrollment_confirmed', 'challenge_succeeded',
      'challenge_failed', 'recovery_code_used', 'mfa_disabled', 'secret_rotated'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_mfa_audit_user_created
 ON user_mfa_audit_events(user_id, created_at DESC);

CREATE OR REPLACE FUNCTION user_mfa_audit_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'user_mfa_audit_events es append-only';
END;
$$;
CREATE TRIGGER trg_user_mfa_audit_no_update_delete
 BEFORE UPDATE OR DELETE ON user_mfa_audit_events
 FOR EACH ROW EXECUTE FUNCTION user_mfa_audit_reject_mutation();
CREATE TRIGGER trg_user_mfa_audit_no_truncate
 BEFORE TRUNCATE ON user_mfa_audit_events
 FOR EACH STATEMENT EXECUTE FUNCTION user_mfa_audit_reject_mutation();
