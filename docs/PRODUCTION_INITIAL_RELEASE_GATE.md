# AXYRON ATOMIC — Puerta de salida a producción inicial

> **Estado actual verificado — 2026-11-08 (auditoría integral V1.0, rama `agent/opencode-vps`).**
> Las secciones siguientes son un registro histórico y se conservan sin reescritura. Estado real comprobado ese día:
> - `main = fa0a536`; CI del SHA exacto en verde (run `42526343714`, los seis jobs, incluido `qdrant-e2e`). Delta `ad68953 → fa0a536`: la regresión unitaria de rollback de `replace_source` (`1867a11`) y documentos; `a298344 → fa0a536`: solo documentos.
> - Producción sirve el código de `main = a298344` (desplegado con backup previo, rollback etiquetado y verificación real en `/health` 6/6 y readiness `ready`). `d33ca42` (aislamiento de la BD de pruebas frente a `.env`) es un cambio de pruebas/infra de suite, no de producto, y corresponde al propietario desplegarlo si corresponde.
> - `AUTH_ENABLED=true` en producción (readiness `ready`; 401 sin sesión, 422 con payload inválido; sin cuentas ni correos reales de prueba todavía).
> - Migraciones PostgreSQL `022` y `023` aplicadas en producción el 2026-11-08 con rehearsal previo en contenedor desechable; segunda ejecución del migrador: ninguna migración pendiente. Verificadas de nuevo en instancia desechable de esta auditoría (001→023 desde cero, re-ejecución idempotente, matriz PostgreSQL **77 passed**).
> - `QVAPAY_ENABLED=false` (confirmado por presencia de flag `false`); `BILLING_ENFORCEMENT_ENABLED` no habilitado (sombra/`shadow`, confirmado en readiness); `SANDBOX_DOCKER_ENABLED` ausente → por defecto `false` y fail-closed.
> - Rollback de aplicación ensayado en vivo (ida y vuelta, salud 6/6 y readiness `ready`); rollback completo de DB no ensayado (no fue necesario).
> - Cobros, checkout, ledger en cobro real y sandbox **siguen desactivados**. `REL-01` bloqueada; la V1.0 no se declara liberada.
> - Persistente como histórico: cualquier afirmación de este documento sobre «autenticación desactivada» corresponde al momento de su redacción y no al estado actual.

**Estado histórico del documento:** plan de cierre obligatorio; no certifica que el producto esté listo ni habilita despliegues o cobros.
**Objetivo:** entregar una primera versión privada y comercialmente operable, con ATOMIC CODE como único modelo facturable inicial. Vídeo, visión, imágenes, organizaciones y proveedores adicionales quedan fuera de este lanzamiento.

## 1. Definición de producción inicial

La primera producción debe permitir que un usuario se registre, verifique su correo, inicie sesión, cree proyectos aislados, use AXYRON STUDIO, converse con el modelo realmente verificado, consulte plan/consumo/saldo/historial y compre por QvaPay con acreditación servidor-a-servidor idempotente.

El primer lanzamiento será limitado: un modelo, usuarios individuales y catálogo publicado de forma explícita. No se anunciarán capacidades que no estén operativas.

## 2. Bloqueadores verificados en el repositorio

- `AUTH_ENABLED` permanece desactivado por defecto. El repositorio ya incluye registro pendiente, verificación de correo, reenvío, recuperación de contraseña, revocación de sesiones, rate limiting persistente, OAuth Google/GitHub y MFA integrado en contraseña/OAuth. La implementación está cubierta por CI; la entrega SMTP, OAuth real, proxy/cookies y aceptación siguen pendientes de staging.
- No habilitar autenticación pública hasta validar en staging los flujos completos, configuración runtime de MFA/SMTP/OAuth, seguridad del proxy, revisión independiente y pruebas de abuso.
- La medición de Ollama conserva Shadow Mode por defecto. Se conectó `workspace_routes.py` al orquestador durable cuando `BILLING_ENFORCEMENT_ENABLED=true`: calcula una reserva superior sobre prompt final + RAG + salida, exige `Idempotency-Key`, reserva PostgreSQL antes de inferir, reclama una ejecución única, exige contadores reales de Ollama, cifra el resultado con AES-256-GCM y liquida el ledger solo después de persistir ciphertext. Las repeticiones recuperan resultados completados sin repetir inferencia; los estados inciertos no se reejecutan. La clave de resultados usa variables separadas de MFA (`AXYRON_BILLING_RESULT_*`). La ruta sigue desactivada por defecto: para activarla faltan custodiar/injectar esa clave en runtime, provisionar cuotas o lotes reales y verificar pruebas E2E con PostgreSQL + Ollama en staging. Sin saldo, la ruta devuelve 402; sin medición verificable, no entrega respuesta facturada. Esto no integra QvaPay ni habilita checkout.
- Existe una base PostgreSQL aditiva para cuotas, reservas, asignaciones y ledger (migraciones 007/008/009/010), además de un servicio transaccional inicial de reserva/liquidación y conciliación auditada de reservas `unknown`/`review` cuando se confirma que no hubo ejecución. La auditoría es append-only e idempotente; la función requiere que una capa superior valide al administrador y la evidencia. El CI de la migración 009 y sus pruebas Python/PostgreSQL terminó correctamente (run 247). Se añadió un registro de ejecución único por reserva y almacenamiento de resultado exclusivamente cifrado (migración 010); la capa de almacenamiento permite reclamar una ejecución una sola vez y recuperar ciphertext completado con verificación SHA-256. Se añadió `api/billing_result_crypto.py` con AES-256-GCM, nonce aleatorio de 96 bits y AAD ligado a user_id/reservation_id/execution_id; el proveedor de claves es una interfaz inyectable y los tests cubren integridad, contexto, clave incorrecta y rotación por key_id. Esto NO proporciona por sí solo un KMS: aún falta conectar un gestor externo de secretos/claves, configurar custodia/rotación operativa y enlazar el cifrado/descifrado al orquestador de ejecución y a rutas HTTP. La orquestación durable `api/billing_execution_durable.py` SÍ está conectada a `POST /workspace/chat/completions` cuando `BILLING_ENFORCEMENT_ENABLED=true`: exige `Idempotency-Key`, verifica el manifiesto del runtime antes de RAG/inferencia, calcula la reserva conservadora, reserva créditos en PostgreSQL, reclama una ejecución única, llama a Ollama una sola vez, valida modelo/contadores reales, cifra y persiste el resultado antes de liquidar. Una repetición compatible recupera el resultado cifrado sin repetir inferencia; una clave reutilizada con otro payload devuelve conflicto y los estados inciertos requieren conciliación. El modo predeterminado continúa siendo shadow/free, sin cobros. Hay pruebas unitarias del flujo y pruebas PostgreSQL de persistencia/recuperación; el CI #42435202109 aprobó las cinco tareas (814 pruebas Python aprobadas, 9 omitidas; migraciones/transacciones PostgreSQL, Qdrant Cloud, build/smoke de imágenes y E2E de Studio). Esto no equivale todavía a un E2E en staging con el Ollama exacto de producción, ni sustituye KMS administrado, rotación de claves y prueba de restauración. La ruta heredada `/v1/chat/completions` queda bloqueada cuando se activa el ledger para impedir que una clave compartida evite la facturación individual. También se reforzó la idempotencia de reservas para vincular clave a payload, cantidad, proyecto, request_id y versión de política; las pruebas de integración cubren reutilización incompatible. Siguen pendientes pruebas adicionales de expiración, recuperación tras caída y conciliación de uso confirmado. La tabla de telemetría sigue siendo observacional y no debe usarse directamente como fuente de cobro.
- La API heredada /v1 usa una clave compartida y no representa identidad individual; queda fuera de facturación.
- QvaPay está APPROVED comercialmente según el propietario, pero faltan órdenes, firma, consulta de transacción, webhook e idempotencia.
- Precios, límites y tarifas de referencia no son tarifas activas ni costes reales medidos.
- La salud exige PostgreSQL, Ollama y Qdrant; hay que validar dependencias y configuración real antes de desplegar.
- La identidad del modelo en runtime debe verificarse contra el artefacto servido. No declarar ATOMIC CODE 1.1 si el motor ejecuta otra versión.
- La discrepancia de contrato del modelo quedó corregida en el repositorio: el cliente solo puede solicitar el ID público `atomic-code`; el runtime continúa seleccionando el alias configurado en servidor y la ruta de workspace rechaza la respuesta si `requested_model` o `returned_model` no coinciden con `settings.chat_model`. CI #252 aprobó esquema, catálogo y pruebas de identidad; CI #253 está en curso para la validación de rechazo en runtime. Esto todavía no conecta el cobro.

## 3. Entregables obligatorios antes de cobrar

### A. Identidad, sesiones y protección
- [x] Código de verificación de correo con token de un solo uso, hash, caducidad y consumo atómico; falta probar entrega SMTP real.
- [x] Recuperación de contraseña, revocación de sesiones y notificación; falta aceptación end-to-end en staging.
- [x] Rate limiting persistente para registro, login, recuperación y callbacks OAuth; confirmar IP efectiva detrás del proxy en staging.
- [x] Sesiones, CSRF, cookie de sesión HttpOnly/Secure configurable y expiración; el login por contraseña ahora establece explícitamente HttpOnly y tiene prueba de regresión. Falta validar infraestructura HTTPS real.
- [x] Rol administrativo global separado de roles de proyecto y MFA integrado en login/OAuth; faltan configuración runtime, rotación MFA en staging y revisión de operaciones sensibles.
- [x] Pruebas automatizadas de aislamiento, cuentas suspendidas/no verificadas y rutas MFA; falta aceptación funcional y revisión independiente.

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
- AXYRON STUDIO móvil/escritorio: registro/login, proyectos, chat, historial, perfil, plan, consumo, saldo, compras y soporte.
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


### Preflight unificado fail-closed

Se añadió `api/billing_preflight.py` para agrupar el cálculo de presupuesto y la huella SHA-256 de la solicitud. Recibe explícitamente los mensajes finales completos (incluidos system/historial/RAG), modelo público/runtime, parámetros de generación y ventana de contexto. Rechaza la preparación facturable salvo que `tokenizer_verified is True`; también rechaza runtime/modelo público no autorizado. Es una función pura. El endpoint de chat ya usa preflight y orquestación durable cuando la facturación está activada, pero la verificación real del tokenizer/Modelfile/template sigue pendiente; la puerta permanece desactivada.


### Identidad estable para reintentos HTTP

Se añadió `api/billing_request_identity.py`. Genera un UUID determinista por combinación usuario + `Idempotency-Key`, valida longitud (1–200) y caracteres imprimibles ASCII, y evita que un reintento HTTP cree un `request_id` diferente. El endpoint ya exige la cabecera, valida sesión/CSRF/rol de proyecto antes de invocarla y pasa la misma clave al servicio transaccional. La ruta legada `/v1` sigue fuera de la facturación multiusuario.


### Corrección de cookie de sesión — 7 de noviembre de 2026

La ruta de login por contraseña establecía la cookie de sesión sin `HttpOnly`. Se corrigió a `httponly=True` y se añadió una prueba que verifica el atributo en la respuesta. La cookie CSRF sigue siendo legible por el navegador para adjuntar el encabezado `X-CSRF-Token`; no contiene el token de sesión. GitHub Actions `42399587370` aprobó las pruebas Python, Playwright, build de imagen en CI, migraciones PostgreSQL e integración Qdrant Cloud. Esto no reemplaza la validación de staging ni autoriza activar `AUTH_ENABLED`.


### Readiness de modelos configurados

La ruta `/health` comprueba ahora que el endpoint de etiquetas de Ollama incluya el modelo de chat y el modelo de embeddings configurados, además de verificar que el servicio responda. Si falta cualquiera de los dos modelos, readiness devuelve HTTP 503; `/health/live` conserva su función de liveness. Las pruebas de disponibilidad y modelo ausente pasaron en GitHub Actions `42400165930`.

> **Estado actual verificado — 2026-11-08 (activación V1.0 autorizada, rama `agent/opencode-vps`).**
> - Producción sirve el código de la rama con: `QVAPAY_ENABLED=true` (checkout operativo), `BILLING_ENFORCEMENT_ENABLED=true` (modo `ledger`, attestation y result key configuradas), `SANDBOX_DOCKER_ENABLED=true` (daemon dedicado userns-remapped con TLS, imagen por digest, aislamiento verificado), `AUTH_ENABLED=true`.
> - `/health` 6/6; readiness **ready**; `/auth/me` 401 sin sesión; landing/Studio públicos sirviendo el árbol auditado (assets == repo).
> - Registro verificado EN VIVO por el propietario (cuenta real `gemeni0305@gmail.com`, verificación de correo entregada, 50 créditos FREE acreditados atómicamente: lote `promotion` 50/50 y ledger `grant` +50).
> - **Falta para la condición de salida:** publicación de términos/privacidad/reembolsos, primer pago real E2E de QvaPay, MFA E2E de cuenta real y aceptación formal del propietario. `REL-01` bloqueada; la V1.0 no se declara liberada.
> - Intervención operativa autorizada documentada: IP secundaria 172.16.0.1 (br-54dec66c6382) por desaparición de docker0; regla UFW #14 para el daemon sandbox. Rollback de imágenes `rollback-v1.0-20261108` / `rollback-pre-pages`.

> **Estado actual verificado — 2026-11-09 (Studio independiente + SSO, rama `hardening/studio-independent-app`).**
> - AXYRON Studio ahora es una aplicación independiente con rutas reales (`/dashboard`, `/projects`, …), documento propio y estilos propios; la web principal conserva landing + SSO (`/sso-start`).
> - SSO landing ↔ Studio por código de un solo uso implementado y probado en PostgreSQL efímero (7/7 en ese estado); se añadieron 2 casos nuevos (state no ASCII y cuenta suspendida) pendientes de CI. `STUDIO_ORIGIN` requerido en `.env` para habilitarlo (sin él, 503 fail-closed).
> - Migración `024_sso_codes.sql` añadida; verificada desde cero en instancia desechable.
> - CI del Studio standalone en verde (`studio-browser-e2e`, 6/6) tras ampliar el job.
> - Despliegue del Studio (DNS `studio.axyronatomic.com`, TLS, vhost `deploy/studio.conf`, `STUDIO_ORIGIN` en `.env`, `python -m api.migrate`) corresponde al propietario.
> - **REL-01 sigue bloqueada**: legal sin publicar, primer pago real E2E, MFA E2E y aceptación formal pendientes.

> **Endurecimiento de Studio/SSO — 2026-11-09 (misma rama, sin desplegar).**
> - SSO: código en fragmento (`#code=…`), URL limpiada antes del intercambio, `state` hasheado en UTF-8 (401 en vez de 500) y `Cache-Control: no-store` en `authorize`.
> - Studio: chat con historial completo e idempotencia por payload; agente con detalle/aprobaciones/`resume`/`cancel`/`reconcile`; modelos con verificación en vivo; dashboard muestra readiness degradado; logout documentado como host-only (sin logout global).
> - Evidencia local: `pytest -q` → 1070 passed, 25 skipped; E2E Playwright de Studio aprobado; `check_frontend_js.py` aprobado. **No hay CI verde declarada para este estado**: falta ejecutar CI sobre el SHA final.
> - Siguen bloqueados: despliegue DNS/TLS de `studio.axyronatomic.com`, `STUDIO_ORIGIN` en `.env`, migración real, E2E con dependencias reales, primer pago QvaPay, MFA E2E, legal y aceptación del propietario. Confirmar el dominio canónico antes de publicar.
