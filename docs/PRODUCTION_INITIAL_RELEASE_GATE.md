# AXION ATOMIC — Puerta de salida a producción inicial

**Estado:** plan de cierre obligatorio; no certifica que el producto esté listo ni habilita despliegues o cobros.
**Objetivo:** entregar una primera versión privada y comercialmente operable, con ATOMIC CODE como único modelo facturable inicial. Vídeo, visión, imágenes, organizaciones y proveedores adicionales quedan fuera de este lanzamiento.

## 1. Definición de producción inicial

La primera producción debe permitir que un usuario se registre, verifique su correo, inicie sesión, cree proyectos aislados, use AXION STUDIO, converse con el modelo realmente verificado, consulte plan/consumo/saldo/historial y compre por QvaPay con acreditación servidor-a-servidor idempotente.

El primer lanzamiento será limitado: un modelo, usuarios individuales y catálogo publicado de forma explícita. No se anunciarán capacidades que no estén operativas.

## 2. Bloqueadores verificados en el repositorio

- auth_enabled está desactivado por defecto. El registro crea usuarios pending_verification, pero no se encontró un flujo completo de verificación de correo.
- No habilitar autenticación pública hasta añadir verificación, recuperación de contraseña, rate limiting y pruebas de abuso.
- La medición de Ollama está en Shadow Mode: emite logs, no persiste uso durable ni cobra créditos. Existe un helper puro de cálculo de tarifa que exige contadores finales confiables y coincidencia entre modelo solicitado/devuelto; todavía no reserva saldo ni está conectado a inferencia.
- Existe una base PostgreSQL aditiva para cuotas, reservas, asignaciones y ledger (migraciones 007/008/009/010), además de un servicio transaccional inicial de reserva/liquidación y conciliación auditada de reservas `unknown`/`review` cuando se confirma que no hubo ejecución. La auditoría es append-only e idempotente; la función requiere que una capa superior valide al administrador y la evidencia. El CI de la migración 009 y sus pruebas Python/PostgreSQL terminó correctamente (run 247). Se añadió un registro de ejecución único por reserva y almacenamiento de resultado exclusivamente cifrado (migración 010); la capa de almacenamiento permite reclamar una ejecución una sola vez y recuperar ciphertext completado con verificación SHA-256. Se añadió `api/billing_result_crypto.py` con AES-256-GCM, nonce aleatorio de 96 bits y AAD ligado a user_id/reservation_id/execution_id; el proveedor de claves es una interfaz inyectable y los tests cubren integridad, contexto, clave incorrecta y rotación por key_id. Esto NO proporciona por sí solo un KMS: aún falta conectar un gestor externo de secretos/claves, configurar custodia/rotación operativa y enlazar el cifrado/descifrado al orquestador de ejecución y a rutas HTTP. Se añadió `api/billing_execution_durable.py`: reserva, claim único, inferencia, persistencia de ciphertext antes de liquidar y recuperación de ejecuciones `completed` sin repetir inferencia; los estados `started`/`unknown`/`review` bloquean la reejecución. Tiene pruebas unitarias del orden persistir→liquidar y recuperación sin segunda llamada. Aún no está integrado en `workspace_routes.py` y requiere serializador estable más proveedor KMS real. Se añadió una prueba de integración PostgreSQL que simula caída de liquidación después de persistir ciphertext y verifica recuperación sin segunda inferencia; el workflow PostgreSQL ahora ejecuta explícitamente las pruebas del store y de recuperación durable. También se reforzó la idempotencia de reservas para vincular clave a payload, cantidad, proyecto, request_id y versión de política; las pruebas de integración cubren reutilización incompatible. Siguen pendientes pruebas adicionales de expiración, recuperación tras caída y conciliación de uso confirmado. La tabla de telemetría sigue siendo observacional y no debe usarse directamente como fuente de cobro.
- La API heredada /v1 usa una clave compartida y no representa identidad individual; queda fuera de facturación.
- QvaPay está APPROVED comercialmente según el propietario, pero faltan órdenes, firma, consulta de transacción, webhook e idempotencia.
- Precios, límites y tarifas de referencia no son tarifas activas ni costes reales medidos.
- La salud exige PostgreSQL, Ollama y Qdrant; hay que validar dependencias y configuración real antes de desplegar.
- La identidad del modelo en runtime debe verificarse contra el artefacto servido. No declarar ATOMIC CODE 1.1 si el motor ejecuta otra versión.
- La discrepancia de contrato del modelo quedó corregida en el repositorio: el cliente solo puede solicitar el ID público `atomic-code`; el runtime continúa seleccionando el alias configurado en servidor y la ruta de workspace rechaza la respuesta si `requested_model` o `returned_model` no coinciden con `settings.chat_model`. CI #252 aprobó esquema, catálogo y pruebas de identidad; CI #253 está en curso para la validación de rechazo en runtime. Esto todavía no conecta el cobro.

## 3. Entregables obligatorios antes de cobrar

### A. Identidad, sesiones y protección
- Verificación de correo con token aleatorio de un solo uso, hash almacenado, caducidad y consumo atómico.
- Recuperación de contraseña, invalidación de sesiones y notificación de cambio.
- Rate limiting persistente/distribuido para registro, login, recuperación y endpoints costosos.
- Controles de sesión, CSRF, cookies seguras y expiración.
- Rol administrativo global separado de roles de proyecto; MFA/2FA para operaciones económicas críticas.
- Pruebas de aislamiento entre usuarios/proyectos y de cuentas suspendidas/no verificadas.

### B. Inferencia y límites
- Persistir cada petición y medición en PostgreSQL con UUID, usuario, proyecto, modelo, política y estado.
- Contadores reales de Ollama; valores ausentes permanecen NULL y nunca se cobran como cero ni como estimación silenciosa.
- Idempotencia por petición y hash de payload.
- Reservas atómicas ANTES de inferir, cuotas diarias/mensuales, límites de salida, concurrencia y RPM. La reserva previa debe tener un límite superior defendible para el prompt completo (system, historial y RAG) y la salida; no usar contadores posteriores como si fueran una reserva previa ni permitir deuda/ saldo negativo.
- Conciliación idempotente de éxito, fallo, parcial y estado desconocido.
- Ledger append-only de créditos, asientos compensatorios y reconstrucción/verificación de saldos.
- Pruebas de concurrencia, doble solicitud, timeout, caída del proceso y recuperación.

### C. Catálogo y cobros
- Publicar versiones explícitas de planes, paquetes, precios, límites y ponderadores; los valores del roadmap no se activan automáticamente.
- Medir costes reales de VPS, almacenamiento y modelo; separar costes verificados de estimaciones.
- Órdenes internas persistidas antes de crear facturas.
- QvaPay: HMAC sobre bytes originales, timestamp, consulta backend, comparación de UUID/importe/moneda/estado, protección replay e idempotencia.
- Acreditar solo tras confirmación del servidor y dentro de una transacción atómica.
- Sandbox oficial probado, incluidos webhooks duplicados/manipulados/atrasados y conciliación.
- Reembolsos/reversiones mediante movimientos compensatorios.
- No vender créditos con expiración de 12 meses hasta revisar términos, reembolsos y obligaciones aplicables.

### D. Experiencia y operación
- AXION STUDIO móvil/escritorio: registro/login, proyectos, chat, historial, perfil, plan, consumo, saldo, compras y soporte.
- Panel administrativo mínimo: usuarios, suspensión, catálogo, tarifas, pagos, conciliación, ajustes justificados, auditoría y métricas.
- Estado de servicio, readiness checks, logs sin prompts/secretos, métricas, alertas y trazabilidad por request ID.
- Privacidad, términos, uso aceptable, reembolsos, caducidad, soporte y contacto publicados antes de aceptar pagos.
- Procedimiento de incidencias, respuesta a abuso, backups y prueba de restauración.

### E. Infraestructura y lanzamiento
- Inventario actualizado de solo lectura del VPS, servicios, puertos, recursos, almacenamiento, proxy, DNS, TLS, volúmenes y backups.
- Validar capacidad de API, PostgreSQL, Qdrant y Ollama sin degradar servicios preexistentes.
- Secretos fuera del repositorio y de logs.
- Revisar Compose, healthchecks, persistencia, permisos, límites y política de reinicio.
- Despliegue reproducible, migraciones revisadas, backup probado, smoke tests, rollback seguro y monitorización.
- Pruebas de carga con concurrencia realista y límites conservadores.

## 4. Orden de ejecución

1. Cerrar y verificar CI de las migraciones 007/008 y el servicio transaccional de reservas.
2. Ampliar pruebas de ledger, FEFO, expiración, fallos, estados desconocidos y recuperación.
3. Completar identidad segura: verificación, recuperación, rate limits y RBAC global.
4. Diseñar y probar un límite superior conservador de tokens antes de integrar medición Shadow Usage con reservas y conciliación; mantener Shadow Mode hasta demostrar que nunca se inicia inferencia sin reserva suficiente.
5. Implementar órdenes y QvaPay en sandbox.
6. Completar vistas de usuario y administración sobre APIs probadas.
7. Ejecutar auditoría de seguridad, privacidad, aislamiento, concurrencia, carga y recuperación.
8. Preparar despliegue con inventario VPS de solo lectura y plan de cambios.
9. Solicitar autorización específica para migraciones y despliegue en VPS.
10. Habilitar cobros solo tras pruebas end-to-end y aprobación explícita del catálogo comercial final.

## 5. Exclusiones

- ATOMIC VIDEO, imágenes y visión multimodal.
- Entrenamiento en VPS o GPU de pago.
- Organizaciones, saldos compartidos y marketplace de agentes.
- Proveedores externos no verificados.
- Streaming mientras no exista conciliación segura de tokens parciales.
- API heredada con clave global como vía de facturación individual.

## 6. Condición de salida

Solo etiquetar como **producción inicial lista para cobro** cuando A–E estén implementados, probados y documentados, con CI verde, restauración probada, QvaPay sandbox y revisión de seguridad. Un documento, una migración creada o un endpoint presente no equivalen a una capacidad lista.

**Regla operativa:** el trabajo de repositorio no despliega el VPS. No ejecutar builds, migraciones reales, reinicios, cambios de red/puertos/volúmenes ni pagos reales sin autorización específica.


### Serialización y huella canónica de solicitudes (implementación auxiliar)

Se añadieron `api/billing_result_codec.py` y `api/billing_request_fingerprint.py`. El codec serializa de forma determinista el resultado estructurado de Ollama, valida el esquema/contadores y limita el payload a 2 MiB antes del cifrado; no guarda plaintext en PostgreSQL. La huella SHA-256 enlaza identidad, proyecto, modelo público, mensajes finales, temperatura, máximo de salida y versión de política, evitando que una clave idempotente se reutilice para otro contenido o parámetros. Ambos módulos tienen pruebas unitarias. Aún deben conectarse al endpoint HTTP y al orquestador durable; la autenticación sigue deshabilitada y no se aceptan solicitudes facturables.
