# AXION ATOMIC — Implementación inicial de medición en shadow mode

**Estado:** persistencia best-effort de Shadow Mode implementada en `main`; CI debe confirmar la migración y los tests.  
**Alcance:** preservar la respuesta pública del chat y observar los metadatos que Ollama devuelve. No es facturación ni contabilidad.

## Cambios

- `api/ollama.py` incorpora el resultado inmutable `InferenceResult` y `parse_chat_response()`.
- `chat_with_usage()` conserva texto, modelo solicitado/devuelto, estado `done`, contadores de prompt/output y duraciones en nanosegundos.
- Los contadores ausentes o inválidos quedan como `None`; nunca se convierten silenciosamente en cero. Los booleanos, negativos, strings y floats no se aceptan como contadores.
- La función pública previa `chat()` continúa devolviendo únicamente texto para no romper consumidores existentes.
- `/workspace/chat/completions` genera un `request_id` UUID por inferencia y lo usa tanto para el evento JSON como para persistencia en PostgreSQL.
- `migrations/006_inference_usage_events.sql` añade una tabla con clave primaria `request_id`, referencias a usuario/proyecto, contadores y duraciones nullable, origen de medición y timestamp. Incluye índices por usuario, proyecto y modelo.
- `api/usage_events.py` persiste los metadatos en una transacción breve; no guarda prompts, respuestas ni secretos. La restricción primaria evita duplicar el mismo `request_id`.
- La escritura es best-effort: si PostgreSQL falla, la respuesta de inferencia sigue siendo exitosa. No existe aún outbox/reintento durable y puede perderse la observación.
- La respuesta pública mantiene la estructura previa y no expone los metadatos nuevos.
- La ruta heredada `/v1` no se incorpora a medición individual.
- `tests/test_ollama_usage.py` cubre parsing completo, contadores ausentes/inválidos, contenido inválido, modelos solicitado/devuelto, petición HTTP no streaming, propagación de timeout y compatibilidad del wrapper `chat()`.
- `tests/test_workspace_role_matrix_http.py` se actualizó para simular el contrato `InferenceResult`, comprobar la respuesta del endpoint, validar el UUID y la identidad/proyecto del evento, verificar que el evento no contiene el texto del usuario y que un logger defectuoso no interrumpe la respuesta.
- `tests/test_model_identity.py` y `tests/test_workspace_authorization_boundaries.py` actualizan sus mocks al adaptador `chat_with_usage()`.

## Límites deliberados

- Shadow Mode ya crea registros de observación persistentes en PostgreSQL; no crea saldos, créditos, reservas, cuotas ni costes.
- No bloquea peticiones ni cambia precios o límites.
- La clave `request_id` evita duplicar una observación, pero no existe idempotencia económica ni conciliación porque todavía no existe ledger.
- La emisión usa el logger `axion.usage.shadow`; el entorno de ejecución debe configurar nivel INFO y retención/acceso adecuados para que los eventos se conserven. Los logs no deben tratarse como libro contable.
- Los contadores solo reflejan lo que devuelve Ollama. Si faltan, el evento marca `usage_source=unavailable`.
- No se mide aún latencia de extremo a extremo de la ruta ni coste de infraestructura.
- La API heredada compartida y los proveedores externos permanecen fuera de este alcance.

## Verificación

Se añadieron pruebas de mapeo de persistencia y de esquema PostgreSQL. La ejecución de GitHub Actions para los últimos commits debe verificarse antes de declarar esta revisión cerrada. Las pruebas asíncronas usan `asyncio.run` para no añadir una dependencia de `pytest-asyncio`. Tampoco se ejecutaron migraciones, llamadas reales a Ollama, cambios en VPS, Docker o despliegues.

## Siguiente paso

1. Confirmar que CI ejecuta las pruebas actualizadas y corregir incompatibilidades.
2. Añadir outbox/reintentos durables si se requiere garantía de entrega.
3. Configurar permisos de solo INSERT/SELECT para el rol de aplicación y validar retención/acceso.
4. Implementar consultas de consumo protegidas por identidad; mantener billing desactivado.
