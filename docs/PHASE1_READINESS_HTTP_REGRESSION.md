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


## API-02 — handlers HTTP de saturación

Se amplió `tests/test_capacity_http.py` con dos pruebas asíncronas que provocan las excepciones a través de rutas temporales registradas en la aplicación FastAPI real:

1. `CapacityExceeded` produce HTTP **503**, cabecera `Retry-After` con el tiempo configurado y mensaje público genérico.
2. `SQLAlchemyPoolTimeout` produce HTTP **503**, `Retry-After: 3` y no revela el diagnóstico interno del pool/driver.

Las rutas temporales se retiran al finalizar cada prueba. No se cambia la lógica de producción ni se conecta a una base de datos real.

**Commit:** `857cad6843dfa4f8b463762bfab3a4dac21c9c1c`.

## Límites

- Las pruebas usan dobles para dependencias; no certifican PostgreSQL, Ollama, Qdrant, Redis ni configuración de staging.
- No habilitan autenticación, no alteran configuración y no ejecutan operaciones de infraestructura.
- No se modificó código de producción.

## Verificación

- Implementación publicada en `agent/chatgpt`.
- CI de `10b0f7a` (run `42497277051`): Python, imagen, Qdrant y browser E2E terminaron en success; el job PostgreSQL figura como `cancelled` pese a que sus pasos de migración e idempotencia aparecen completados. No se considera una ejecución 5/5 aprobada. CI del HEAD nuevo `857cad6`: pendiente de aparecer y revisarse.
