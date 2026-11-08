# Fase 1 — regresión HTTP de readiness

**Rama:** `agent/chatgpt`  
**Área:** API-02 / ARC-01  
**Commits de implementación:** `231fed410c1f23c3daaa13a7bb9d414331e82154`, `c5bc2f49a5eacbbae4bc3eb0f33ac3fe5a4f3d19`

## Brecha abordada

Las pruebas existentes de `/health/readiness` invocaban directamente la función Python. Eso verificaba la lógica de combinación, pero no el contrato HTTP registrado en FastAPI.

## Cobertura añadida

En `tests/test_api_health.py` se añadieron tres pruebas asíncronas con `httpx.ASGITransport`, sin servicios externos:

1. La ruta HTTP devuelve **503** y `status=blocked` cuando falla una dependencia crítica; conserva el diagnóstico seguro y no expone el texto interno de la excepción.
2. La ruta HTTP devuelve **200** cuando los controles requeridos están listos, aunque Redis (dependencia opcional) esté degradado; el estado opcional se conserva en la respuesta.
3. La ruta HTTP `/health/live` devuelve **200** y `alive` sin invocar chequeos de dependencias, separando liveness de readiness.

## Límites

- Las pruebas usan dobles para dependencias; no certifican PostgreSQL, Ollama, Qdrant, Redis ni configuración de staging.
- No habilitan autenticación, no alteran configuración y no ejecutan operaciones de infraestructura.
- No se modificó código de producción.

## Verificación

- Implementación publicada en `agent/chatgpt`.
- CI del commit nuevo: pendiente de resultado al crear este documento. No marcar como aprobada hasta revisar los cinco jobs del SHA correspondiente.
