"""Model Router: elige la cadena de modelos (primario + alternativos) según tipo de tarea,
tamaño del prompt, memoria y disponibilidad. Avisa cuando la tarea excede la capacidad razonable del modelo."""
from dataclasses import dataclass, field
from enum import Enum

from core.errors import NoSuitableModel
from core.models import ModelConfig


class TaskKind(str, Enum):
    CHAT = "chat"
    CODE = "code"
    REVIEW = "review"
    PLAN = "plan"
    SUMMARY = "summary"


@dataclass
class RouteDecision:
    model: str
    fallbacks: list[str]
    needs_decomposition: bool = False
    reasons: list[str] = field(default_factory=list)


class ModelRouter:
    """routes: {TaskKind: [nombres de modelo en orden de preferencia]}; "*" sirve de ruta por defecto."""

    def __init__(self, models: list[ModelConfig], routes: dict[str, list[str]], decomposition_ratio: float = 0.7):
        self.models = {m.name: m for m in models}
        self.routes = routes
        self.decomposition_ratio = decomposition_ratio
        if "*" not in routes:
            raise NoSuitableModel("Falta la ruta por defecto '*'")

    def select(self, kind: TaskKind, prompt_tokens: int, available: set[str] | None = None) -> RouteDecision:
        wanted = self.routes.get(kind.value, self.routes["*"])
        reasons: list[str] = []
        usable: list[ModelConfig] = []
        for name in wanted:
            cfg = self.models.get(name)
            if cfg is None:
                reasons.append(f"{name}: no registrado")
            elif available is not None and name not in available:
                reasons.append(f"{name}: no disponible en Ollama")
            elif prompt_tokens + cfg.max_output_tokens > cfg.num_ctx:
                reasons.append(f"{name}: el prompt (~{prompt_tokens} tokens) no cabe en {cfg.num_ctx}")
            else:
                usable.append(cfg)
        if not usable:
            raise NoSuitableModel("; ".join(reasons) or "Sin modelos candidatos")
        primary = usable[0]
        heavy = prompt_tokens > primary.num_ctx * self.decomposition_ratio
        if heavy:
            reasons.append("La tarea ocupa gran parte del contexto: conviene dividirla en etapas")
        return RouteDecision(primary.name, [m.name for m in usable[1:]], heavy, reasons)
