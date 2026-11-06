-- 003: aprobaciones por acción (persistentes) y registro de auditoría con cadena de hashes. Solo AÑADE tablas.
-- La tabla 'approvals' del starter (aprobaciones a nivel de plan) se conserva sin cambios.
CREATE TABLE IF NOT EXISTS action_approvals (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 tool TEXT NOT NULL,
 what TEXT NOT NULL,
 why TEXT NOT NULL,
 resources TEXT NOT NULL,
 modification TEXT NOT NULL,
 risks TEXT NOT NULL,
 expected TEXT NOT NULL,
 fingerprint TEXT NOT NULL,
 action_hash TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','approved','rejected','used')),
 reviewer TEXT,
 note TEXT,
 created_at TIMESTAMPTZ NOT NULL,
 expires_at TIMESTAMPTZ NOT NULL,
 decided_at TIMESTAMPTZ,
 used_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_action_approvals_project_state ON action_approvals(project_id, state);
CREATE TABLE IF NOT EXISTS audit_log (
 seq INTEGER PRIMARY KEY,
 ts TIMESTAMPTZ NOT NULL,
 project_id TEXT,
 actor TEXT NOT NULL,
 event TEXT NOT NULL,
 data TEXT NOT NULL,
 prev_hash TEXT NOT NULL,
 hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_audit_log_project ON audit_log(project_id, seq);
CREATE TABLE IF NOT EXISTS audit_chain_head (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 last_hash TEXT NOT NULL,
 seq INTEGER NOT NULL
);
INSERT INTO audit_chain_head (id, last_hash, seq) VALUES (1, '', 0) ON CONFLICT (id) DO NOTHING;
