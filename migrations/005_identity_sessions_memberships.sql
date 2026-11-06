-- 005: identidad, sesiones y membresías multiusuario.
-- Migración estrictamente aditiva: no altera ni elimina tablas o datos existentes.
-- Los IDs y hashes se generan en la aplicación; nunca se almacenan tokens de sesión en claro.

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled', 'pending_verification')),
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    csrf_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    user_agent_hash CHAR(64),
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_expiry
    ON user_sessions(user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_user_sessions_active
    ON user_sessions(token_hash, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS project_memberships (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'editor', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(project_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_project_memberships_user
    ON project_memberships(user_id, project_id);
CREATE INDEX IF NOT EXISTS idx_project_memberships_project_role
    ON project_memberships(project_id, role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_single_owner
    ON project_memberships(project_id)
    WHERE role = 'owner';
