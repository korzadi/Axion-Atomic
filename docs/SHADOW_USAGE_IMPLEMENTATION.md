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
- `tests/test_ollama_usage.py` añade pruebas de parsing completo, contadores ausentes, valores inválidos, contenido inválido y diferencia entre modelo solicitado/devuelto.

## Límites deliberados

- Shadow mode no crea registros persistentes en PostgreSQL, saldos, créditos, reservas, cuotas ni costes.
- No bloquea peticiones ni cambia precios o límites.
- No hay idempotencia económica ni conciliación porque todavía no existe ledger.
- La emisión usa el logger `axion.usage.shadow`; el entorno de ejecución debe configurar nivel INFO y retención/acceso adecuados para que los eventos se conserven. Los logs no deben tratarse como libro contable.
- Los contadores solo reflejan lo que devuelve Ollama. Si faltan, el evento marca `usage_source=unavailable`.
- No se mide aún latencia de extremo a extremo de la ruta ni coste de infraestructura.
- La API heredada compartida y los proveedores externos permanecen fuera de este alcance.

## Verificación

No se ejecutó pytest ni CI desde esta sesión. Los tests están añadidos, pero su resultado es **pendiente de ejecución**. Tampoco se ejecutaron migraciones, llamadas reales a Ollama, cambios en VPS, Docker o despliegues.

## Siguiente paso

1. Ejecutar suite focalizada y suite completa en CI.
2. Corregir cualquier incompatibilidad sin alterar contratos existentes.
3. Verificar en un entorno de prueba que el logger emite eventos y que no incluye prompts/respuestas.
4. Después, diseñar persistencia PostgreSQL de telemetría en modo append-only, con retención y control de acceso, antes de introducir reservas/cuotas activas.
