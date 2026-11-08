"""Medición local del consumo de tokens de Ollama.

Herramienta de diagnóstico de solo lectura: ejecuta unas pocas inferencias
mínimas contra el servicio Ollama configurado y reporta los contadores que
Ollama devuelve (prompt_eval_count, eval_count, duraciones). No envía ni
registra prompts con datos del negocio, no modifica el estado del servicio y
no necesita secretos. Sus resultados son orientativos, no un benchmark de
producción ni una tarifa de costes.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

PROMPTS = {
    "short": "Resume en una frase: qué es una API.",
    "medium": "Explica en tres frases qué es una API REST y cómo difiere de GraphQL.",
}


def measure_chat(base_url: str, model: str, name: str, prompt: str, num_predict: int, num_ctx: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": num_predict, "num_ctx": num_ctx},
    }
    response = httpx.post(base_url.rstrip("/") + "/api/chat", json=payload, timeout=600)
    response.raise_for_status()
    data = response.json()
    return {
        "case": name,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
        "total_duration_ms": round((data.get("total_duration") or 0) / 1e6, 1),
        "prompt_eval_duration_ms": round((data.get("prompt_eval_duration") or 0) / 1e6, 1),
        "eval_duration_ms": round((data.get("eval_duration") or 0) / 1e6, 1),
        "load_duration_ms": round((data.get("load_duration") or 0) / 1e6, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://host.docker.internal:11434",
                        help="URL HTTP de Ollama (por defecto: host.docker.internal:11434)")
    parser.add_argument("--chat-model", default="atomic-code:1.1")
    parser.add_argument("--num-predict", type=int, default=96)
    parser.add_argument("--num-ctx", type=int, default=4096,
                        help="Contexto para la medición; el valor por defecto es 4096 (no 16384) para minimizar coste")
    args = parser.parse_args()

    results = []
    for name, prompt in PROMPTS.items():
        results.append(measure_chat(args.base_url, args.chat_model, name, prompt, args.num_predict, args.num_ctx))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
