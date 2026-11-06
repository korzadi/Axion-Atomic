"""Límite superior pre-inferencia para el contrato de tokenizer de ATOMIC CODE.

La cota UTF-8 solo se admite para el tokenizer byte-fallback Qwen fijado por
la política. Incluye TODOS los mensajes finales enviados a Ollama (system,
historial y RAG), overhead conservador de framing/template y máximo de salida.
No realiza reservas ni escrituras; la capa transaccional debe reservar el valor
devuelto ANTES de llamar al motor.
"""
from __future__ import annotations

from dataclasses import dataclass


POLICY_VERSION = "atomic-code-budget-v1"
SUPPORTED_TOKENIZER_CONTRACT = "qwen2_byte_fallback"


class ContextBudgetExceeded(ValueError):
    """El límite superior no cabe en la ventana de contexto configurada."""


class UnsupportedTokenizerContract(ValueError):
    """No existe una cota segura para el tokenizer/runtime solicitado."""


@dataclass(frozen=True)
class InferenceBudget:
    policy_version: str
    runtime_model: str
    tokenizer_contract: str
    input_tokens_upper_bound: int
    output_tokens_upper_bound: int
    input_weight: int
    output_weight: int
    reserved_credits: int
    context_window: int


def calculate_preflight_budget(
    messages: list[dict],
    max_output_tokens: int,
    context_window: int,
    *,
    runtime_model: str,
    expected_runtime_model: str,
    tokenizer_contract: str,
    input_weight: int = 1,
    output_weight: int = 1,
    framing_tokens_per_message: int = 32,
    template_overhead_tokens: int = 256,
) -> InferenceBudget:
    """Devuelve una reserva máxima conservadora; nunca usa texto del cliente como autoridad."""
    if not isinstance(runtime_model, str) or not runtime_model.strip():
        raise ValueError("runtime_model inválido")
    if runtime_model != expected_runtime_model:
        raise ValueError("El runtime no coincide con el modelo autorizado")
    if tokenizer_contract != SUPPORTED_TOKENIZER_CONTRACT:
        raise UnsupportedTokenizerContract("Tokenizer sin cota superior verificada")
    numeric = (
        max_output_tokens, context_window, input_weight, output_weight,
        framing_tokens_per_message, template_overhead_tokens,
    )
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in numeric):
        raise ValueError("Los límites y ponderadores deben ser enteros no negativos")
    if max_output_tokens < 1 or context_window < 1:
        raise ValueError("La salida y la ventana de contexto deben ser positivas")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Se requieren los mensajes completos de inferencia")

    input_upper = template_overhead_tokens
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Mensaje de inferencia inválido")
        role = message.get("role")
        text = message.get("content")
        if role not in ("system", "user", "assistant") or not isinstance(text, str):
            raise ValueError("Rol o contenido de mensaje inválido")
        # Qwen byte-fallback: el número de tokens del contenido no supera
        # el número de bytes UTF-8. El framing se reserva aparte por mensaje.
        input_upper += len(text.encode("utf-8")) + framing_tokens_per_message

    if max_output_tokens > context_window:
        raise ContextBudgetExceeded("La salida solicitada supera la ventana de contexto")
    total_token_bound = input_upper + max_output_tokens
    if total_token_bound > context_window:
        raise ContextBudgetExceeded("El prompt completo y la salida máxima no caben en contexto")

    reserved = input_upper * input_weight + max_output_tokens * output_weight
    return InferenceBudget(
        policy_version=POLICY_VERSION,
        runtime_model=runtime_model,
        tokenizer_contract=tokenizer_contract,
        input_tokens_upper_bound=input_upper,
        output_tokens_upper_bound=max_output_tokens,
        input_weight=input_weight,
        output_weight=output_weight,
        reserved_credits=reserved,
        context_window=context_window,
    )
