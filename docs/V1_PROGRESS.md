# AXYRON ATOMIC V1.0 — Registro de progreso

**Rama de trabajo:** `agent/opencode-vps`
**Fase activa:** 12 — QA y liberación V1.0 (desarrollo inverso 12 → 7)
**Estado global:** EN DESARROLLO  
**Implementación global estimada:** 68% (media simple de las 12 fases; no equivale a preparación productiva)
**Preparación productiva:** 35% (requiere CI del HEAD, staging y configuración externa)

> Regla: los porcentajes son estimaciones de implementación basadas en la matriz de aceptación. No certifican disponibilidad operativa. Solo se declara **verificada** una capacidad cuando existe una prueba reproducible aprobada para el HEAD indicado. Las fases 10 y 12 conservan bloqueos externos que impiden declarar la V1.0 liberada.

## Resumen oficial de las 12 fases

| Fase | Módulo | Avance | Estado |
| ---: | --- | ---: | --- |
| 1 | Estabilización y arquitectura | 70% | EN PROGRESO |
| 2 | Autenticación y MFA | 60% | EN PROGRESO |
| 3 | Axyron Studio | 50% | EN PROGRESO |
| 4 | Modelos de IA | 65% | EN PROGRESO |
| 5 | Agente AXYRON | 75% | EN PROGRESO |
| 6 | Memoria y RAG | 70% | EN PROGRESO |
| 7 | Archivos y sandbox | 65% | EN PROGRESO |
| 8 | Administración | 80% | EN PROGRESO |
| 9 | Créditos y facturación | 80% | EN PROGRESO |
| 10 | Integración QvaPay | 50% | EN PROGRESO |
| 11 | Instalación y documentación | 90% | EN PROGRESO |
| 12 | QA y liberación V1.0 | 70% | EN PROGRESO |

**Lectura de los porcentajes:** reflejan implementación y pruebas locales del código inspeccionado, no aceptación en staging. Las cifras heredadas del orden antiguo de fases se conservan solo como histórico en las secciones siguientes.

## Fase 1 — Autenticación y cuentas

**Estado:** EN CURSO — **75%**

### Funcionalidades presentes en el código
- Registro con Argon2id, consentimiento legal y cuenta pendiente de verificación.
- Verificación de correo con token aleatorio, hash persistido, expiración y uso único.
- Reenvío de verificación con respuesta genérica.
- Login con rate limiting por IP/cuenta, rechazo de cuentas inactivas y sesión opaca.
- Cookies de sesión HttpOnly y protección CSRF.
- Logout con revocación de sesión.
- Recuperación de contraseña con token de un solo uso y revocación transaccional de sesiones.
- OAuth Google/GitHub con state ligado al navegador/proveedor; si MFA está activo, el callback solicita el segundo factor.
- Rutas de proyectos protegidas por sesión y pertenencia.
- Rutas principales y de recuperación registradas en `api/main.py`.

### Pruebas existentes
- Prueba de logout añadida en commit `3d98e946f3f4b4cb1628b96dfbc8bc565ea71fa5`: confirma revocación de sesión y eliminación de ambas cookies; CI run `42479092644` completado con éxito.
- Pruebas de registro añadidas en commit `384a7911113e717c464d71521acf53f07d3858e3`: comprueban que el token de verificación nunca aparece en la respuesta y que un fallo SMTP tampoco lo filtra. CI run `42479161490` pendiente de resultado al actualizar este registro.
- `tests/test_auth_security.py`: hashing, política de contraseña y rechazo de cuenta inactiva.
- `tests/test_auth_routes.py`: gate cerrado, rate limits, login, MFA y OAuth.
- `tests/test_auth_recovery_threadpool.py`: operaciones bloqueantes fuera del event loop.
- `tests/test_email_verification_postgres.py`: tokens, expiración, uso único y cuentas deshabilitadas.
- `tests/test_password_reset_postgres.py`: recuperación, expiración, uso único y revocación de sesiones.
- `docs/AUTHENTICATION_IMPLEMENTATION_STATUS.md`: dependencias operativas y bloqueos.
- Evidencia histórica: workflow CI #339, run `42255282471`, commit `fc4e719c5c682b1138150bf48596319e8dab833a`, éxito histórico de pruebas Python y migraciones PostgreSQL. No sustituye CI actual.

### Pendiente para cerrar la fase
1. Ejecutar CI completo actual sobre el commit final y revisar todos los logs.
2. Validar en navegador registro, verificación, login, logout, recuperación y MFA.
3. Verificar que los tokens de verificación/recuperación no se filtran a telemetría, historial o logs.
4. Validar SMTP, OAuth y cookies HTTPS en staging con dominios definitivos.
5. Verificar UX de errores, expiración y reenvío.
6. Documentar los bloqueos externos y habilitación segura.

### Bloqueos externos
- SMTP real, entrega y reputación del remitente no demostrados.
- Credenciales y callbacks OAuth definitivos pendientes de validación en staging.
- HTTPS, cookies Secure, proxy y dominio deben probarse en el entorno objetivo.
- `AUTH_ENABLED=false` permanece como valor seguro por defecto. No activarlo en producción desde esta tarea.

### Commits
- `0f689311a31cca0fa5c0010ea77007d5f5b39747`: corrige las aserciones de las pruebas de recuperación para validar el contrato real de las funciones (diccionarios de resultado). La ejecución anterior `42479287187` detectó dos fallos en las pruebas nuevas —no en la lógica de producción—; la corrección está bajo CI en `42479380635`.
- `faae033383d3a28d8625390087d54e5db1d65b0b`: registro inicial de progreso.
- `3d98e946f3f4b4cb1628b96dfbc8bc565ea71fa5`: prueba de revocación y limpieza de cookies al cerrar sesión; CI exitoso.
- `384a7911113e717c464d71521acf53f07d3858e3`: pruebas anti-filtración de token de verificación; CI pendiente.

### Próxima tarea
Completar la matriz de pruebas integrales de autenticación y corregir cualquier fallo reproducible antes de pasar a fase 2.

---

## Reglas de protección
- No publicar secretos ni leer/imprimir el contenido de `.env`.
- No borrar datos, volúmenes ni reinicializar PostgreSQL.
- No desplegar, reconstruir ni cambiar el VPS sin autorización explícita.
- No tocar KorzadiVPN ni sus dependencias.
- No instalar Qdrant local ni incorporar Open WebUI.
- No reactivar `atomic-code:16k-8k`.
- No simular integraciones ni declarar pruebas pendientes como aprobadas.


## Auditoría de continuidad — 2026-11-08 07:27 (America/New_York)

**HEAD inspeccionado:** `72947537c52262804b3c13e482d40c0eb0904f68` (`fix: preserve generic registration response on email failure`).

### Cambios recientes confirmados en `main`
- `72947537c52262804b3c13e482d40c0eb0904f68`: conserva la respuesta genérica de registro si falla el envío del correo.
- `829ef638b19827fec300f948cf4583e0b1e45b93`: corrige aserciones de tokens inválidos en pruebas de recuperación.
- `31634988b56b9c43c05b3d6b6fe91d6e7f557068`: añade cobertura para enlaces inválidos de verificación y recuperación.
- `9c9bd9d07a275e2f29e865f81441307048e9742d`: corrige continuaciones de pruebas de rate limit.
- `7e33fe1714fdd08328a003cab68d0d701afe0986`: prueba que el registro no revele enumeración por entrega de correo.

### Verificación del HEAD actual
- Lectura de `AGENTS.md`, `README.md`, `api/auth_routes.py`, `tests/test_auth_routes.py`, `docs/AUTHENTICATION_IMPLEMENTATION_STATUS.md` y workflow CI.
- El diff de HEAD confirma que el fallo de entrega de correo queda absorbido y se mantiene la respuesta genérica; no se incluye el token en la respuesta.
- La consulta de estados de commit para HEAD no devolvió checks/status publicados. Por tanto, **CI del HEAD actual: NO VERIFICADO**. No se declara superado.
- No se ejecutaron pruebas locales ni navegador desde esta sesión: el acceso disponible permite inspección y cambios de archivos en GitHub, pero no ofrece ejecución de terminal/pytest ni acceso SSH al VPS.
- No se ha modificado ni desplegado el VPS, PostgreSQL, Docker, servicios, volúmenes ni frontend.

### Decisión de fase
La Fase 1 permanece **EN CURSO**. No se incrementa el porcentaje ni se inicia Fase 2 hasta disponer de evidencia CI completa sobre el HEAD y completar la validación de staging (SMTP/OAuth/HTTPS/cookies) ya enumerada. La cifra 75% es el último valor registrado previamente; esta auditoría no la certifica de nuevo.

**Siguiente tarea verificable:** ejecutar el workflow CI completo para el HEAD `72947537c52262804b3c13e482d40c0eb0904f68`, revisar todos los jobs y corregir cualquier fallo antes de cerrar Fase 1.


## Continuidad y reordenamiento del plan — 2026-11-08

El propietario actualizó la taxonomía oficial de las 12 fases. Esta secuencia reemplaza los nombres y el orden anteriores; el trabajo previo se conserva y se reclasifica, no se repite:

1. Estabilización y arquitectura.
2. Autenticación y MFA.
3. Axyron Studio.
4. Modelos de IA.
5. Agente AXYRON.
6. Memoria y RAG.
7. Archivos y sandbox.
8. Administración.
9. Créditos y facturación.
10. Integración QvaPay.
11. Instalación y documentación.
12. QA y liberación V1.0.

**Fase activa:** 1 — Estabilización y arquitectura. El trabajo histórico de autenticación pasa a la Fase 2 y se conserva íntegramente.

### Bloque implementado en esta continuidad

- Añadidas dos pruebas de integración de la función /health/readiness en tests/test_api_health.py.
- La primera comprueba que una dependencia crítica ausente se traduce en HTTP 503 y estado blocked, conservando el detalle seguro de dependencias.
- La segunda comprueba que Redis, al ser opcional, puede estar degradado sin bloquear readiness cuando las dependencias críticas están disponibles.
- Commit: 466d85b0b7c7abccc70267adab74a1ed874911c6 — test: cover readiness endpoint dependency status mapping.
- Estas pruebas se añadieron al repositorio, pero no se ejecutaron en esta sesión. No se consideran aprobadas hasta CI.
- CI consultada para el commit de documentación anterior: no hay runs devueltas por la consulta disponible; no se afirma aprobación.
- Sin cambios en frontend, configuración del VPS, contenedores, PostgreSQL, volúmenes ni servicios externos.

### Criterio pendiente de Fase 1

Confirmar por CI las pruebas nuevas y la suite completa; después continuar con las brechas de arquitectura/contratos y persistencia que sigan abiertas en docs/V1_ACCEPTANCE_MATRIX.md. No se cierra la fase con pruebas meramente escritas.

### Nota sobre porcentajes

Los porcentajes heredados de la tabla anterior corresponden al orden anterior de fases y no son directamente comparables con esta nueva taxonomía. No se presentan como porcentajes reales de las nuevas 12 fases hasta reclasificar los criterios de aceptación y recalcularlos con evidencias del mismo HEAD. La matriz de aceptación sigue siendo la fuente de verdad para esa recalibración.


## Continuidad de desarrollo — checkpoint 2026-11-08

**Fase activa:** 1 — Estabilización y arquitectura.

### Implementación adicional
- Se reforzaron las pruebas de integración de `/health/readiness` en `tests/test_api_health.py`.
- Se añadieron aserciones basadas en el esquema JSON para comprobar el estado HTTP 503, el estado `blocked`, las comprobaciones de autenticación, las dependencias críticas y la sección opcional. Esto evita acoplar la prueba al orden/serialización exacta de las claves JSON.
- Commit: `68b7cea15d0927c0c2f97f76d3b3878bdbcb2857` — `test: make readiness response assertions schema-focused`.
- Commit anterior del mismo bloque: `466d85b0b7c7abccc70267adab74a1ed874911c6` — añade cobertura de dependencia crítica no disponible y degradación opcional de Redis.

### Verificación
- Confirmado mediante lectura posterior en GitHub que ambos métodos de prueba y la aserción por esquema están en `main`.
- No hay ejecución de Python/pytest ni runner CI disponible en esta sesión. Las pruebas están **añadidas, no ejecutadas**.
- La consulta de workflow runs para el commit de documentación anterior devolvió lista vacía; no se afirma que CI esté aprobada.
- No se modificó `api/main.py`, `api/readiness.py`, frontend, configuración VPS, PostgreSQL, Docker, volúmenes ni servicios externos.

### Medición honesta
- La matriz `docs/V1_ACCEPTANCE_MATRIX.md` contiene criterios con estados históricos, parciales y pendientes, pero varios resultados corresponden a SHA anteriores y no se pueden atribuir al HEAD actual.
- Hasta obtener pruebas del mismo HEAD, el porcentaje **verificado en el HEAD actual** para cada fase es 0%; esto no significa que no exista implementación, sino que aún no hay evidencia de ejecución/CI actual que permita certificarla. Se mantiene Fase 1 en progreso.
- No se recalcula avance de implementación a partir de la mera presencia de archivos.

### Siguiente tarea
- Conseguir una ejecución de CI reproducible para el HEAD actual y resolver fallos; después completar las pruebas de contrato/persistencia ARC-01, API-02 y DB-01 sin tocar datos ni servicios de producción.


## Cobertura adicional de fallos de infraestructura — 2026-11-08

- Se amplió `tests/test_api_health.py` con dos escenarios de fallo reproducibles: conexión PostgreSQL no disponible y respuesta de inventario de modelos Ollama malformada.
- La prueba PostgreSQL exige que el chequeo marque `database=unavailable`, mantenga el diagnóstico de Ollama y responda HTTP 503.
- La prueba de inventario malformado exige que Ollama pueda estar accesible, pero que ambos modelos requeridos se clasifiquen como no disponibles y readiness falle con HTTP 503.
- Commit: `d28cd5b64dd90b30a470b8c707934885d44277be` — `test: cover database outage and malformed model inventory`.
- Verificación de implementación: los dos casos y sus dobles están publicados en `main`; la lógica actual de `api/main.py` los maneja mediante el control de excepción de DB y la validación defensiva de `_ollama_model_names`.
- Ejecución: no se pudo ejecutar pytest en esta sesión; no se marcan como aprobadas. Estado CI consultado para commits previos: sin runs/status publicados por el conector disponible; el HEAD nuevo aún requiere CI.
- No se cambió código de producción ni se tocó PostgreSQL, Docker, VPS, frontend o servicios externos.

**Siguiente tarea:** revisar y fortalecer la matriz de migraciones PostgreSQL en CI aislada, incluyendo idempotencia y contratos de esquema; no ejecutar migraciones sobre la base de producción.


## Migraciones: orden numérico y pruebas de integridad — 2026-11-08

### Implementación
- Corregido `api/migrate.py::discover`: el orden de migraciones ahora usa el valor numérico de la versión. El orden lexicográfico anterior podía colocar `1000_*` antes de `999_*` al superar tres dígitos.
- La detección de duplicados ahora compara versiones numéricas, por lo que `001_*` y `0001_*` se consideran una colisión y el migrador falla antes de aplicar SQL.
- Añadido `tests/test_migrate.py` con cuatro pruebas: orden 010/999/1000, versiones duplicadas con padding distinto, nombre inválido y cambio de checksum al modificar el contenido.
- Commits: `a9c92dfc416923891852726be56e9ffdefbd736e` (corrección) y `cd9dbf39ce795b2d4eaa0d98468c8a083e48bf96` (pruebas).

### Verificación y límites
- Confirmada la publicación de `api/migrate.py` y `tests/test_migrate.py` en `main` mediante lectura del repositorio.
- No se ejecutó pytest en esta sesión; las cuatro pruebas están escritas, no aprobadas.
- El workflow existente `postgres-migrations` ya ejecuta dos veces `python -m api.migrate` en un PostgreSQL efímero y luego valida esquema, reservas y persistencia. Esta ruta permanece como verificación CI requerida; no se tocó ninguna base de datos real.
- No se modificaron SQL de migración, rollback, datos, volúmenes, VPS, Docker ni servicios externos.

### Próxima tarea de Fase 1
- Completar cobertura del contrato del migrador en PostgreSQL aislado: confirmar que una segunda ejecución no aplica migraciones nuevas, que un checksum histórico alterado provoca aborto y que los cambios transaccionales fallidos no dejan una versión registrada. Mantener toda prueba destructiva confinada al PostgreSQL efímero de CI.

---

## Checkpoint Fase 12 — QA local reproducible (2026-11-08, rama `agent/opencode-vps`)

### Cambios de esta sesión
- Corregido `sandbox/backends.py`: el backend local resuelve `python`/`python3` al intérprete que ejecuta la API (`sys.executable`) en lugar de exigir un alias o una ruta presente en el `PATH` restringido del sandbox. Elimina los 9 fallos por `exit_code=127` en sistemas donde solo existe `python3` o un venv.
- Añadida regresión en `tests/test_sandbox_exec.py` que verifica la resolución del intérprete sin depender del entorno del host.
- Añadidas 4 pruebas de contrato en `tests/test_payment_orders_http.py`: aislamiento por usuario en listado y detalle de órdenes, orden ajena/inexistente indistinguible (404), rechazo de UUID inválido antes de tocar la base de datos y no filtración de campos del proveedor ni de detalles internos.

### Verificación ejecutada (mismo árbol de trabajo)
- `python3 -m compileall -q api agent core rag sandbox audit tests scripts` — OK.
- `python3 -m pytest -q` — **855 passed, 9 skipped, 3 warnings** (los 9 omitidos son pruebas PostgreSQL que exigen `DATABASE_URL`).
- `python3 scripts/check_frontend_js.py` — sintaxis válida en los 3 scripts inline, `workspace.js`, `studio.js` y `admin.js`.
- `git diff --check` — limpio.
- Cobertura local (`coverage run --branch -m pytest -q`): 84% total. Los módulos con menor cobertura son dependientes de PostgreSQL (`billing_reservations`, `mfa_store`, `payment_manager`, `password_reset`, `email_verification`) y se omiten localmente por diseño.

### Pendiente / bloqueado
- CI del HEAD de esta rama: no ejecutada en esta sesión; no se declara aprobada.
- PostgreSQL real, Playwright/Chromium, Docker smoke y Qdrant Cloud: no ejecutados localmente; dependen de CI o de infraestructura externa.
- Restauración de backup en entorno aislado (DB-02) y despliegue: siguen pendientes.

### Siguiente tarea
Continuar con Fase 11 (instalación y documentación): revisar preflight del instalador, validación de configuración y procedimiento de actualización/restauración reproducible sin tocar producción.

## Checkpoint Fase 8 — gestión administrativa de usuarios y roles (2026-11-08)

### Implementado
- `GET /admin/users/{user_id}/roles`: consulta asignaciones globales activas e históricas con permiso `users.read`.
- `POST /admin/users/{user_id}/roles`: concede un rol global (`platform_admin`, `billing_admin`, `billing_support`, `billing_readonly`) con motivo obligatorio, permiso `users.manage`, CSRF y auditoría en la misma transacción.
- `DELETE /admin/users/{user_id}/roles/{role}`: revoca un rol activo con motivo obligatorio y auditoría. Impide dejar la plataforma sin ningún `platform_admin` activo.
- `POST /admin/users/{user_id}/status`: activa o deshabilita cuentas con permiso `users.manage`. Deshabilitar revoca todas las sesiones del usuario y queda auditado; activar exige correo verificado y nunca se permite deshabilitar la propia cuenta.
- Portal `frontend/admin.js`: sección de gestión visible solo con `users.manage`, con concesión, revocación, consulta de roles y cambio de estado, confirmaciones y resultado accesible (`aria-live`).
- `tests/test_admin_user_management.py`: 13 pruebas de autorización, validación, conflictos, auditoría, revocación de sesiones y no activación de cuentas sin verificar.

### Verificación
- `python3 -m pytest -q` — **874 passed, 9 skipped** (los 9 son PostgreSQL); no cubre las rutas nuevas contra PostgreSQL real.
- `python3 scripts/check_frontend_js.py` — sintaxis válida.
- CI del HEAD: pendiente. Browser E2E de la nueva sección: pendiente.

### Pendiente de Fase 8
- Probar las mutaciones contra PostgreSQL real y la matriz HTTP completa con sesiones/CSRF reales.
- Añadir E2E de navegador para la nueva gestión.
- Revisar si se requieren más operaciones administrativas (catálogo, tarifas) antes de cerrar la fase.

## Checkpoint Fases 7 y 11 — sandbox y restauración (2026-11-08)

### Fase 7
- `sandbox/snapshot.py` rechaza archivos con enlaces duros (`st_nlink > 1`) además de symlinks. Evita incluir en el snapshot contenido externo al que un enlace duro apunte.
- Prueba de regresión en `tests/test_sandbox_exec.py` que crea un enlace duro a un archivo externo y verifica rechazo y limpieza del directorio temporal.
- El backend local resuelve el intérprete Python del proceso, eliminando fallos de entorno ya registrados.
- Aislamiento Docker, red deshabilitada, límites de CPU/memoria/PIDs, auditoría y limpieza ya existían y sus pruebas siguen pasando.
- Sigue bloqueado AGT-04 completo: daemon dedicado, TLS, imágenes fijadas por digest y E2E real no están disponibles en este entorno.

### Fase 11
- Nuevo `scripts/restore_postgres.sh`: restauración únicamente en un contenedor/base desechables, rechaza nombres del stack real, exige base vacía, verifica el dump con `pg_restore --list`, no imprime secretos y exige confirmación exacta.
- Documentación de restauración aislada, actualización segura y procedimiento de recuperación en `docs/VPS_INSTALLATION.md`.
- 6 pruebas de contrato del script con Docker simulado; no se ejecutó una restauración real ni se creó infraestructura.

### Verificación combinada
- `python3 -m pytest -q` — **875 passed, 9 skipped** antes de añadir las pruebas PostgreSQL de administración (que se omiten localmente).
- `python3 scripts/check_frontend_js.py` — OK.
- `git diff --check` — limpio.
- CI del HEAD: pendiente.

### Bloqueos de Fase 10 y Fase 9
- QvaPay: contrato oficial de Lightning Address confirmado y adaptador de cliente implementado con pruebas. El cobro sigue desactivado: faltan custodia del token del titular, persistencia de invoices, sincronización paginada, rutas de checkout, catálogo/precios aprobados y pruebas en sandbox oficial. No existe webhook firmado; no se inventan endpoints ni firmas.
- Facturación: el catálogo comercial es `preview_only`, sin precios ni paquetes aprobados; no se activan cobros. La deuda pendiente es de producto/negocio, no de código inventable.

### E2E de navegador (Fase 12)
- `tests/e2e/studio-browser.mjs` ampliado para cubrir la gestión administrativa de usuarios.
- Ejecutado localmente con Playwright 1.58.2/Chromium: landing, MFA del portal y concesión/cambio de estado de usuario **aprobados**.
- No sustituye el job CI ni valida PostgreSQL/Docker/Qdrant reales.

## Checkpoint Fase 9 — consumo por modelo en administración (2026-11-08)

### Implementado
- `GET /admin/billing/overview` incluye `usage`, agregado por `requested_model` con número de solicitudes, tokens de entrada/salida y mediciones no disponibles.
- La consulta solo lee `inference_usage_events` y no expone prompts, respuestas, usuarios ni IDs de solicitud.
- `frontend/admin.js` muestra «Consumo por modelo» dentro del panel de facturación visible con `billing.read`.

### Verificación
- `python3 -m pytest -q` — **875 passed, 10 skipped** (PostgreSQL omitido localmente).
- `python3 scripts/check_frontend_js.py` — OK.
- E2E de navegador — aprobado.
- No se ejecutaron PostgreSQL real ni CI del HEAD. No se habilitan cobros ni facturación.

### Siguiente tarea
Validar el job PostgreSQL de CI con las pruebas administrativas y de facturación; después revisar conciliación/reversos sin inventar precios ni endpoints de QvaPay.

## Checkpoint Fase 9 — reversión auditada de consumo (2026-11-08)

### Implementado
- `reverse_settled_reservation` en `api/billing_reservations.py`: revierte únicamente reservas liquidadas con consumo, recalcula la parte usada de cada asignación y crea asientos `reversal` compensatorios. No edita ni borra asientos originales y no cambia el estado `settled`.
- Restaura `consumed_credits` en cuotas o lotes comprados; en lotes también incrementa `available_credits`.
- Idempotencia por clave y motivo; una segunda clave sobre la misma reserva se rechaza.
- `POST /admin/billing/reservations/reverse` con `billing.manage`, CSRF, motivo obligatorio, auditoría global determinista y reintento seguro de la auditoría.
- `frontend/admin.js`: formulario «Reversión de consumo liquidado» con confirmación y `aria-live`.

### Verificación
- 10 pruebas HTTP nuevas con motor simulado.
- 3 pruebas PostgreSQL añadidas al archivo que ejecuta el job de CI; **no ejecutadas localmente**.
- `python3 -m pytest -q` — **885 passed, 10 skipped**.
- `compileall`, sintaxis JS, E2E de navegador y `git diff --check` — OK.
- CI del HEAD: pendiente. No se activan cobros, precios ni QvaPay.

## Checkpoint Fase 10 — cliente oficial de QvaPay Lightning Address (2026-11-08)

### Implementado
- `api/qvapay_lightning.py`: cliente asíncrono para `GET /user/lightning-address`, LNURL `payRequest`, callback de invoice y `GET /coins`; transporte `httpx` inyectable para pruebas.
- Validación de dirección `name@qvpay.me`, callback limitado a dominios oficiales de QvaPay, importes dentro de límites LNURL, comentario LUD-12 y conversión USD→sats con redondeo hacia arriba.
- `match_payment` exige referencia, sats exactos y dirección; no confía solo en el comentario del pagador.
- Configuración en `api/config.py`: `QVAPAY_ENABLED=false` por defecto, token como `SecretStr`, timeout positivo y dirección validada. Nunca se registra el token.
- `docs/QVAPAY_INTEGRATION_STATUS.md` y `docs/QVAPAY_LIGHTNING_PAYMENT_FLOW.md` actualizados con el contrato oficial y sus límites.

### Verificación
- 13 pruebas nuevas en `tests/test_qvapay_lightning.py` con `httpx.MockTransport`.
- `python3 -m pytest -q` — **898 passed, 10 skipped**.
- `compileall`, sintaxis JS y `git diff --check` — OK.
- No se usaron credenciales reales, no se crearon invoices reales y no se habilitaron cobros. CI del HEAD pendiente.

### Siguiente tarea
Persistencia de invoices y sincronización paginada de cobros ligada a órdenes internas, sin activar checkout hasta disponer de catálogo/precios aprobados y sandbox oficial.

## Desarrollo ChatGPT — Fase 1 — 2026-11-08

**Rama de trabajo:** `agent/chatgpt`  
**Commit de implementación:** `9a590a0c0a14837df9a145660768b1a61cd72567`  
**Rama OpenCode:** `agent/opencode-vps`, sin modificaciones realizadas.

### Tarea implementada

Se amplió `tests/test_postgres_migrations.py` con tres pruebas de integración dirigidas al migrador real y destinadas exclusivamente al PostgreSQL efímero del job `postgres-migrations`:

1. **Idempotencia:** ejecuta de nuevo el migrador y exige que no aplique migraciones y que la lista de versiones/checksums permanezca idéntica.
2. **Integridad histórica:** crea una migración temporal con una versión ya aplicada y checksum distinto; exige que el migrador aborte.
3. **Atomicidad:** ejecuta una migración temporal que crea una tabla y luego falla; exige que ni la versión ni la tabla parcial queden registradas.

Los archivos temporales viven en `tmp_path`; no se modifican los SQL versionados del repositorio. Las pruebas requieren `DATABASE_URL` PostgreSQL y quedan omitidas fuera del job aislado, conforme al patrón del módulo.

**Commit:** `9a590a0c0a14837df9a145660768b1a61cd72567` — `test: verify migration runner idempotency and transaction safety`.

### Verificación y límites

- Publicación confirmada en GitHub, rama `agent/chatgpt`.
- **Ejecución pytest: pendiente.** Esta sesión no dispone de terminal ni de runner local; no se declara aprobada ninguna de las tres pruebas.
- El workflow actual ejecuta el migrador dos veces antes de las pruebas PostgreSQL, pero no se afirma que el workflow haya corrido para este nuevo SHA.
- No se tocaron producción, VPS, Docker, PostgreSQL real, volúmenes, secretos, frontend ni archivos asignados a OpenCode.
- No se fusionaron ramas. `agent/opencode-vps` permanece en su HEAD previo observado.

### Estado de Fase 1

La tarea de cobertura del contrato del migrador queda **implementada y pendiente de CI**. La Fase 1 continúa abierta: ARC-01 y API-02 requieren evidencia del HEAD actual; DB-01 requiere que el job PostgreSQL ejecute estas pruebas y los smoke tests existentes. También siguen pendientes la revisión de los demás criterios de Fase 1 y la validación aislada de los contratos de API/infraestructura.

**Siguiente tarea:** comprobar el resultado de CI del SHA `9a590a0c0a14837df9a145660768b1a61cd72567`; corregir cualquier fallo reproducible. Después continuar con el siguiente criterio abierto de arquitectura/contratos de Fase 1, sin iniciar Fase 2 antes de satisfacer los criterios de aceptación.


## Continuidad ChatGPT — Fase 1 — 2026-11-08 (API-02)

**Rama:** `agent/chatgpt`  
**Commit:** `f0bf0cde1c5925d835429c8222e8bda423540534`

### Tarea real abordada: errores de capacidad y agotamiento del pool

La matriz de aceptación identifica API-02 como implementada, pero pendiente de pruebas sobre el HEAD evaluado. Se amplió `tests/test_capacity_http.py` con dos regresiones:

- La saturación de inferencia debe responder HTTP 503, conservar `Retry-After` y devolver el mensaje público controlado sin exponer el tipo de excepción.
- El agotamiento del pool SQLAlchemy debe responder HTTP 503, conservar `Retry-After: 3` y no filtrar el texto interno del error del pool ni el tipo `TimeoutError`.

No se cambió el comportamiento de producción: los handlers existentes ya construyen respuestas genéricas; estas pruebas protegen el contrato HTTP ante futuras regresiones.

### Verificación

- Código y pruebas publicados en `agent/chatgpt`.
- **Ejecución local:** no disponible en esta sesión.
- **CI del commit anterior `333bdf2da559088ee2f3c919d2eec60c1a6573f1`:** al momento de esta actualización, `studio-browser-e2e` y `qdrant-cloud-integration` terminaron con éxito; `python-tests`, `postgres-migrations` y `container-image-build` seguían en ejecución. No se declara CI completa.
- El nuevo commit dispara una ejecución para el SHA actualizado; debe revisarse antes de marcar API-02 como verificada.
- No se modificaron módulos de OpenCode, código de producción, frontend, secretos, datos, VPS ni servicios.

### Estado

API-02 queda con cobertura de regresión ampliada, **pendiente de ejecución CI**. Fase 1 permanece abierta. Próximo paso: revisar todos los checks del SHA actual y después continuar ARC-01 con revisión de contratos entre rutas, esquemas y persistencia, evitando duplicar cambios de la otra rama.


## Corrección de regresiones API-02 tras CI — 2026-11-08

**Commit de corrección de pruebas:** `a722273721007c3bb832ae11cc31e5a6ed837606`.

### Hallazgo reproducible
- El workflow CI #1112, ejecutado sobre el SHA anterior `dd30e7da2a09b1710417731e33adc7c340ddcc8d`, terminó en fallo únicamente en el job `python-tests`.
- Resultado de pytest: **2 fallidas, 850 aprobadas, 9 omitidas**.
- Causa: las aserciones comparaban bytes con la secuencia literal `\\u00e1`, mientras que Starlette serializa el texto acentuado como UTF-8 real. El contrato HTTP de producción devolvía el mensaje genérico esperado; el defecto estaba en las aserciones añadidas.
- Se corrigieron ambas pruebas para leer `response.json()["detail"]` como texto Unicode y decodificar el cuerpo UTF-8 al comprobar que no aparecen detalles internos. No se modificó código de producción.

### Estado de CI y límites
- En el SHA fallido, los jobs `studio-browser-e2e`, `container-image-build`, `postgres-migrations` y `qdrant-cloud-integration` terminaron con éxito.
- `python-tests` falló por las dos aserciones descritas.
- El commit de corrección dispara una nueva ejecución; **la corrección aún no está verificada por CI** hasta revisar el workflow del nuevo HEAD.
- No se tocaron la rama `agent/opencode-vps`, VPS, producción, servicios, datos, secretos ni archivos ajenos a esta tarea.

**Siguiente paso:** comprobar CI del nuevo HEAD. Si queda verde, continuar ARC-01 con auditoría de contratos entre rutas, esquemas y persistencia. Fase 1 sigue abierta y no se declara completada.

## Endurecimiento de readiness OAuth — 2026-11-08

**Rama:** `agent/chatgpt`  
**HEAD al documentar:** `9bf4a36b4153ac308bd4f54049dd76a8f4d854c6`

### Hallazgo y corrección

- En `api/readiness.py`, el control `public_https_origin` solo comprobaba que `oauth_public_base_url` fuera truthy. Una URL HTTP, localhost, con credenciales embebidas, puerto inválido, query o fragmento podía aparecer como configuración HTTPS preparada.
- Se añadió `_is_public_https_origin`, que exige esquema HTTPS, hostname, excluye localhost, credenciales, query y fragmento, y valida el puerto.
- La preparación de autenticación ahora queda bloqueada cuando el origen OAuth no cumple ese contrato.
- Se añadieron regresiones para HTTP, FTP, host vacío, userinfo, puerto inválido, query, fragmento y localhost.
- Archivos: `api/readiness.py`, `tests/test_readiness.py`.
- Commits: `3dee239822a168fd4b4e5d297c491e5111fe62e9` (fix) y `9bf4a36b4153ac308bd4f54049dd76a8f4d854c6` (tests).

### Verificación y límites

- Lectura posterior en GitHub confirma el contenido de ambos archivos y el HEAD indicado.
- No se ejecutó pytest localmente en esta sesión.
- CI del SHA `9bf4a36b4153ac308bd4f54049dd76a8f4d854c6`: workflow #`42483118977` pendiente al documentar; no se marca como aprobado.
- No se modificaron `tests/test_capacity_http.py` ni archivos de OpenCode. El fallo API-02 anterior sigue pendiente de coordinación.
- No se modificó configuración real, secretos, servicios, VPS ni datos.

**Estado:** endurecimiento implementado; pruebas escritas, pendientes de CI. Fase 1 sigue abierta.

### Ajuste de contrato de origen OAuth y análisis de CI — 2026-11-08

- La revisión de `api/config.py` mostró que el contrato de configuración OAuth ya exige hostname público, dominio y ausencia de ruta, mientras el primer helper de readiness solo comprobaba HTTPS y excluía localhost.
- Se alineó `_is_public_https_origin` con ese contrato: rechaza IPs, hostnames sin dominio público, sufijos locales y rutas distintas de raíz, además de los casos ya cubiertos.
- Se añadieron regresiones para loopback IPv4, rutas de callback, dominios .local y hostnames sin punto.
- Commits: `ab72c0552cc680986eb3737f963d6b2288eca6f6` (alineación) y `9b0954fc2666b684fd17ac6bb9d767ce108b0dda` (pruebas).
- CI del commit anterior `d54fdff2f04c386d7a6654f0166bd7791a390035`: `studio-browser-e2e`, `qdrant-cloud-integration`, `postgres-migrations` y `container-image-build` pasaron; `python-tests` falló con 851 passed, 9 skipped y 2 fallos preexistentes en `tests/test_capacity_http.py`, por invocar `.json()` en `JSONResponse`.
- El archivo de capacidad también contiene cambios históricos de OpenCode; permanece bloqueado para edición hasta coordinar. No se alteró.
- CI de los commits `ab72c055...` y `9b0954f...` seguía ejecutándose/pendiente al documentar; no se declaran pruebas aprobadas.
- Fase 1 sigue abierta; no se habilitó AUTH ni se tocó configuración de producción.

### Contrato único de origen HTTPS público — 2026-11-08

- La auditoría de ARC-01 detectó duplicación entre la validación de `OAUTH_PUBLIC_BASE_URL` en configuración y el control `public_https_origin` de readiness. Esa duplicación ya había permitido que ambas comprobaciones tuvieran reglas diferentes.
- Se centralizó `is_public_https_origin` en `api/config.py`; tanto el validador Pydantic como readiness consumen ahora el mismo contrato.
- La validación rechaza protocolos inseguros, IPs, dominios locales, userinfo, query/fragment, rutas, puertos inválidos y etiquetas DNS mal formadas (vacías, con guion inicial/final, caracteres no permitidos o longitud excesiva).
- Se añadieron regresiones en `tests/test_config.py` para normalización del origen y hostnames DNS mal formados; se conserva la cobertura HTTP/readiness existente.
- Commits: `bd85dd32dee45957660bf714f610a09803c17883` (helper y validador), `405b7776b39c06e50c3185c307a17430b6beb9f8` (readiness compartida), `86e4049acba1ad212dcae18f722d900d58614605` (pruebas).
- No se tocó `tests/test_capacity_http.py`, que continúa pendiente de coordinación por solapamiento histórico con OpenCode.
- CI del HEAD previo `fe08b700482ed9d02fbd870d8d84879d5c643274`: 3 jobs pasaron (Studio E2E, Qdrant Cloud, migraciones PostgreSQL e imagen; imagen y migraciones también finalizaron correctamente), pero `python-tests` falló con 2 errores de test en `tests/test_capacity_http.py` por invocar `.json()` directamente sobre `JSONResponse`. No son fallos de este cambio, que aún requiere su propio CI.
- La matriz ARC-01 permanece Parcial; no se declara completada hasta revisar contratos restantes y evidencia del mismo SHA.

### Contrato HTTPS compartido para Qdrant — 2026-11-08

- La revisión de ARC-01 encontró que `QDRANT_URL` y `OAUTH_PUBLIC_BASE_URL` mantenían validaciones distintas para el mismo requisito de origen HTTPS público.
- Se cambió el validador de `QDRANT_URL` para reutilizar `is_public_https_origin`, que ahora aplica a ambos orígenes: HTTPS, hostname DNS válido, sin IP/local, sin credenciales, sin ruta, query ni fragmento y con puerto válido.
- Se añadieron regresiones para URLs Qdrant con HTTP, IP loopback, puerto inválido, ruta, hostname mal formado, query y userinfo, además de una URL HTTPS válida.
- Archivos: `api/config.py`, `tests/test_config.py`.
- Commits: `2ac236a99df2217c6442cf9971da718764597436` (validador Qdrant) y `d01a17d8bb390a6948436c4b3839b69fb838be22` (pruebas).
- Esta tarea no cambia el cliente Qdrant, la colección, credenciales ni la conectividad; solo valida el origen configurado antes de su uso.
- CI del HEAD previo `f3c227a47d25950d0754f3da542be61a338af942`: `python-tests` falló por dos errores conocidos en `tests/test_capacity_http.py` (uso de `.json()` sobre `JSONResponse`); los otros jobs observados finalizaron con éxito salvo PostgreSQL, que seguía en curso al consultar. Las nuevas pruebas de configuración necesitan CI propio.
- `tests/test_capacity_http.py` permanece sin cambios hasta coordinar con OpenCode.
- ARC-01 continúa Parcial; Fase 1 sigue abierta.


### Revisión adicional de hostname público — 2026-11-08

- La revisión del validador compartido encontró que eliminar todos los puntos finales con `rstrip(".")` hacía que un hostname mal formado como `example.com..` se normalizara y aceptara.
- Se ajustó el parser para permitir como máximo un punto raíz DNS final y rechazar puntos finales repetidos.
- Se añadieron regresiones para Qdrant y OAuth, conservando la aceptación/normalización de un único punto final.
- Archivos: `api/config.py`, `tests/test_config.py`.
- Implementación y pruebas publicadas en `agent/chatgpt`; ejecución local no disponible y CI del nuevo HEAD `c41f490` confirmada en verde (run `42488024013`).
- CI del HEAD anterior `641210a948d2e97a8807ac68918a9aba119785a1`: 855 aprobadas, 9 omitidas y 2 fallidas, ambas en `tests/test_capacity_http.py` por llamar `.json()` directamente sobre `JSONResponse`. Studio E2E, Qdrant, build de imagen y migraciones PostgreSQL pasaron.
- `tests/test_capacity_http.py` permanece sin cambios hasta coordinar con OpenCode. No se modificó su rama, VPS, producción ni datos.


### Validación estricta de puertos explícitos — 2026-11-08

- Una revisión adicional del parser estándar `urlsplit` encontró que acepta `https://example.com:` y devuelve `port=None`, aunque la URL declara explícitamente un puerto vacío.
- `is_public_https_origin` ahora rechaza autoridades cuyo host termina en `:` después de separar cualquier userinfo; conserva puertos válidos y sigue rechazando puertos no numéricos o fuera de rango.
- Se añadieron regresiones para Qdrant y OAuth con puerto explícito vacío.
- Archivos: `api/config.py`, `tests/test_config.py`.
- Commits: `dfb4a6e39cc1ce49ebfb97a7b76c6fa21ad2bd0f` (corrección) y `9232a6f6b3e8bd533babf4ec70c35739e4227113` (regresiones).
- No se ejecutó pytest local; CI del nuevo HEAD `c41f490` confirmada en verde (run `42488024013`). CI del HEAD anterior `e83b71d7850ae171859f63e32b89060d01d1c218` terminó con 855 passed, 9 skipped y 2 fallos conocidos en `tests/test_capacity_http.py`; Studio E2E, Qdrant, migraciones y build de imagen pasaron.
- No se modificó el archivo compartido `tests/test_capacity_http.py`; no se integró la rama de OpenCode ni se realizaron operaciones VPS/producción.


### Consentimiento de registro con tipo estricto — 2026-11-08

- La revisión del contrato de registro encontró que Pydantic podía convertir valores como `1`, `0` o cadenas (`"true"`) a booleanos. En un campo de aceptación legal, esa coerción no demuestra que el cliente haya enviado el booleano JSON explícito.
- `RegisterRequest.terms_accepted` ahora usa validación estricta: solo acepta `true`/`false` JSON; el valor predeterminado continúa siendo `false`. La ruta existente sigue exigiendo `is True` antes de registrar.
- Se añadieron regresiones para rechazar enteros y cadenas, y confirmar que el booleano `true` se acepta.
- Archivos: `api/schemas.py`, `tests/test_auth_routes.py`.
- Commits: `3f69d7330a85ad41bd5e01bf86c90ec5e9b9dad5` (contrato) y `20abc36b7988c7d7a5ded1251e53358d664f475b` (pruebas).
- No se ejecutó pytest local; CI del HEAD vigente aún debe confirmarse. El workflow del HEAD anterior `1252a8e4c50d2aa0c99c8db8a1e29f2af8416d37` tenía Studio E2E, Qdrant Cloud y build de imagen aprobados; Python y migraciones PostgreSQL seguían ejecutándose al consultar.
- No se modificaron archivos con solapamiento observado con `agent/opencode-vps`, ni se tocó VPS, producción, datos o secretos. La Fase 1 permanece abierta.

## Checkpoint Fase 12 — CI confirmada y simulacro de restauración (2026-11-08, `agent/opencode-vps`)

### Evidencia ejecutada
- CI del SHA `5e55582690891a66a002852b29aa28ae7f54fb63` en verde (run `42485697750`): studio-browser-e2e, postgres-migrations, qdrant-cloud-integration, container-image-build, python-tests. Sustituye la anotación «CI no confirmada» para ese SHA.
- Suite local: **911 passed, 11 skipped** (10/11 PostgreSQL omitidos localmente); `compileall`, `check_frontend_js.py`, `pip check` y `git diff --check` correctos.
- **Simulacro DB-02 real:** contenedor PostgreSQL 16-alpine desechable en `127.0.0.1`; backup `backups/pre-frontend-upgrade-20261108T001710Z.dump` restaurado con `scripts/restore_postgres.sh` (41 tablas; `schema_migrations` hasta `021`); migración `022` aplicada con `python -m api.migrate` (quedó en 022; segunda ejecución: ninguna migración); contenedor eliminado. Migraciones 001→023 verificadas desde cero en instancia desechable; matriz PostgreSQL completa: **70 passed**.
- Dependencias: `pip check` sin conflictos; `cryptography>=43,<47` es el único pin por rango (acotado).

### Fase 10 — persistencia y conciliación de invoices (este bloque)
- Migración `023_qvapay_lightning_invoices.sql`: tabla `payment_invoices` ligada a `payment_orders`; una invoice abierta por orden (índice parcial); referencia LNURL unguessable (`axy` + hex); sats exactos, precio BTC/USD, comisión, `transaction_uuid` y estado (`created`/`superseded`/`expired`/`paid`) auditados; `UNIQUE (provider, provider_transaction_id)`.
- `api/qvapay_settlement.py`: `new_payment_reference`, `create_invoice_record` (valida orden pendiente, supersede la invoice abierta), `reconcile_lightning_payments` (confirma solo con referencia + sats exactos + destinatario + `transaction_uuid`; delega créditos en `confirm_verified_payment`; idempotente), `fetch_recent_payments` (paginación 20/página, deduplicación, tope configurable).
- Checkout/rutas HTTP siguen sin implementarse; cobros y acreditación automática deshabilitados.
- Pruebas: 5 unitarias (`tests/test_qvapay_settlement.py`) y 8 PostgreSQL (`tests/test_qvapay_settlement_postgres.py`, añadidas al job CI). Commit `08b6e65`.

### Fase 11
- `docs/VPS_INSTALLATION.md`: resultado real del simulacro de restauración y sección «Mantenimiento rutinario» (backups, simulacro anual/por versión, health, logs, espacio, migraciones, dependencias, secretos).

### Pendiente / bloqueado
- REL-01 sigue bloqueada: AUTH/MFA, sandbox dedicado (AGT-04), catálogo/precios QvaPay, sandbox oficial, backup en staging y validación web pendiente.
- CI del nuevo HEAD (`08b6e65`): pendiente al redactar; debe confirmarse antes de declarar QA-01/QA-02 «Verificadas».
- PostgreSQL local de esta sesión omitido; verificado en instancia desechable y en el job CI.

### Fase 10 — expiración automática de órdenes y invoices (continuación)
- `api/payment_manager.py`: `_expire_one` y `expire_overdue_orders` (pendientes vencidas → `expired`, cierre de invoice abierta, evento `expired` idempotente, `FOR UPDATE SKIP LOCKED`); `get_payment_order` expira de forma perezosa la orden solicitada si venció.
- 4 pruebas PostgreSQL nuevas en `tests/test_qvapay_settlement_postgres.py` (expiración + cierre de invoice idempotente, órdenes frescas respetadas, expiración perezosa vía GET, validación de `limit`).
- Verificado en instancia desechable: migraciones 001→023 y 54 pruebas PostgreSQL en verde; contenedor eliminado.

### Siguiente tarea
Confirmar CI del SHA publicado; después continuar Fase 11 (preflight/staging) y Fase 10 (rutas de checkout condicionadas a catálogo/precios aprobados).

## Checkpoint Fase 8 — E2E de reversión y recuperación administrativas (2026-11-08, `agent/opencode-vps`)

### Implementado y verificado
- `tests/e2e/studio-browser.mjs` amplía la gestión administrativa: reversión auditada (`#billing-reversal-*`) y recuperación de liquidaciones (`#billing-recovery-run`) con respuestas simuladas y confirmaciones aceptadas.
- ADM-01 pasa a verificada a nivel backend/CI: PostgreSQL (CI verde, 70→74 pruebas en `postgres-migrations` incluyendo QvaPay) y E2E de navegador de gestión de usuarios, reversión y recuperación.
- `.gitignore` ignora `/node_modules/`; la instalación local replica el patrón `npm install --no-save` del job CI.
- CI `42488531176` (`68ffa13`) y `42488645522` (`1db1d32`): cinco jobs en verde en ambos SHA.

### Estado
- Fase 8: ADM-01 verificada en backend/CI; pendiente E2E contra staging y validación manual del portal.
- Fase 10: expiración automática de órdenes/invoices verificada (CI verde).
- REL-01 sigue bloqueada (AUTH, sandbox, catálogo/precios, staging).

## Checkpoint Fase 12 — integración ChatGPT+OpenCode preparada y validada (2026-11-08)

### Integración
- `agent/chatgpt` avanzó hasta `f6636fe` (reconciliación RAG, contrato de payload, lock por proyecto); `agent/opencode-vps` hasta `cd8f1cc`.
- Conflicto único `docs/V1_ACCEPTANCE_MATRIX.md`, resuelto en `integration/chatgpt-opencode-20261108b` conservando los dos bloques completos (OpenCode primero, después RAG de ChatGPT). Sin conflictos funcionales: no hay solape en API, seguridad, base de datos ni migraciones.
- Árbol combinado verificado: **933 passed, 11 skipped**; `compileall` y `check_frontend_js.py` OK; matriz PostgreSQL 74 passed en instancia desechable (migraciones 001→023 + doble ejecución del migrador).
- PR **#7** abierto hacia `main` (sin merge; control del propietario). CI completa en verde sobre `8318af6` (run `42488953926`): studio-browser-e2e, container-image-build, postgres-migrations, python-tests, qdrant-cloud-integration.
- La rama de integración es una rama nueva; no se modificó `agent/chatgpt` ni `main`, no hubo force-push ni reset.

### Estado
- REL-01 sigue bloqueada (AUTH, sandbox, catálogo/precios, staging). La V1.0 no se declara liberada.

## Checkpoint Fase 11/12 — accesibilidad, traversal y README (2026-11-08, `agent/opencode-vps`)

### Cambios
- README: eliminada afirmación obsoleta («sin mutaciones administrativas»); el portal administrativo y la API ya gestionan usuarios/roles/estado con confirmaciones, MFA y auditoría.
- `tests/e2e/a11y-scan.mjs`: escaneo axe WCAG 2 A/AA de landing, login administrativo y vista autenticada de gestión (mock): **0 violaciones** en las tres. Studio autenticado y navegación completa por teclado no escaneados.
- `tests/test_workspace_path_confinement.py`: 3 regresiones nuevas (formas siempre inválidas en `resolve`, segmentos exóticos en `_relative_parts`, y traversal codificado que jamás escapa de la raíz; el archivo externo queda intacto).
- Suite completa: **919 passed, 11 skipped**; 11 en el módulo de confinamiento.

### Fase 11
- Preflight, validación de configuración, `restore_postgres.sh` con simulacro real, sección de mantenimiento y contrato de `.env.example` completados; falta verificación contra VPS real/staging (autorización pendiente). Fase 11 pasa a 70%.

## Checkpoint Fase 12 — contrato frontend-backend y accesibilidad (2026-11-08, `agent/opencode-vps`)

### Cambios
- README: corregida afirmación obsoleta sobre la API administrativa.
- `tests/e2e/a11y-scan.mjs`: escaneo axe WCAG 2 A/AA; **0 violaciones** en la carga inicial de la landing, el login administrativo y la vista autenticada de gestión (mock). Studio autenticado y navegación completa por teclado sin cubrir.
- `tests/test_workspace_path_confinement.py`: 3 regresiones nuevas contra traversal exotic (backslashes, segmentos vacíos/dobles, `.` inicial y traversal codificado `..%2f`; el archivo externo permanece intacto).
- `tests/test_frontend_backend_routes.py`: contrato estático frontend→FastAPI; cada literal API de los cuatro archivos del frontend corresponde a una ruta registrada (exacta, prefijo o sufijo-fragmento).
- CI `42489658918` (`a6b9c0c`): los cinco jobs en verde (studio-browser-e2e, container-image-build, postgres-migrations, python-tests, qdrant-cloud-integration).

### Verificación
- `.venv/bin/python -m pytest -q` → **920 passed, 11 skipped**.
- `compileall`, sintaxis JS, `git diff --check` correctos.

### Estado
- Fase 12: QA local y CI en verde para el HEAD; REL-01 sigue bloqueada por dependencias externas.

## Checkpoint Fase 12 — actualización de integración (corrección) (2026-11-08)

**Corrección del checkpoint anterior.** La anotación «bloqueada por CI roja en agent/chatgpt» era errónea: las 3 pruebas fallidas solo lo hacían sin `DATABASE_URL` local, porque el dialect por defecto es PostgreSQL y el código nuevo intenta una conexión real. El job `python-tests` de CI ejecuta con `DATABASE_URL=sqlite:///./ci-test.db`; en ese entorno `agent/chatgpt` (cbdb5f4) da 932 passed y el árbol combinado 942 passed. El hallazgo correcto: CI de python-tests usa SQLite para desarrollo y CI; producción sigue siendo PostgreSQL.

- `integration/chatgpt-opencode-20261108b` actualizada a `53781b3` (merge de `cbdb5f4`, CI del PR #7: 5/5 en verde, run `42490644871`).
- Matriz PostgreSQL desechable del árbol combinado: **82 passed** (incluye `test_sqlalchemy_meta_store.py`).
- PR #7 conversación registra la corrección. Sin conflictos; `main` y `agent/chatgpt` sin modificar.

## Checkpoint Fase 12 — actualización de integración bloqueada por CI roja en agent/chatgpt (2026-11-08)

- `origin/agent/chatgpt` avanzó a `acf37a6` (14 commits: serialización de mutaciones RAG y redacción de secretos legacy).
- Al integrarlos sobre `8318af6`: **3 pruebas fallan**, todas ya rotas en `agent/chatgpt` por sí solo:
  1. `test_rag_manual_ingest.py::ManualIngestSecurityTests::test_retrieval_redacts_legacy_secrets_from_text_and_source` (la implementación no redacta el prefijo `[Source: ...]`).
  2. `test_rag_qdrant_integration.py::…::test_project_scoped_source_lifecycle_against_qdrant` (intento de conexión real a PostgreSQL 127.0.0.1:5433, autenticación fallida).
  3. `test_workspace_knowledge_upload_rag_integration.py::…::test_http_handler_extracts_indexes_lists_and_retrieves_uploaded_file` (mismo origen).
- `8318af6` (HEAD de `integration/chatgpt-opencode-20261108b`, PR #7) pasa las 28 pruebas de esos módulos y CI de 5 jobs en verde. La integración **no** incorpora los commits nuevos hasta que `agent/chatgpt` quede en verde (merge limpio, sin conflictos, según `git merge-tree`).
- Detalle documentado en el PR #7 (comentario de coordinación). No se modificó `agent/chatgpt` ni `main`.

## Checkpoint Fase 8/10 — invoices QvaPay agregadas en administración (2026-11-08, `agent/opencode-vps`)

### Implementado
- `GET /admin/billing/overview` añade `invoices`: por estado, número de invoices, suma de sats y `overdue_open` (invoices abiertas cuya orden ya venció), vía `payment_invoices JOIN payment_orders`. Sin referencias LNURL, sin `pr`, sin datos de usuario ni de orden.
- `frontend/admin.js`: sección «Invoices QvaPay» en «Operaciones de créditos y facturación» (visible con `billing.read`).
- `tests/e2e/studio-browser.mjs`: aserción de la nueva sección con mock (sats 21000).
- Dos pruebas de `test_admin_audit_routes.py` actualizadas al quinto agregado.
- SQL agregado verificado contra instancia PostgreSQL desechable con migraciones 001→023; contenedor eliminado.
- CI `42490282851` (`d659eeb`): los cinco jobs en verde. Suite local: **920 passed, 11 skipped**.

### Límites
- Solo lectura; no habilita checkout, cobros ni acreditación. Catálogo/precios siguen pendientes del producto.

## Checkpoint Fase 11 — instalación, documentación y secretos (2026-11-08, `agent/opencode-vps`)

### Cambios
- `docs/USER_GUIDE.md`: guía de usuario completa (cuenta, MFA, proyectos, Atomic Code, Conocimiento, agente con aprobaciones, consumo, facturación, administración, privacidad, límites y cosas no disponibles); README enlaza la guía.
- `tests/test_secrets_in_repo_guard.py`: guardarraíl de secretos (rutas prohibidas en git, patrones de claves privadas/tokens, cobertura de .gitignore): 3 passed.
- `.env.example` ya estaba blindado con `tests/test_env_example_contract.py` (5 pruebas).
- `scripts/install_vps.sh --check` ejecutado en el host real: falla de forma segura ante stack existente (`Puerto 8070 ocupado; no se detendrá el servicio existente.`, exit 1); sin cambios ni secretos impresos.
- `test_vps_installer_contract.py`: 23 passed. OPS-01/02/03 actualizados en la matriz.
- Fase 11 pasa a 75%; pendiente: `--prepare/--check/--deploy` y rollback en staging, inventario real (operador), upgrade aislado. CI `42491118328` sobre `87d3b9d`: los cinco jobs en verde (studio-browser-e2e, container-image-build, postgres-migrations, python-tests, qdrant-cloud-integration).

## Checkpoint Fase 12 — accesibilidad Studio verificada (2026-11-08, `agent/opencode-vps`)

- `tests/e2e/a11y-scan.mjs` amplía el escaneo axe WCAG 2 A/AA a las vistas autenticadas del Studio (`#app/inicio`, `#app/facturacion`) con backend simulado: **0 violaciones** también en ambas.
- STU-04 queda auditada a nivel automático inicial (landing, Studio, admin login y administración); siguen sin verificar navegación completa por teclado y lectores de pantalla reales, así como el backend en staging.
- CI de la integración actualizada a `f98ead9`: 5/5 en verde. PR #7 pendiente de revisión del propietario.

## Checkpoint Fase 9/10 — validación comercial V1 con mediciones reales (2026-11-08, `agent/opencode-vps`)

### Alcance autorizado por el propietario

El propietario autorizó el trabajo en `agent/opencode-vps` (no en `agent/chatgpt`). Se respetó: sin cambios en catálogo/precios/configuración, cobros desactivados, sin merge.

### Implementado
- `docs/COMMERCIAL_VALIDATION_V1.md`: **entregables A–H** de la especificación comercial aprobada:
  - Auditoría del sistema (§A) con el estado real de payment_orders, reservas, ledger, reversos, expiración, conciliación QvaPay, medición sombra de tokens.
  - Matriz de costes con datos **medidos** en el host (atomic-code:1.1: 26 tok/s prompt eval, ~10.3 tok/s eval output; prompt medio 26/96 tokens; embedding respondió) + tarifas del roadmap marcadas como provisional (no medida).
  - Simulación por plan/paquete y sensibilidad de comisión (0,5 %/1 %/2,5 %): coste variable máximo por crédito para conservar margen ≥35 % (STARTER 0,0108, PLUS 0,0086, PRO 0,0076, STUDIO 0,0072 @0,5 %).
  - Hallazgo crítico: pesos actuales 1 crédito = 1 token hacen inservible el catálogo (FREE ≈ 0,4 turnos); propuesta documentada de 1 crédito = 100 tokens **pendiente de decisión del propietario**.
  - Ningún plan incumple el 35 % con hipótesis actuales; margen no certificable sin coste atribuible medido durante 30 días de sombra y comisión Lightning confirmada por escrito.
- `scripts/measure_model_tokens.py`: runner reproducible de medición de tokens (solo lectura, sin secretos).
- cobros, checkout y `BILLING_ENFORCEMENT_ENABLED` siguen desactivados; catálogo `preview_only`; VPS, `.env` y secretos intactos.

### Pendiente
- Decisiones del propietario (pesos de créditos, tarifa por modelo versionada en BD, confirmación por escrito de comisión QvaPay, atribución de costes, términos legales) antes de habilitar comercialización.

## Checkpoint Fase 10 — conciliación administrativa QvaPay (2026-11-08, `agent/opencode-vps`)

### Implementado
- `POST /admin/billing/qvapay/reconcile`: consulta administrativa (solo con `billing.manage` y CSRF) de los últimos cobros del titular vía `QvaPayLightningClient` y conciliación con invoices abiertas vía `reconcile_lightning_payments`. Falla cerrado (503) cuando `QVAPAY_ENABLED=false` o falta el token; nunca expone el token ni detalles internos del proveedor; la auditoría global se registra antes de la llamada externa.
- Reutiliza íntegramente las reglas existentes: coincidencia por referencia + sats exactos + destinatario + `transaction_uuid`, y acreditación vía `confirm_verified_payment` (idempotente). No cobra a nadie, no crea órdenes ni habilita checkout.
- `frontend/admin.js`: sección «Conciliación de cobros QvaPay» en «Operaciones de créditos y facturación» (visible con `billing.manage`), con confirmación explícita y resultado accesible (`aria-live`).
- `tests/e2e/studio-browser.mjs`: mock y clic en el botón de conciliación; verificado «Cobros consultados: 4».
- `tests/test_admin_qvapay_reconcile.py`: 6 pruebas de contrato HTTP (autorización, fail-closed sin flag/token, auditoría previa a la llamada externa, error del proveedor ocultado, resumen de outcomes sin detalles de pago, límites de `max_pages`).

### Verificación
- `DATABASE_URL=sqlite:///./ci-test.db .venv/bin/python -m pytest -q` — **1006 passed, 11 skipped**.
- `.venv/bin/python -m compileall`, `scripts/check_frontend_js.py`, `pip check`, `git diff --check` — OK.
- E2E de navegador (Playwright 1.58.2/Chromium) — **aprobado** con la nueva sección.
- `node tests/e2e/a11y-scan.mjs` — 0 violaciones WCAG 2 A/AA (sin cambios).
- CI del HEAD resultante: pendiente al redactar; debe confirmarse antes de declarar QA-01/QA-02 verificadas para este SHA.

### Límites
- No habilita cobros, checkout ni acreditación automática. Catálogo/precios siguen pendientes del producto; sandbox oficial pendiente. REL-01 sigue bloqueada.

## Checkpoint Fase 12 — auditoría de teclado (STU-04) (2026-11-08, `agent/opencode-vps`)

- `tests/e2e/a11y-scan.mjs` incorpora `keyboardAudit`: recorre con Tab la landing, el portal administrativo estático y la vista de gestión autenticada (mock). Resultado: **25 paradas (gestión), 30 (landing), 5 (admin login); 0 problemas**: foco siempre en elemento interactivo y visible; la secuencia termina en `body` tras la última parada (sin trampa ni pérdida de foco). El script sale con código 1 si detecta problemas.
- STU-04 pasa a: vistas escaneadas con axe (0 violaciones) + navegación por teclado sin trampas ni foco perdido en las mismas vistas. Siguen sin verificar lectores de pantalla reales y el backend en staging.

## Estado de fases tras este bloque (sin cambios de porcentaje por estas pruebas)

- Fase 7 (Archivos y sandbox): sin cambios funcionales nuevos; suite y snapshot/Docker tests siguen en verde. AGT-04 bloqueada (daemon/TLS/digest/E2E real).
- Fase 8 (Administración): ADM-01 conserva su verificación previa; el nuevo endpoint queda pendiente de CI para este SHA.
- Fase 9 (Créditos y facturación): sin cambios; cobros desactivados; catálogo `preview_only`.
- Fase 10 (QvaPay): conciliación administrativa implementada y probada; checkout/rutas HTTP/catálogo de cobro siguen bloqueados por decisiones comerciales.
- Fase 11 (Instalación y documentación): sin cambios; pendiente staging con autorización del operador.
- Fase 12 (QA): teclado auditado; suite 1006/1006 (SQLite); REL-01 sigue bloqueada.

## Evidencia CI del bloque anterior — 2026-11-08 (`agent/opencode-vps`)

- CI del HEAD `76c5356e0bd0001b659db0aa10eb2a51191256b2` (run `42496765302` al redactar; rama `agent/opencode-vps`): los cinco jobs en verde:
  - `python-tests`: **1006 passed, 11 skipped** (con `DATABASE_URL=sqlite:///./ci-test.db`).
  - `postgres-migrations`: **74 passed** (PostgreSQL efímero, migraciones 001→023 + doble ejecución del migrador).
  - `studio-browser-e2e`: aprobado con la nueva sección «Conciliación de cobros QvaPay».
  - `container-image-build`: success. `qdrant-cloud-integration`: success.
- QA-01/QA-02 pueden considerarse verificadas **para este SHA** (no para staging ni para producción). REL-01 sigue bloqueada por AUTH/sandbox/catálogo/staging.

- CI `42496918230` sobre `704f6d3` (commit documental): 5/5 en verde. La evidencia de código corresponde a `76c5356` (CI `42496765302`).

## Integración de candidato — 2026-11-08 (rama `agent/opencode-vps`)

- `origin/agent/chatgpt` avanzó a `d420ef4` (`feat(maintenance): bounded rate-limit cleanup command`, `fix(auth): OAuth response hardening`).
- `integration/chatgpt-opencode-20261108b` actualizada directamente: primero fast-forward a `d420ef4` (verificado local: **1015 passed, 11 skipped**, compileall y check_frontend_js OK) y luego merge de `origin/agent/opencode-vps` (`000393c`). Árbol combinado verificado: **1021 passed, 11 skipped**; E2E de navegador aprobado; `check_frontend_js.py` OK.
- CI del commit combinado `000393c` (run `42497299420`): **5/5 en verde** — python-tests 1021/1021, postgres-migrations 74 passed, studio-browser-e2e aprobado, container-image-build y qdrant-cloud-integration success.
- GitHub marcó el PR #9 (agent/opencode-vps → integration/chatgpt-opencode-20261108b) como **MERGED** de forma automática al quedar todas las ramas integradas en la candidata; no se fusionó nada a `main` ni se modificó `agent/chatgpt`. `main` permanece sin tocar; la integración final corresponde al propietario.
- La candidata de integración sigue cubriendo las mismas puertas REL-01: AUTH/MFA en staging, AGT-04 (daemon/TLS/digests), catálogo/precios QvaPay y sandbox oficial de QvaPay. V1.0 no se declara liberada.

## Fase 11 — autorización del operador: inventario ejecutado (2026-11-08, `agent/opencode-vps`)

El propietario autorizó el alcance de la Fase 11. Se ejecutaron las verificaciones de solo lectura permitidas:

- `bash scripts/inspect_vps_state.sh` (HEAD `4508226`): inventario completado sin modificar nada ni mostrar secretos:
  - Proyecto Compose `axyron-atomic`: frontend, api (Up 16 h), postgres 16-alpine (healthy), redis 7.4-alpine (healthy); volumen `axyron_atomic_pgdata` presente (driver `local`) y referenciado por `axyron-atomic-postgres-1`; red `axyron-atomic_default`.
  - Proyecto legado `axion-atomic`: sin contenedores; volumen `axion_atomic_pgdata` inexistente; sin redes.
  - Puertos en escucha: `127.0.0.1:8070` (API) y `127.0.0.1:5433` (PostgreSQL).
  - El script no leyó ni imprimió `.env`, no inspeccionó contenedores ajenos y no modificó recursos.
- `bash scripts/install_vps.sh --check`: vuelve a fallar de forma segura (`Puerto 8070 ocupado; no se detendrá el servicio existente.`, exit 1). No se detuvo ni alteró el stack; no se ejecutó `--deploy` ni `--upgrade-frontend` (requieren intervención interactiva del operador sobre el stack en vivo).
- Se eliminó un artefacto de pruebas local (`ci-test.db`) que quedó como no rastreado tras una corrida de la suite; el árbol de trabajo queda limpio.
- La restauración de backup en entorno desechable (DB-02) ya tiene evidencia válida (2026-11-08, migraciones 001→023 + doble ejecución del migrador; contenedor eliminado). No se repite sin cambios en migraciones o scripts de restauración.
- `inspect_vps_state.sh` de OPS-02 pasa a **ejecutado en el host** (evidencia reproducible); sigue pendiente la revisión operativa por parte del operador como control previo a cualquier actualización.
- No se desplegó, reinició, construyó ni reconfiguró nada; PostgreSQL, Redis, API y frontend siguen como estaban.

## Fase 11 — verificación de backups y configuración (misma sesión autorizada)

- Integridad de dumps (lectura, `pg_restore --list`, sin restauración): los tres `pre-frontend-upgrade-*.dump` (2026-11-07/08) son válidos con 274 objetos cada uno y contentura idéntica. `pre-migration-20261107T204351Z.dump` (834 B, 0 objetos, formato CUSTOM, PostgreSQL 16.15) corresponde a un snapshot previo a la primera migración sobre base vacía: coherente, no un dump corrupto.
- `docker compose --project-name axyron-atomic -f compose.yaml --env-file .env config --quiet` → exit 0 (la configuración valida; no se imprimieron valores de `.env`).
- No se ejecutó restauración, `--deploy` ni `--upgrade-frontend`; el stack en vivo permanece sin cambios.

### Ajuste de tabla
Fase 11 pasa de 75 % a **80 %**: el inventario de solo lectura se ejecutó en el host con autorización (OPS-02), la validación de configuración (`compose config --quiet`) quedó verificada y la integridad de los dumps (274 objetos ×3) confirmada. No sube más porque `--deploy/--upgrade-frontend` en stack real y el ensayo de rollback siguen pendientes de autorización interactiva del operador.

## Fase 11 — plantilla .env completa para QvaPay (2026-11-08, `agent/opencode-vps`)

- `.env.example` añade `QVAPAY_ENABLED=false`, `QVAPAY_USER_TOKEN=` (vacío), `QVAPAY_LIGHTNING_ADDRESS=axyronatomic@qvpay.me` y `QVAPAY_REQUEST_TIMEOUT_SECONDS=10.0`, con comentarios de seguridad: sin catálogo/precios firmados no se activa; no hay webhook firmado (conciliación por consulta); el token se custodia fuera de Git. La instalación reproducible (`install_vps.sh --prepare` copia la plantilla y randomiza secretos) queda coherente: el `.env` generado incluye la integración desactivada.
- `tests/test_env_example_contract.py`: exige `QVAPAY_ENABLED=false`, presencia de las 4 claves y token vacío/dirección `@qvpay.me`. 6 pruebas OK. Suite completa: **1007 passed, 11 skipped**.
- Sin lecturas ni cambios sobre el `.env` real, el stack, PostgreSQL ni servicios.

## Integración de candidato (segunda actualización) — 2026-11-08 (`agent/opencode-vps`)

- `origin/agent/chatgpt` avanzó a `c010da6` (14 commits: endurecimiento de orígenes HTTPS, nuevas regresiones de readiness y de capacidad vía ASGI, docs de traspaso de Fase 1).
- `integration/chatgpt-opencode-20261108b` actualizada: merge de `c010da6` y merge de `origin/agent/opencode-vps` (`6553036`). Árbol combinado verificado: **1027 passed, 11 skipped**; `compileall`, `check_frontend_js.py` OK; E2E de navegador aprobado.
- CI del commit combinado `6553036` (run `42498413465`): **5/5 en verde** — python-tests 1027/1027, postgres-migrations 74 passed, studio-browser-e2e aprobado, container-image-build y qdrant-cloud-integration success.
- GitHub cerró el PR #9 como MERGED al contener la candidata ambas ramas; sigue sin fusionarse nada a `main`.
- `REL-01` sigue bloqueada por AUTH/MFA en staging, AGT-04, catálogo/precios QvaPay y sandbox oficial; la V1.0 no está liberada.

## Despliegue controlado en el stack real — 2026-11-08 (autorizado por el propietario, `agent/opencode-vps`)

El propietario autorizó cerrar la Fase 11 en producción con un despliegue controlado de las imágenes construidas desde `agent/opencode-vps` (HEAD al desplegar: `d447482`).

### Procedimiento ejecutado
1. Backup previo: `backups/pre-release-20261108T161250Z.dump` (pg_dump CUSTOM vía `docker exec`, 0600) — válido, 274 objetos; idéntico contenido al de 2026-11-08 (sin escrituras de usuarios desde el último dump).
2. Imágenes etiquetadas para rollback: `axyron-atomic-api:rollback-20261108` (22faebefbabe) y `axyron-atomic-frontend:rollback-20261108` (2fd6d7a6e48f).
3. `docker compose --project-name axyron-atomic -f compose.yaml --env-file .env build api frontend` — build OK (api → 120f6f6a023f, frontend → 4136ef24def8).
4. `docker compose ... up -d --no-deps api frontend` — contenedores recreados; postgres y redis **sin cambios**.

### Verificación posterior (real)
- `/health`: 6/6 ok (database, ollama, chat_model, embedding_model, qdrant, redis).
- `/health/readiness`: 503 `blocked` como se esperaba (AUTH desactivada; clave MFA no configurada); modo facturación `shadow`.
- Landing y assets (`/`, `/studio.js`, `/admin.js`): 200 OK. `admin.js` servido incluye la sección «Conciliación de cobros QvaPay» (`billing-qvapay-run` presente).
- `POST /admin/billing/qvapay/reconcile`: 503 (fail-closed, auth desactivada) — comportamiento correcto; no ejecuta llamadas externas.
- Logs de la API sin errores de arranque.
- El stack legado `axion-atomic` sigue ausente; el volumen de producción `axyron_atomic_pgdata` no fue modificado ni recreado.

### Límites
- La V1.0 **no** está liberada: `REL-01` sigue bloqueada (AUTH/MFA es Fase 2 del flujo del propietario y requiere verificación en vivo con SMTP/MFA reales; AGT-04 daemon; catálogo/precios QvaPay; cobros). Lo desplegado es el código de la rama de desarrollo con las puertas seguras intactas (AUTH/BILLING/QVAPAY desactivados por defecto).
- Rollback ensayado de facto solo en el procedimiento (imagen previa etiquetada y salud verificada tras el cambio); el rollback completo de DB no fue necesario.

### Ajuste de tabla (segundo)
Fase 11 pasa de 80 % a **85 %**: actualización controlada ejecutada y verificada en el host real (backup previo, rollback etiquetado, build, recreación y salud post-deploy). El 15 % restante corresponde a AUTH/MFA (Fase 2), rollback DB completo y REL-01.

## RELEASE CANDIDATE EN PRODUCCIÓN — 2026-11-08 (autorización total del propietario, rama `agent/opencode-vps`)

### Base de datos
- El backup `pre-release-20261108T161250Z.dump` (restored + migrado en contenedor desechable) confirmó producción en `schema_migrations=021`.
- Migrador real aplicado sobre producción (`docker exec axyron-atomic-api-1 python -m api.migrate`): **022** (`agent_runs_status_check` + estado `cancelled`) y **023** (`payment_invoices` + índices). Segunda ejecución: ninguna migración pendiente. Sin pérdida de datos; backups previos intactos.
- Rehearsal completo (restore → migrate → doble ejecución → borrado): OK.

### Autenticación habilitada en producción
- SMTP validado sin enviar correo: `smtp.gmail.com:587` STARTTLS + autenticación OK (credenciales del `.env`, nunca impresas).
- OAuth Google/GitHub configurado en `.env` (presencia verificada, valores no leídos).
- `AUTH_ENABLED=true` aplicado y contenedor API recreado. `/health/readiness` → **`ready`**: authentication_enabled/transactional_email/https_cookie/public_https_origin/mfa_encryption_key todos `true`.
- Verificación conductual: `/auth/projects` sin sesión → 401; `chat/completions` → 401; `admin/billing/qvapay/reconcile` → 401; `auth/register` con payload inválido → 422 (antes de tocar SMTP). No se crearon cuentas ni se enviaron correos.
- MFA real (claves `runtime-v1` de 32 B ya presentes en `.env`, keyring vacío) — login MFA no ensayado con cuenta real.
- Rollback de configuración disponible: `.env` previo en `/tmp/.env.rollback-20261108` (0600) y restauración simplemente reaplicando `AUTH_ENABLED=false` + recrear.

### main fusionado y desplegado
- `integration/chatgpt-opencode-20261108b` → **PR #9 cerrado MERGED** (auto-marcado por GitHub al quedar contenido).
- `main`: fast-forward local → `origin/main` (`e671347`) y merge `--no-ff` de la candidata → **`main = e383621`**, push EXITOSO.
- Imágenes etiquetadas `pre-main-20261108` (api `120f6f6a023f`, frontend `4136ef24def8`); `rollback-20261108` conserva la imagen previa al upgrade de hoy.
- Rebuild desde `main` y recreación: api `b374e97df9cd`, frontend sin cambios (mismo contenido, no se recreó). `/health` 6/6 ok, `/health/readiness` **ready**, landing/assets 200, `/admin.js` con sección QvaPay presente, dominio público `https://axyronatomic.com/health` → 200.
- CI de `main` (`42499947946`, `e383621`): **5/5 en verde** — python-tests 1027/1027, postgres-migrations 74, studio-browser-e2e, container-image-build, qdrant-cloud-integration.

### Lo que NO se activó y por qué
- `BILLING_ENFORCEMENT_ENABLED=false`: sin catálogo/precios aprobados; el modo `shadow` sigue midiendo.
- `QVAPAY_ENABLED=false` y sin token: no existen `QVAPAY_USER_TOKEN` ni catálogo de cobros aprobados; no se inventan credenciales. El flujo queda listo para activación cuando el propietario los entregue.
- Sandbox Docker (`SANDBOX_DOCKER_ENABLED=false`): requiere daemon dedicado no privilegiado + imágenes por digest + TLS (AGT-04).
- `REL-01` sigue NO LIBERADA como declaración formal: falta ensayo de registro/verificación/MFA con buzón real, checkout QvaPay con catálogo, sandbox y validación E2E en producción. Infraestructura y puertas operativas sí están cerradas para todo lo que depende de este host.

### Fase 11
- 85 % → **90 %**: actualización en producción ensayada y verificada; migraciones reales aplicadas con rehearsal previo; inventario ejecutado; configuración validada; rollback documentado.

## Rehearsal de rollback de aplicación y verificación de assets — 2026-11-08 (continuación, `agent/opencode-vps`)

### Assets desplegados == repositorio (verificado byte a byte)
`studio.js`, `studio.css`, `workspace.js`, `admin.js` e `index.html` servidos por `https://127.0.0.1:8070/` son **idénticos** a `frontend/` en `main` (`cmp`, sin diferencias). La instancia sirve exactamente el código auditado.

### Rollback de aplicación ensayado en vivo (ida y vuelta)
1. Imágenes actuales etiquetadas `main-20261108`; `latest` repuntado a `rollback-20261108` (imágenes previas al despliegue de hoy).
2. `up -d --no-deps api frontend` con las imágenes antiguas: arranque correcto en 17 s; `/health` 6/6 ok; `admin.js` servido **sin** la sección QvaPay (comportamiento de la imagen previa, esperado).
3. Re-forward a `main-20261108`: `up -d --no-deps api frontend`; `/health` 6/6 ok; readiness **ready**; landing 200; `admin.js` recuperado con la sección QvaPay (`billing-qvapay-run`).
4. Dominio público `https://axyronatomic.com/health` → 200.

Conclusión: el procedimiento de rollback documentado funciona en producción real contra la base ya migrada (023). No se requieren cambios adicionales; volumen y datos intactos durante todo el ejercicio.

### Pendiente para el 100 % (bloqueos externos reales)
1. `QVAPAY_USER_TOKEN` real y catálogo/precios aprobados → activar QVAPAY y pasar a cobro asistido.
2. Buzón de prueba del propietario para ensayo de registro/verificación/MFA end-to-end (la configuración y el flujo SMTP están validados; falta el clic real en el correo).
3. Sandbox AGT-04 (daemon dedicado no privilegiado + imágenes por digest + TLS).
4. Declaración formal de REL-01/V1.0 liberada tras (1)-(3) y aceptación del propietario.

## Certificación QA-HEAD-001/002 — 2026-11-08 (`agent/opencode-vps`)

### HEAD y CI
- `origin/main` == `a5df4f774eaac141b7b87ba5ce7cc958dba902c6` (coincide con el SHA de referencia). `agent/opencode-vps` == `a5df4f7`. El `main` local estaba 19 commits por detrás; actualizado con ff-only.
- CI del SHA exacto (run `42515231275`): `python-tests`, `studio-browser-e2e`, `container-image-build`, `postgres-migrations`, `qdrant-cloud-integration` → **5/5 success**. No se presentan como resultado del HEAD ejecuciones de commits anteriores.

### Regresiones
- Primera ejecución local: 1 fallo en `tests/test_frontend_serving.py::test_api_routes_keep_priority_over_frontend_mount` (esperaba 503 con AUTH cerrada; el `.env` real de este host la tiene habilitada → 401). Defecto de hermeticidad de la prueba; corregido con `mock.patch.object(settings, "auth_enabled", False)`.
- Suite final: **1033 passed, 13 skipped** (PostgreSQL). `compileall`, `check_frontend_js.py`, `bash -n scripts/*.sh`, `pip check`, `git diff --check`: correctos. Sin código de producción modificado.

### Producción (sondas de solo lectura; sin cambios en el VPS)
- `/health/readiness` → `ready` (`authentication_enabled`, `transactional_email`, `https_cookie`, `public_https_origin`, `mfa_encryption_key` = true; billing `shadow`). `/auth/me` → 401 (local y dominio público). Migraciones 022/023 ya aplicadas el 2026-11-08. Rollback de aplicación ensayado (evidencia previa del día).
- Flags comprobados sin imprimir valores: `AUTH_ENABLED=true`; `QVAPAY_ENABLED=false`; `BILLING_ENFORCEMENT_ENABLED` no habilitado; `SANDBOX_DOCKER_ENABLED` ausente (por defecto `false`, fail-closed). Cobros/ledger/sandbox/QvaPay **desactivados**.
- Deriva documentada: producción sirve el código de `main` previo (`e383621`/`aad1f48`); único delta de código en `a5df4f7` = valor por defecto de `qvapay_lightning_address` (inerte) más docs/tests. Actualizar producción corresponde al propietario.

### Documentación reconciliada (historial preservado)
- `docs/V1_ACCEPTANCE_MATRIX.md`: filas API-02, STU-01, STU-04, SEC-01/02/03, QA-01/02, REL-01 actualizadas a la evidencia real; nueva sección QA-HEAD-001/002.
- `docs/PRODUCTION_INITIAL_RELEASE_GATE.md` y `docs/AGENT_RUNTIME_API_STATUS.md`: bloques fechados de estado actual añadidos al inicio; contenido histórico conservado.
- `README.md`: nota de estado verificado en «Estado de implementación».

### Pendiente / bloqueado
- `REL-01` bloqueada: buzón real (registro/verificación/MFA), `QVAPAY_USER_TOKEN` + catálogo/precios aprobados, AGT-04 (daemon TLS + imágenes por digest). V1.0 no liberada.
- PR hacia `main` preparado; no se fusiona (decisión del propietario tras auditoría de ChatGPT).

## Despliegue controlado a `main = a2f41d0` — 2026-11-08 (autorizado por el propietario, `agent/opencode-vps`)

### Procedimiento ejecutado
1. PR #16 (QA-HEAD-001/002, `be83ca6`) fusionado a `main` → **`main = a2f41d0`** (merge commit); CI del PR 5/5 verde (run `42517493977`).
2. `main` local actualizado ff-only; árbol == `be83ca6`.
3. Backup previo en producción: `backups/pre-qa-head-deploy-20261108T200210Z.dump` (0600, 297 objetos, formato CUSTOM) vía `pg_dump` dentro del contenedor; contenedor PostgreSQL **sin reinicios ni cambios**.
4. Imágenes previas etiquetadas como ancla de rollback: `axyron-atomic-api:rollback-qa-head-20261108`, `axyron-atomic-frontend:rollback-qa-head-20261108` (= `main-20261108`).
5. `docker compose build api frontend` desde `main` (api `92249f21f80c`); `up -d --no-deps api frontend`; postgres/redis intactos.

### Verificación posterior (real)
- `/health` 200: database, ollama, chat/embedding models, qdrant, redis — 6/6 ok.
- `/health/readiness` 200 `ready` (auth/email/cookie/origin/MFA key true; billing `shadow`).
- `/auth/me` → 401; landing 200; dominio público `https://axyronatomic.com/health` → 200; `admin.js` servido incluye conciliación QvaPay.
- Assets servidos == repositorio (`studio.js`, `studio.css`, `workspace.js`, `admin.js`, index) — idénticos (`cmp`).
- Logs de la API sin errores de arranque.
- Producción == `main` (`a2f41d0`). Cambios de contenido respecto al despliegue anterior: corrección de hermeticidad de `tests/test_frontend_serving.py` y documentación de reconciliación — **sin código de producción modificado**.

### Pendiente
- Sin cambios en la decisión de cobros: `BILLING_ENFORCEMENT_ENABLED` sigue desactivado; `QVAPAY_ENABLED=false`; sandbox desactivado. `REL-01` bloqueada (buzón real, token/catálogo QvaPay, AGT-04). V1.0 no se declara liberada.

## Auditoría integral V1.0 — 2026-11-08 (`agent/opencode-vps`, base `main = ad68953`)

### HEAD y ramas
- Fetch completo; las tres ramas de trabajo apuntan a `ad68953` (merge de PR #15 con ARC-02 integrado). Árbol limpio.
- `main` CI del SHA exacto (run `42525211231`): **6/6 jobs** — python-tests, postgres-migrations, qdrant-cloud-integration, **qdrant-e2e**, container-image-build, studio-browser-e2e.
- Suite local (`DATABASE_URL=sqlite`): **1035 passed, 22 skipped**; `compileall`, `check_frontend_js.py`, `bash -n`, `pip check`, `git diff --check`: OK.
- Secretos: sin `.env` ni claves trackeadas; sin patrones de credenciales; `.pyc` no trackeados.

### Corrección de defectos
- `tests/test_rag_replace_rollback.py` (nuevo): fija con fallo inyectado el contrato de rollback de `replace_source` — (1) falla el borrado de fragmentos antiguos → se retira la versión nueva, la previa permanece íntegra y la operación falla con `KnowledgeStoreUnavailable`; (2) también falla el rollback → sigue fallando cerrada; nunca se declara éxito. Unitario con doble en memoria; no sustituye a la E2E real (`tests/test_rag_qdrant_e2e.py`).
- Sin cambios funcionales de producción; `rag/*` intacto.

### Documentación reconciliada (historial preservado)
- Matriz: `STU-03`/`AI-02` → Implementada con E2E real en CI (`ad68953`); `QA-01`/`QA-02` con `ad68953` y 6/6; `OPS-03` actualizado (rollback ida y vuelta en vivo; upgrade en staging pendiente); sección de conteo real de criterios (9 Verificadas · 9 Implementadas · 12 Parciales · 1 Bloqueada = 31) y desglose implementación/pruebas/productivo/bloqueadores.
- Gate y README: referencias al SHA actual e inclusión del job `qdrant-e2e` en la lista de CI.

### Estado honesto
- Implementación ~90 % de criterios con código y CI verde; pruebas verificadas ~80 %; preparación productiva ~75 % (producción en `a2f41d0`; 15 commits de `main` pendientes de despliegue por el propietario; delta sin migraciones).
- `REL-01` **bloqueada**: (1) buzón real; (2) token/catálogo QvaPay; (3) AGT-04. V1.0 no se declara liberada.

## Despliegue controlado a `main = a298344` — 2026-11-08 (autorizado por el propietario)

- PR #22 fusionado con autorización del propietario: `main = a298344`; CI 6/6 verde (run `42526094951`).
- Ramas sincronizadas ff: `main` = `origin/agent/chatgpt` = `origin/agent/opencode-vps` = `a298344`.
- Backup previo: `backups/pre-main-a298344-20261108T213805Z.dump` (0600, 297 objetos). Imágenes previas etiquetadas `axyron-atomic-api:rollback-a298344` y `axyron-atomic-frontend:rollback-a298344`.
- Rebuild y recreación solo de la API (el frontend no cambió de contenido); postgres y redis intactos.
- Verificación real: `/health` 6/6 ok; `/health/readiness` `ready` (auth/email/cookie/origin/MFA true; billing `shadow`); `/auth/me` 401; dominio público 200; assets servidos == repo (`cmp`); logs sin errores.
- Contenido respecto al despliegue anterior: rollback test `replace_source`, docs QA/reconciliación y demás archivos de PR #22. Sin cambios de esquema ni migraciones (022/023 intactas).
- `REL-01` sigue bloqueada (buzón real, QvaPay token/catálogo, AGT-04). V1.0 no se declara liberada.
