CREATE TABLE IF NOT EXISTS approvals (
 id BIGSERIAL PRIMARY KEY, project_id TEXT NOT NULL, goal TEXT NOT NULL,
 plan_json JSONB NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
 reviewer TEXT, reviewer_note TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_approvals_status_created ON approvals(status,created_at);
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, repository_path TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS knowledge_sources (
 id BIGSERIAL PRIMARY KEY, project_id TEXT, source TEXT NOT NULL, checksum TEXT,
 indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_tasks (
 id BIGSERIAL PRIMARY KEY, project_id TEXT NOT NULL, goal TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_actions (
 id BIGSERIAL PRIMARY KEY, task_id BIGINT REFERENCES agent_tasks(id),
 action_type TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}'::jsonb,
 status TEXT NOT NULL DEFAULT 'proposed', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS model_versions (
 id BIGSERIAL PRIMARY KEY, model_name TEXT NOT NULL, quantization TEXT,
 adapter_uri TEXT, dataset_version TEXT,
 evaluation_json JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
