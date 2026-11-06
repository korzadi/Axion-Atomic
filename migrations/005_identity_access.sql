-- 005: identidad, sesiones revocables y pertenencia explícita a proyectos.
-- Migración aditiva: no modifica ni elimina datos ni tablas anteriores.
CREATE TABLE IF NOT EXISTS axion_users (
 id TEXT PRIMARY KEY,
 email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK (role IN ('admin','member')),
 active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS axion_sessions (
 token_hash TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES axion_users(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL,
 revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_axion_sessions_user_expiry ON axion_sessions(user_id, expires_at);
CREATE TABLE IF NOT EXISTS project_memberships (
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES axion_users(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK (role IN ('owner','editor','viewer')),
 created_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(project_id,user_id)
);
CREATE INDEX IF NOT EXISTS idx_project_memberships_user ON project_memberships(user_id, project_id);
