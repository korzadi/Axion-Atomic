# Qwen Engineering — starter

Proyecto independiente para Qwen2.5-Coder-7B-Instruct en VPS de 4 CPU / 16 GB RAM. Se integra con Ollama y Open WebUI existentes. **No despliega ni modifica el VPS.**

## Componentes
- Ollama existente: chat y embeddings.
- FastAPI: API OpenAI-compatible `/v1/chat/completions`.
- PostgreSQL: tareas y aprobaciones.
- Qdrant: índice vectorial RAG.
- Agente: planificación y aprobaciones humanas. No ejecuta comandos ni aplica cambios.
- QLoRA: entrenamiento preparado para GPU externa; no entrenar en el VPS de 16 GB.

## Preparación futura (no ejecutar sin autorización)
1. Copiar `.env.example` a `.env`, cambiar contraseñas y API key.
2. Ajustar `OLLAMA_BASE_URL` al Ollama existente.
3. Descargar en el Ollama existente `qwen2.5-coder:7b-instruct` y `nomic-embed-text`.
4. Revisar puertos y límites de recursos.
5. Con autorización explícita: `docker compose -p qwen-engineering up -d --build`.

API prevista: `http://127.0.0.1:8070/health`.

## Open WebUI
Añadir conexión OpenAI compatible apuntando a `http://HOST:8070/v1`, con la API key configurada y modelo `qwen-engineering`. Si Open WebUI está en Docker, `localhost` apunta a su propio contenedor; usa una dirección de host/red Docker alcanzable. Mantén la API privada.

## Seguridad
- Compose independiente, volúmenes propios y puertos ligados a loopback.
- No monta Docker socket, home del host, `.env` ajenos ni claves.
- Ejecución arbitraria de comandos deshabilitada.
- La aprobación registra una decisión; no ejecuta el plan.
- Documentos recuperados son datos no confiables, nunca instrucciones.
- No indexar secretos, semillas, tokens, dumps ni datos personales.

## Limitaciones
Es un starter funcional, no un agente autónomo de producción ni un modelo ya entrenado. Antes de permitir edición real hacen falta worktrees aislados, generación y revisión de diffs, runner efímero, permisos por proyecto, auditoría y pruebas de seguridad.

# Axion-Atomic
