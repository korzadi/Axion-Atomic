-- REVERSIÓN MANUAL de 003. DESTRUCTIVA (borra aprobaciones y auditoría). No la ejecuta el migrador;
-- requiere autorización expresa del propietario y copia de seguridad previa.
DROP TABLE IF EXISTS audit_chain_head;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS action_approvals;
DELETE FROM schema_migrations WHERE version = '003';
