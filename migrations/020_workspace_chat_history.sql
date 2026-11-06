-- 020: historial de chat privado por usuario y proyecto.
-- Aditiva: conserva los proyectos y los datos existentes.
CREATE TABLE IF NOT EXISTS workspace_chat_history (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, project_id),
    CONSTRAINT workspace_chat_history_messages_array
        CHECK (jsonb_typeof(messages) = 'array'),
    CONSTRAINT workspace_chat_history_messages_limit
        CHECK (jsonb_array_length(messages) <= 100)
);
CREATE INDEX IF NOT EXISTS idx_workspace_chat_history_project_updated
    ON workspace_chat_history(project_id, updated_at DESC);
