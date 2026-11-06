"""Preflight unificado y fail-closed para futuras solicitudes facturables.

No reserva créditos ni llama a Ollama. El caller debe pasar exactamente los
mensajes finales que enviará al runtime y evidencia explícita de verificación
del tokenizer para el artefacto desplegado.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.billing_budget import InferenceBudget, calculate_preflight_budget
from api.billing_request_fingerprint import billing_request_fingerprint


class TokenizerVerificationRequired(RuntimeError):
    """La facturación no puede estimar tokens sin verificar el artefacto real."""


@dataclass(frozen=True)
class BillingPreflight:
    payload_sha256: str
    budget: InferenceBudget


def prepare_billing_preflight(
    *,
    user_id: str,
    project_id: str,
    public_model: str,
    runtime_model: str,
    expected_runtime_model: str,
    final_messages: list[dict],
    temperature: float,
    max_output_tokens: int,
    context_window: int,
    tokenizer_contract: str,
    tokenizer_verified: bool,
) -> BillingPreflight:
    """Calcula presupuesto y fingerprint sobre el contexto íntegro final."""
    if tokenizer_verified is not True:
        raise TokenizerVerificationRequired(
            "El tokenizer/Modelfile/template del runtime no está verificado"
        )
    if public_model != "atomic-code":
        raise ValueError("Modelo público no habilitado para facturación")
    budget = calculate_preflight_budget(
        final_messages,
        max_output_tokens,
        context_window,
        runtime_model=runtime_model,
        expected_runtime_model=expected_runtime_model,
        tokenizer_contract=tokenizer_contract,
    )
    fingerprint = billing_request_fingerprint(
        user_id=user_id,
        project_id=project_id,
        model=public_model,
        messages=final_messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        policy_version=budget.policy_version,
    )
    return BillingPreflight(payload_sha256=fingerprint, budget=budget)
