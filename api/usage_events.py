"""Persistencia best-effort de métricas de inferencia en Shadow Mode.

No realiza cargos, reservas ni mutaciones de saldo. Los contadores desconocidos
se conservan como NULL y nunca se convierten en cero.
"""
from sqlalchemy import text

from api.database import engine


_INSERT_USAGE = text("""
    INSERT INTO inference_usage_events (
        request_id, user_id, project_id, requested_model, returned_model,
        prompt_tokens, output_tokens, total_duration_ns, load_duration_ns,
        prompt_eval_duration_ns, eval_duration_ns, usage_source, done
    ) VALUES (
        CAST(:request_id AS UUID), :user_id, :project_id, :requested_model, :returned_model,
        :prompt_tokens, :output_tokens, :total_duration_ns, :load_duration_ns,
        :prompt_eval_duration_ns, :eval_duration_ns, :usage_source, :done
    )
    ON CONFLICT (request_id) DO NOTHING
""")


def persist_shadow_usage_event(*, request_id: str, user_id: str, project_id: str, result) -> None:
    """Guarda una medición sin contenido conversacional y con UUID idempotente."""
    with engine.begin() as conn:
        conn.execute(_INSERT_USAGE, {
            "request_id": request_id,
            "user_id": str(user_id),
            "project_id": project_id,
            "requested_model": result.requested_model,
            "returned_model": result.returned_model,
            "prompt_tokens": result.prompt_eval_count,
            "output_tokens": result.eval_count,
            "total_duration_ns": result.total_duration_ns,
            "load_duration_ns": result.load_duration_ns,
            "prompt_eval_duration_ns": result.prompt_eval_duration_ns,
            "eval_duration_ns": result.eval_duration_ns,
            "usage_source": result.usage_source,
            "done": result.done,
        })
