-- 006: persistencia de medición de inferencia en modo observación.
-- Solo añade una tabla; no habilita cuotas, créditos, facturación ni pagos.
-- No almacena prompts, respuestas, secretos ni contenido RAG.
CREATE TABLE inference_usage_events (
    request_id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    requested_model TEXT NOT NULL CHECK (length(requested_model) BETWEEN 1 AND 200),
    returned_model TEXT CHECK (returned_model IS NULL OR length(returned_model) <= 200),
    prompt_tokens BIGINT CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    output_tokens BIGINT CHECK (output_tokens IS NULL OR output_tokens >= 0),
    total_duration_ns BIGINT CHECK (total_duration_ns IS NULL OR total_duration_ns >= 0),
    load_duration_ns BIGINT CHECK (load_duration_ns IS NULL OR load_duration_ns >= 0),
    prompt_eval_duration_ns BIGINT CHECK (prompt_eval_duration_ns IS NULL OR prompt_eval_duration_ns >= 0),
    eval_duration_ns BIGINT CHECK (eval_duration_ns IS NULL OR eval_duration_ns >= 0),
    usage_source TEXT NOT NULL CHECK (usage_source IN ('ollama_response', 'unavailable')),
    done BOOLEAN,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_inference_usage_user_observed
    ON inference_usage_events(user_id, observed_at DESC);
CREATE INDEX idx_inference_usage_project_observed
    ON inference_usage_events(project_id, observed_at DESC);
CREATE INDEX idx_inference_usage_model_observed
    ON inference_usage_events(requested_model, observed_at DESC);
