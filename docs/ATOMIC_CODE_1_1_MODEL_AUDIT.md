# Auditoría inicial del modelo ATOMIC CODE 1.1

Fecha de consulta: 2026-11-05

Repositorio oficial: https://huggingface.co/Korzadi/Atomic-Code-1.1

## Evidencia pública revisada

La ficha pública del repositorio declara:

- Tarea: generación de texto.
- Arquitectura: Qwen2 / Qwen2ForCausalLM.
- Modelo base declarado: Qwen2.5-Coder-7B-Instruct.
- Tamaño declarado: aproximadamente 7.61B parámetros.
- Hidden size: 3584.
- Vocabulario: 152064.
- Contexto declarado: 32768 tokens.
- Pesos consolidados en Safetensors, BF16/FP16.
- Licencia declarada: Apache-2.0.
- Tokenizer disponible en la distribución consolidada: tokenizer.json y tokenizer_config.json.
- Plantilla de chat Jinja disponible en la raíz del repositorio.
- Distribución GGUF: atomic-code-Q4_K_M.gguf, 4.68 GB.
- Distribución consolidada: cuatro shards Safetensors, aproximadamente 15.2 GB en total.
- Adaptador LoRA en la raíz, aproximadamente 323 MB.

La página oficial publica explícitamente el uso con Ollama mediante el identificador:

`hf.co/Korzadi/Atomic-Code-1.1:Q4_K_M`

Por tanto, existe una ruta de distribución GGUF documentada por el propio repositorio para Ollama. No se necesita sustituir ATOMIC CODE 1.1 por otro modelo.

## Decisión técnica provisional

1. Mantener ATOMIC CODE 1.1 como modelo principal.
2. Utilizar la variante GGUF Q4_K_M como primera candidata para el VPS de 4 CPU / 16 GB RAM.
3. Configurar el identificador de modelo como parámetro, sin ejecutar pulls automáticos ni modificar Ollama.
4. Mantener un contexto operativo inicial conservador; el contexto máximo declarado por la ficha no equivale a memoria disponible ni a rendimiento medido.
5. Conservar la ruta Transformers/Safetensors como alternativa para GPU externa, no como ruta de inferencia recomendada para el VPS CPU-only.

## Límites y verificaciones pendientes

- No se ejecutó inferencia en el Ollama existente.
- No se descargó ni importó el GGUF.
- No se modificó Ollama ni sus modelos.
- No se midió RAM máxima, latencia, tokens/segundo ni estabilidad con concurrencia.
- No se inspeccionó el contenido binario ni se validó el hash de los pesos.
- La ficha mezcla referencias de versión v1.1 (adaptador) y v1.2 (checkpoint consolidado). La correspondencia exacta entre el nombre público 1.1 y los artefactos consolidados debe confirmarse antes de congelar una versión de producción.
- Aunque la licencia declarada es Apache-2.0, la revisión legal de redistribución debe conservar la evidencia y revisar cualquier licencia de componentes o datasets de origen.

## Resultado

**Compatibilidad de formato con Ollama: documentada por el repositorio oficial para la variante GGUF Q4_K_M.**

**Compatibilidad operativa en el Ollama ya instalado: pendiente de prueba autorizada.**

**Adecuación a 16 GB RAM: plausible por el tamaño del archivo cuantizado, pero no demostrada hasta medir memoria pico y rendimiento real.**

## Fuentes

- Ficha oficial y configuración de uso: https://huggingface.co/Korzadi/Atomic-Code-1.1
- Archivos de la distribución consolidada: https://huggingface.co/Korzadi/Atomic-Code-1.1/tree/main/consolidated
- GGUF Q4_K_M: https://huggingface.co/Korzadi/Atomic-Code-1.1/tree/main/gguf
