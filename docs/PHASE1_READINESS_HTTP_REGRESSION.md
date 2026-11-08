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

## Configuración OAuth/Qdrant — origen HTTPS estricto

- `api/config.py:is_public_https_origin` rechaza ahora espacios, tabs, saltos de línea y controles ASCII dentro del origen antes de llamar a `urlsplit`.
- Motivo: `urllib.parse.urlsplit` elimina tabs y saltos de línea incrustados; no se debe aceptar una cadena malformada normalizándola silenciosamente a otro hostname.
- Regresiones en `tests/test_config.py` para tabs y saltos de línea en QDRANT_URL y OAUTH_PUBLIC_BASE_URL.
- No se cambia el origen configurado válido ni se modifica ningún secreto.

## Corrección de enrutamiento de las pruebas HTTP — 2026-11-08

- La ejecución CI 42497775952 detectó que las dos pruebas de handlers recibían 404: las rutas temporales se añadían después del montaje catch-all axyron-static.
- tests/test_capacity_http.py ahora coloca cada ruta temporal antes del montaje estático, la invoca por ASGI y la retira en finally. No cambia handlers ni rutas productivas.
- Commit correctivo: c010da6771f12573e8c2424fe91c06e5dc916acd.
- CI del SHA exacto: run 42498371877, cinco de cinco jobs completados con success: python-tests, postgres-migrations, qdrant-cloud-integration, studio-browser-e2e y container-image-build.
- El job Python terminó correctamente; PostgreSQL aplicó migraciones y verificó idempotencia/esquema; Qdrant, E2E de navegador y build/smoke de imagen también terminaron correctamente.
- Esta evidencia certifica el HEAD indicado, no SMTP/OAuth real, staging ni aceptación funcional externa. Fase 1 permanece abierta.

## Aislamiento multi-proyecto contra PostgreSQL real de CI — 2026-11-08

- Se añadió `tests/test_workspace_authorization_postgres.py` para probar la consulta de autorización de producción (`api.auth.authorize_project`) contra PostgreSQL 16 efímero, después de aplicar las migraciones reales.
- La prueba crea dos usuarios y dos proyectos independientes con membresías owner separadas. Verifica que el usuario A accede a A, no puede acceder a B aunque B exista y recibe el mismo 404 ante un rol insuficiente.
- Los registros usan identificadores únicos y se eliminan en `finally`; no reutiliza datos, credenciales ni tablas de producción.
- Se incorporó el archivo al job `postgres-migrations` de `.github/workflows/ci.yml`.
- Commits: `6f4938026d2f1d32d21ff77db1c08c65276078c1` (prueba) y `74fe1b5cff7078d5eac82cc0e2e407effa82c3d9` (CI).
- La prueba HTTP previa de roles sigue complementando este test: la nueva cobertura valida la consulta SQL real y la separación entre dos proyectos persistidos, no solo mocks.
- CI del commit `983a145bd1f8d220782bd924c65ba5d34aa0a901`: 5/5 jobs aprobados (run `42498759087`). Esta ejecución antecede a la nueva prueba PostgreSQL y no la cubre.
- CI del nuevo HEAD `74fe1b5cff7078d5eac82cc0e2e407effa82c3d9`: pendiente de ejecución/confirmación. No se declara aprobada la prueba hasta que el job PostgreSQL del SHA exacto termine en success.
- No se modificaron rutas de producción, frontend, ramas de OpenCode, `main`, VPS, datos persistentes ni configuración operativa.
