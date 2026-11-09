-- Rollback manual y destructivo: elimina solicitudes de eliminación de cuenta.
-- Solo ejecutar con autorización explícita; puede afectar trazabilidad operativa.
DROP TABLE IF EXISTS account_deletion_requests;
