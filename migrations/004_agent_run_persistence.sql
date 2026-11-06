-- 004: estado persistente de ejecuciones y acciones del agente.
-- Aditiva: no modifica ni elimina tablas o datos existentes.
CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','awaiting_approval','done','failed','max_steps','needs_reconciliation')),
    final TEXT,
    error TEXT,
    messages TEXT NOT NULL,
    pending_actions TEXT NOT NULL DEFAULT '[]',
    steps INTEGER NOT NULL DEFAULT 0 CHECK (steps >= 0),
    parse_failures INTEGER NOT NULL DEFAULT 0 CHECK (parse_failures >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_project_updated
    ON agent_runs(project_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_project_status
    ON agent_runs(project_id, status);

CREATE TABLE IF NOT EXISTS agent_run_actions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tool TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    args_json TEXT NOT NULL,
    proposal_id TEXT,
    summary TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending','approved','running','applied','failed','rejected','expired')),
    result TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(run_id, action_hash)
);
CREATE INDEX IF NOT EXISTS idx_agent_run_actions_project_state
    ON agent_run_actions(project_id, state);
CREATE INDEX IF NOT EXISTS idx_agent_run_actions_run_created
    ON agent_run_actions(run_id, created_at);
