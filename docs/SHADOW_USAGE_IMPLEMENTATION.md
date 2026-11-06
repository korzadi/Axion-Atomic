# AXION ATOMIC — Implementación inicial de medición en shadow mode

**Estado:** código publicado en `main`; ejecución de pruebas pendiente.  
**Alcance:** preservar la respuesta pública del chat y observar los metadatos que Ollama devuelve. No es facturación ni contabilidad.

## Cambios

- `api/ollama.py` incorpora el resultado inmutable `InferenceResult` y `parse_chat_response()`.
- `chat_with_usage()` conserva texto, modelo solicitado/devuelto, estado `done`, contadores de prompt/output y duraciones en nanosegundos.
- Los contadores ausentes o inválidos quedan como `None`; nunca se convierten silenciosamente en cero. Los booleanos, negativos, strings y floats no se aceptan como contadores.
- La función pública previa `chat()` continúa devolviendo únicamente texto para no romper consumidores existentes.
- `/workspace/chat/completions` usa el resultado tipado y emite un evento JSON de observación con usuario autenticado, proyecto, modelos, contadores y duraciones.
- La respuesta pública mantiene la estructura previa y no expone los metadatos nuevos.
- La ruta heredada `/v1` no se incorpora a medición individual.
- `tests/test_ollama_usage.py` cubre parsing completo, contadores ausentes/inválidos, contenido inválido, modelos solicitado/devuelto, petición HTTP no streaming, propagación de timeout y compatibilidad del wrapper `chat()`.
- `tests/test_workspace_role_matrix_http.py` se actualizó para simular el contrato `InferenceResult`, comprobar la respuesta del endpoint y verificar que el evento de observación no contiene el texto del usuario.

## Límites deliberados

- Shadow mode no crea registros persistentes en PostgreSQL, saldos, créditos, reservas, cuotas ni costes.
- No bloquea peticiones ni cambia precios o límites.
- No hay idempotencia económica ni conciliación porque todavía no existe ledger.
- La emisión usa el logger `axion.usage.shadow`; el entorno de ejecución debe configurar nivel INFO y retención/acceso adecuados para que los eventos se conserven. Los logs no deben tratarse como libro contable.
- Los contadores solo reflejan lo que devuelve Ollama. Si faltan, el evento marca `usage_source=unavailable`.
- No se mide aún latencia de extremo a extremo de la ruta ni coste de infraestructura.
- La API heredada compartida y los proveedores externos permanecen fuera de este alcance.

## Verificación

Las pruebas focalizadas están añadidas y publicadas. No se ejecutó pytest ni se confirmó una ejecución de GitHub Actions desde esta sesión; su resultado sigue **pendiente de ejecución**. Las pruebas asíncronas usan `asyncio.run` para no añadir una dependencia de `pytest-asyncio`. Tampoco se ejecutaron migraciones, llamadas reales a Ollama, cambios en VPS, Docker o despliegues.

## Siguiente paso

1. Confirmar que CI ejecuta las pruebas actualizadas y corregir incompatibilidades.
2. Añadir una prueba de aislamiento ante fallo de logging/telemetría.
3. Verificar en un entorno de prueba la configuración INFO, retención y acceso a los eventos.
4. Después, diseñar persistencia PostgreSQL de telemetría en modo append-only, con retención y control de acceso, antes de introducir reservas/cuotas activas.
