-- 025: solicitudes de eliminación de cuenta (autoservicio controlado).
-- Aditiva. No elimina datos automáticamente: registra una solicitud auditable para
-- revisión del operador. Evita duplicados pendientes por usuario.
CREATE TABLE IF NOT EXISTS account_deletion_requests (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'cancelled', 'processed')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    note TEXT,
    processed_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    CHECK ((status = 'processed') = (processed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_account_deletion_requests_pending_user
    ON account_deletion_requests(user_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_status
    ON account_deletion_requests(status, requested_at DESC);
