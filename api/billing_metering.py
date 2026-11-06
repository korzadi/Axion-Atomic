"""Conversión segura de métricas finales de inferencia a créditos.

No reserva ni cobra. Produce una instantánea determinista que la capa de
orquestación puede pasar al servicio transaccional después de validar el plan.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.billing_policy import UsageUnavailable, credits_for_usage


@dataclass(frozen=True)
class ModelRatePolicy:
    model_name: str
    version: str
    input_weight: int = 1
    output_weight: int = 1
    enabled: bool = False


@dataclass(frozen=True)
class InferenceCharge:
    model_name: str
    policy_version: str
    prompt_tokens: int
    output_tokens: int
    input_weight: int
    output_weight: int
    credits: int


def calculate_inference_charge(result, policy: ModelRatePolicy) -> InferenceCharge:
    """Calcula créditos solo con resultado final, medido y explícitamente habilitado."""
    if policy.enabled is not True:
        raise PermissionError("La facturación de este modelo no está habilitada")
    if (
        not isinstance(policy.model_name, str) or not policy.model_name.strip()
        or not isinstance(policy.version, str) or not policy.version.strip()
    ):
        raise ValueError("La política del modelo requiere nombre y versión")
    if result.requested_model != policy.model_name:
        raise ValueError("El modelo solicitado no coincide con la política de precios")
    if result.done is not True:
        raise UsageUnavailable("La inferencia no confirmó un resultado final")
    if result.usage_source != "ollama_response":
        raise UsageUnavailable("La fuente de uso no permite una liquidación verificable")
    if result.prompt_eval_count is None or result.eval_count is None:
        raise UsageUnavailable("Ollama no proporcionó todos los contadores de tokens")

    credits = credits_for_usage(
        result.prompt_eval_count,
        result.eval_count,
        input_weight=policy.input_weight,
        output_weight=policy.output_weight,
    )
    return InferenceCharge(
        model_name=policy.model_name,
        policy_version=policy.version,
        prompt_tokens=result.prompt_eval_count,
        output_tokens=result.eval_count,
        input_weight=policy.input_weight,
        output_weight=policy.output_weight,
        credits=credits,
    )
