-- 017: RBAC global separado de las membresías de proyecto.
-- No asigna administradores automáticamente y no concede permisos por email.
CREATE TABLE global_role_assignments (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    role TEXT NOT NULL CHECK (role IN ('platform_admin','billing_admin','billing_support','billing_readonly')),
    granted_by TEXT REFERENCES users(id) ON DELETE RESTRICT,
    grant_reason TEXT NOT NULL CHECK (length(grant_reason) BETWEEN 8 AND 1000),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    revoked_by TEXT REFERENCES users(id) ON DELETE RESTRICT,
    revoke_reason TEXT,
    CHECK (
      (revoked_at IS NULL AND revoked_by IS NULL AND revoke_reason IS NULL)
      OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
          AND revoke_reason IS NOT NULL AND length(revoke_reason) BETWEEN 8 AND 1000)
    )
);
CREATE UNIQUE INDEX idx_global_role_one_active_assignment
 ON global_role_assignments(user_id, role) WHERE revoked_at IS NULL;
CREATE INDEX idx_global_role_assignments_user
 ON global_role_assignments(user_id, granted_at DESC);

CREATE TABLE global_admin_audit_events (
    id UUID PRIMARY KEY,
    actor_user_id TEXT REFERENCES users(id) ON DELETE RESTRICT,
    target_user_id TEXT REFERENCES users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL CHECK (length(action) BETWEEN 1 AND 100),
    role TEXT CHECK (role IS NULL OR role IN ('platform_admin','billing_admin','billing_support','billing_readonly')),
    reason TEXT NOT NULL CHECK (length(reason) BETWEEN 8 AND 1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_global_admin_audit_created ON global_admin_audit_events(created_at DESC);
CREATE OR REPLACE FUNCTION global_admin_audit_reject_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'global_admin_audit_events es append-only';
END;
$$;
CREATE TRIGGER trg_global_admin_audit_no_update_delete
 BEFORE UPDATE OR DELETE ON global_admin_audit_events
 FOR EACH ROW EXECUTE FUNCTION global_admin_audit_reject_mutation();
CREATE TRIGGER trg_global_admin_audit_no_truncate
 BEFORE TRUNCATE ON global_admin_audit_events
 FOR EACH STATEMENT EXECUTE FUNCTION global_admin_audit_reject_mutation();
