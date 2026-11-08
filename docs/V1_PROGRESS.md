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
| 11 | Instalación y documentación | 70% | EN PROGRESO |
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
