-- 022: permitir la cancelación explícita de ejecuciones que esperan aprobación.
-- Aditiva para el flujo: no elimina datos ni modifica acciones ya aplicadas.
ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_status_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_status_check
    CHECK (status IN ('running','awaiting_approval','done','failed','max_steps','needs_reconciliation','cancelled'));
