# Especificación del orquestador durable de facturación

Estado: diseño técnico; NO implementado ni conectado a HTTP.
No habilita cobros ni cambia el comportamiento del endpoint actual.

## Hallazgo confirmado en main

`api/billing_execution.py` actualmente reserva créditos, ejecuta `inference_call()`, calcula créditos desde contadores de Ollama y llama a `settle_reservation()`. No llama a `claim_execution()`, no cifra/persiste el resultado y no guarda una prueba durable de los contadores antes de liquidar.

`api/billing_execution_store.py` permite marcar una ejecución como `completed` al persistir ciphertext, pero la tabla 010 no conserva los contadores de uso ni los créditos medidos. Por ello no basta con insertar `persist_encrypted_result()` antes de `settle_reservation()`: tras un crash entre ambas operaciones no habría una fuente durable para reconstruir la liquidación exacta.

## Invariantes obligatorios

1. Autenticar sesión, validar CSRF y autorizar la pertenencia/rol del proyecto antes de consultar una clave idempotente.
2. Una clave se vincula a usuario, proyecto y fingerprint canónico del request efectivo, incluidos mensajes de sistema/RAG y parámetros de generación.
3. Una clave repetida con fingerprint distinto devuelve conflicto; nunca ejecuta el modelo.
4. Una reserva y su derecho de ejecución se crean/reclaman sin permitir dos ganadores concurrentes.
5. Solo el ganador puede llamar a Ollama. Los estados `started`, `unknown` y `review` nunca permiten una segunda inferencia automática.
6. El proveedor de claves debe estar disponible y entregar clave AES-256 válida antes de permitir una ejecución facturable.
7. La respuesta y los metadatos mínimos de medición se serializan en un formato versionado y se cifran juntos. No se persiste prompt ni respuesta en claro.
8. Antes de marcar la ejecución recuperable se guardan, en una única transacción, ciphertext, nonce, key ID, hash, versión del formato, prompt_eval_count, eval_count, créditos medidos y la identidad de la política de medición.
9. La liquidación es idempotente y solo acepta el importe medido durable de la ejecución completada. No acepta importes aportados por el cliente.
10. El endpoint devuelve respuesta solo después de verificar la integridad, descifrar con AAD de usuario/reserva/ejecución y confirmar el estado de liquidación.
11. Si el proveedor responde pero cifrado/persistencia falla, se conserva la reserva como incierta y se bloquea toda reejecución automática. No se liquida por estimación.
12. Si la liquidación tiene resultado ambiguo, se consulta y reconcilia la reserva/ledger; nunca se vuelve a inferir.

## Máquina de estados propuesta

- Reserva: `held -> settled`, o `held -> unknown/review` en incertidumbre.
- Ejecución: `started -> completed` solo con resultado y metadatos cifrados persistidos; `started -> unknown` ante timeout, cancelación o incertidumbre.
- `completed` con reserva `held` significa que hay resultado durable pendiente de liquidación; el worker de recuperación debe descifrar/verificar metadatos y repetir únicamente la operación idempotente de liquidación, nunca Ollama.
- `unknown` requiere reconciliación con evidencia externa/operativa; no se puede convertir automáticamente en una nueva ejecución.

## Cambios de esquema requeridos antes del orquestador

La migración siguiente (número a determinar tras revisar el estado real de migraciones) debe ampliar el registro de ejecución con campos versionados para:
- versión del envelope cifrado;
- metadatos de uso cifrados o incluidos dentro del mismo envelope;
- créditos medidos y policy version protegidos contra modificación;
- estado/fecha de liquidación y referencia de ledger, o una tabla de eventos append-only que permita reconstruirla.

La elección entre guardar créditos medidos en claro bajo constraints y cifrarlos dentro del envelope debe resolverse con threat model y política de auditoría. Si se guardan en claro, deben tratarse como datos financieros sensibles, ser inmutables tras completar y tener auditoría.

## Pruebas obligatorias

- Concurrencia PostgreSQL: N peticiones con misma clave/fingerprint producen una reserva, una ejecución y una llamada al proveedor.
- Misma clave con fingerprint diferente: conflicto antes de invocar proveedor.
- Cada transición con inyección de fallo antes/después de commit.
- Crash tras respuesta del proveedor, antes de cifrar: unknown, sin liquidación y sin reejecución.
- Crash tras persistir envelope y antes de liquidar: recuperación liquida con los metadatos persistidos, sin Ollama.
- Crash durante liquidación: reintento idempotente de liquidación, sin Ollama.
- Cifrado/KMS indisponible: fail closed antes de ejecutar o conservar estado incierto sin cobro.
- Ciphertext alterado, nonce/key ID inválidos o AAD de otro usuario/reserva/ejecución: no devolver respuesta ni liquidar.
- Usuario/proyecto no autorizado: no revelar si existe una clave ni un resultado.
- Pruebas de migraciones PostgreSQL desde una base vacía y desde la versión anterior.

## Criterio de aceptación

No conectar esta lógica al endpoint `POST /workspace/chat/completions`, no habilitar `billing_enabled` y no activar cobros hasta que la máquina de estados, la migración, KMS real, pruebas de concurrencia/fallos y revisión de seguridad estén completas. El endpoint actual permanece en shadow usage y no debe presentarse como facturación activa.
